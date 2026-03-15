from __future__ import annotations

from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_DEFAULT_CONFIG = {
    "max_nesting_depth_warning": 6,
    "max_module_size_warning": 1200,
    "max_dependency_fanout_warning": 12,
    "max_dependency_fanin_warning": 12,
    "god_module_risk_factor_threshold": 3,
    "architectural_concentration_warning_ratio": 0.35,
}


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _slug(value: str) -> str:
    text = str(value).strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    compact = "".join(chars)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_") or "item"


def _share(part: float, total: float) -> float:
    if total <= 0.0:
        return 0.0
    return max(0.0, min(1.0, part / total))


def _module_name(row: dict[str, Any]) -> str:
    for key in ("module", "module_name", "component", "name"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return "unknown_module"


def _module_metric(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row:
            return _safe_float(row.get(key, 0.0))
    return 0.0


def _depends_on(row: dict[str, Any]) -> list[str]:
    value = row.get("depends_on", [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class ArchitecturalComplexityValidationPlugin(ValidationPlugin):
    plugin_name = "architectural_complexity_validation"
    plugin_version = "1.0.0"
    plugin_category = "ARCHITECTURE_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        project_root = Path(str(context.get("project_root", "."))).resolve()
        pf = Path(str(context.get("pf", "."))).resolve()

        config_path = (project_root / "architectural_validation_config.json").resolve()
        loaded_config = read_json(config_path)
        config = dict(_DEFAULT_CONFIG)
        for key in _DEFAULT_CONFIG:
            if key not in loaded_config:
                continue
            if key in {
                "max_nesting_depth_warning",
                "max_module_size_warning",
                "max_dependency_fanout_warning",
                "max_dependency_fanin_warning",
                "god_module_risk_factor_threshold",
            }:
                config[key] = _safe_int(loaded_config.get(key, config[key]))
            else:
                config[key] = _safe_float(loaded_config.get(key, config[key]))

        self.inputs = {
            "config": config,
            "config_path": str(config_path),
            "certification_target": read_json(project_root / "certification_target.json"),
            "subtarget_index": read_json(pf / "rollup" / "01_subtarget_index.json"),
            "subtarget_results": read_json(pf / "rollup" / "02_subtarget_results.json"),
            "component_history_context": read_json(pf / "history" / "43_component_history_context.json"),
            "watchlist": read_json(pf / "intelligence" / "110_component_watchlist.json"),
            "structural_profile": read_json(pf / "architecture" / "200_structural_profile.json"),
        }
        return self.inputs

    def _finding(
        self,
        *,
        finding_id: str,
        severity: str,
        component_or_module: str,
        risk_type: str,
        measured_value: float,
        threshold_triggered: str,
        supporting_metrics: dict[str, Any],
        recommended_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "component_or_module": component_or_module,
            "risk_type": risk_type,
            "measured_value": round(measured_value, 4),
            "threshold_triggered": threshold_triggered,
            "supporting_metrics": dict(supporting_metrics),
            "recommended_actions": list(recommended_actions),
        }

    def run_analysis(self) -> dict[str, Any]:
        config = self.inputs.get("config", {}) if isinstance(self.inputs.get("config", {}), dict) else {}
        depth_warn = _safe_int(config.get("max_nesting_depth_warning", _DEFAULT_CONFIG["max_nesting_depth_warning"]))
        module_size_warn = _safe_int(config.get("max_module_size_warning", _DEFAULT_CONFIG["max_module_size_warning"]))
        fanout_warn = _safe_int(config.get("max_dependency_fanout_warning", _DEFAULT_CONFIG["max_dependency_fanout_warning"]))
        fanin_warn = _safe_int(config.get("max_dependency_fanin_warning", _DEFAULT_CONFIG["max_dependency_fanin_warning"]))
        god_threshold = _safe_int(config.get("god_module_risk_factor_threshold", _DEFAULT_CONFIG["god_module_risk_factor_threshold"]))
        concentration_warn = _safe_float(config.get("architectural_concentration_warning_ratio", _DEFAULT_CONFIG["architectural_concentration_warning_ratio"]))

        structural_payload = self.inputs.get("structural_profile", {}) if isinstance(self.inputs.get("structural_profile", {}), dict) else {}
        modules = [row for row in structural_payload.get("modules", []) if isinstance(row, dict)]

        if not modules:
            component_ctx_payload = self.inputs.get("component_history_context", {}) if isinstance(self.inputs.get("component_history_context", {}), dict) else {}
            component_ctx_rows = [row for row in component_ctx_payload.get("rows", []) if isinstance(row, dict)]
            for row in component_ctx_rows:
                name = _module_name(row)
                modules.append(
                    {
                        "module": name,
                        "nesting_depth": _module_metric(row, "nesting_depth", "wrapper_depth"),
                        "module_size": _module_metric(row, "module_size", "size", "line_count"),
                        "dependency_fanout": _module_metric(row, "dependency_fanout", "fanout"),
                        "dependency_fanin": _module_metric(row, "dependency_fanin", "fanin"),
                        "depends_on": _depends_on(row),
                    }
                )

        watch_payload = self.inputs.get("watchlist", {}) if isinstance(self.inputs.get("watchlist", {}), dict) else {}
        watch_rows = [row for row in watch_payload.get("rows", []) if isinstance(row, dict)]
        watch_by_component = {
            str(row.get("component", "")).strip(): str(row.get("watch_class", "NORMAL")).upper()
            for row in watch_rows
            if str(row.get("component", "")).strip()
        }

        module_by_name = {_module_name(row): row for row in modules}
        depends_map = {name: _depends_on(row) for name, row in module_by_name.items()}

        incoming_counts = {name: 0 for name in module_by_name}
        for source, targets in depends_map.items():
            for target in targets:
                if target in incoming_counts:
                    incoming_counts[target] += 1

        explicit_cycles = [row for row in structural_payload.get("dependency_cycles", []) if isinstance(row, list) and row]
        cycle_pairs: set[tuple[str, str]] = set()
        for source, targets in depends_map.items():
            for target in targets:
                if source in depends_map.get(target, []):
                    cycle_pairs.add(tuple(sorted((source, target))))

        nesting_findings: list[dict[str, Any]] = []
        size_findings: list[dict[str, Any]] = []
        coupling_findings: list[dict[str, Any]] = []
        dependency_findings: list[dict[str, Any]] = []

        risk_factor_counts: dict[str, int] = {name: 0 for name in module_by_name}

        for name, row in module_by_name.items():
            depth = _safe_float(_module_metric(row, "nesting_depth", "depth", "wrapper_depth"))
            module_size = _safe_float(_module_metric(row, "module_size", "size", "line_count"))
            fanout = _safe_float(_module_metric(row, "dependency_fanout", "fanout", "out_degree"))
            fanin = _safe_float(_module_metric(row, "dependency_fanin", "fanin", "in_degree"))
            if fanin <= 0.0:
                fanin = _safe_float(incoming_counts.get(name, 0))

            if depth > depth_warn:
                risk_factor_counts[name] += 1
                severity = "FAIL" if depth >= depth_warn + 3 else "WARNING"
                nesting_findings.append(
                    self._finding(
                        finding_id=f"EXCESSIVE_NESTING_DEPTH_{_slug(name)}",
                        severity=severity,
                        component_or_module=name,
                        risk_type="EXCESSIVE_NESTING_DEPTH",
                        measured_value=depth,
                        threshold_triggered=f"max_nesting_depth_warning:{depth_warn}",
                        supporting_metrics={
                            "nesting_depth": depth,
                            "watch_class": watch_by_component.get(name, "NORMAL"),
                        },
                        recommended_actions=[
                            "cap nesting depth by flattening wrapper layers",
                            "split oversized module into smaller units",
                            "prioritize architecture review for this module",
                        ],
                    )
                )

            if module_size > module_size_warn:
                risk_factor_counts[name] += 1
                severity = "FAIL" if module_size >= module_size_warn * 1.5 else "WARNING"
                size_findings.append(
                    self._finding(
                        finding_id=f"OVERSIZED_MODULE_WARNING_{_slug(name)}",
                        severity=severity,
                        component_or_module=name,
                        risk_type="OVERSIZED_MODULE_WARNING",
                        measured_value=module_size,
                        threshold_triggered=f"max_module_size_warning:{module_size_warn}",
                        supporting_metrics={
                            "module_size": module_size,
                            "nesting_depth": depth,
                        },
                        recommended_actions=[
                            "split oversized module into smaller units",
                            "extract shared logic into neutral module",
                            "move concentrated responsibilities into smaller subsystems",
                        ],
                    )
                )

            hotspot = False
            if fanout > fanout_warn or fanin > fanin_warn:
                hotspot = True
                risk_factor_counts[name] += 1
                severity = "FAIL" if fanout >= fanout_warn * 1.5 or fanin >= fanin_warn * 1.5 else "WARNING"
                coupling_findings.append(
                    self._finding(
                        finding_id=f"COUPLING_HOTSPOT_{_slug(name)}",
                        severity=severity,
                        component_or_module=name,
                        risk_type="COUPLING_HOTSPOT",
                        measured_value=max(fanout, fanin),
                        threshold_triggered=f"max_dependency_fanout_warning:{fanout_warn}|max_dependency_fanin_warning:{fanin_warn}",
                        supporting_metrics={
                            "dependency_fanout": fanout,
                            "dependency_fanin": fanin,
                            "depends_on_count": len(depends_map.get(name, [])),
                        },
                        recommended_actions=[
                            "reduce dependency fan-out from this component",
                            "extract shared logic into neutral module",
                            "prioritize architecture review for this module",
                        ],
                    )
                )

            if hotspot and watch_by_component.get(name, "NORMAL") in {"HOT", "CRITICAL"}:
                risk_factor_counts[name] += 1

        for pair in sorted(cycle_pairs):
            left, right = pair
            risk_factor_counts[left] = risk_factor_counts.get(left, 0) + 1
            risk_factor_counts[right] = risk_factor_counts.get(right, 0) + 1
            dependency_findings.append(
                self._finding(
                    finding_id=f"CIRCULAR_DEPENDENCY_RISK_{_slug(left)}_{_slug(right)}",
                    severity="WARNING",
                    component_or_module=f"{left}<->{right}",
                    risk_type="CIRCULAR_DEPENDENCY_RISK",
                    measured_value=2.0,
                    threshold_triggered="bidirectional_dependency_detected",
                    supporting_metrics={
                        "left_depends_on_right": True,
                        "right_depends_on_left": True,
                    },
                    recommended_actions=[
                        "break bidirectional dependency chain",
                        "extract shared logic into neutral module",
                        "reduce dependency fan-out from this component",
                    ],
                )
            )

        for idx, cycle in enumerate(explicit_cycles, start=1):
            names = [str(item).strip() for item in cycle if str(item).strip()]
            if len(names) < 2:
                continue
            for name in names:
                risk_factor_counts[name] = risk_factor_counts.get(name, 0) + 1
            dependency_findings.append(
                self._finding(
                    finding_id=f"CIRCULAR_DEPENDENCY_RISK_cycle_{idx}",
                    severity="FAIL" if len(names) >= 3 else "WARNING",
                    component_or_module="->".join(names),
                    risk_type="CIRCULAR_DEPENDENCY_RISK",
                    measured_value=float(len(names)),
                    threshold_triggered="explicit_dependency_cycle_detected",
                    supporting_metrics={
                        "cycle_length": len(names),
                        "cycle_nodes": names,
                    },
                    recommended_actions=[
                        "break bidirectional dependency chain",
                        "extract shared logic into neutral module",
                        "prioritize architecture review for this module",
                    ],
                )
            )

        for name, count in sorted(risk_factor_counts.items()):
            if count >= god_threshold:
                module_row = module_by_name.get(name, {}) if isinstance(module_by_name.get(name, {}), dict) else {}
                module_size = _safe_float(_module_metric(module_row, "module_size", "size", "line_count"))
                dependency_findings.append(
                    self._finding(
                        finding_id=f"GOD_MODULE_CANDIDATE_{_slug(name)}",
                        severity="FAIL" if count >= god_threshold + 1 else "WARNING",
                        component_or_module=name,
                        risk_type="GOD_MODULE_CANDIDATE",
                        measured_value=float(count),
                        threshold_triggered=f"god_module_risk_factor_threshold:{god_threshold}",
                        supporting_metrics={
                            "risk_factor_count": count,
                            "module_size": module_size,
                            "dependency_fanout": _safe_float(_module_metric(module_row, "dependency_fanout", "fanout", "out_degree")),
                            "dependency_fanin": _safe_float(_module_metric(module_row, "dependency_fanin", "fanin", "in_degree")),
                        },
                        recommended_actions=[
                            "split oversized module into smaller units",
                            "move concentrated responsibilities into smaller subsystems",
                            "prioritize architecture review for this module",
                        ],
                    )
                )

        module_sizes = {
            name: _safe_float(_module_metric(row, "module_size", "size", "line_count"))
            for name, row in module_by_name.items()
        }
        total_size = sum(value for value in module_sizes.values() if value > 0.0)
        if total_size > 0.0 and module_sizes:
            dominant_name = sorted(module_sizes.items(), key=lambda item: (-item[1], item[0]))[0][0]
            dominant_share = _share(module_sizes.get(dominant_name, 0.0), total_size)
            if dominant_share >= concentration_warn:
                dependency_findings.append(
                    self._finding(
                        finding_id=f"ARCHITECTURAL_CONCENTRATION_WARNING_{_slug(dominant_name)}",
                        severity="FAIL" if dominant_share >= min(0.95, concentration_warn * 1.7) else "WARNING",
                        component_or_module=dominant_name,
                        risk_type="ARCHITECTURAL_CONCENTRATION_WARNING",
                        measured_value=dominant_share,
                        threshold_triggered=f"architectural_concentration_warning_ratio:{concentration_warn}",
                        supporting_metrics={
                            "dominant_module_size": module_sizes.get(dominant_name, 0.0),
                            "total_module_size": total_size,
                            "dominant_share": dominant_share,
                            "module_count": len(module_sizes),
                        },
                        recommended_actions=[
                            "move concentrated responsibilities into smaller subsystems",
                            "extract shared logic into neutral module",
                            "split oversized module into smaller units",
                        ],
                    )
                )

        all_findings = [*nesting_findings, *size_findings, *coupling_findings, *dependency_findings]
        recommendations: list[dict[str, Any]] = []
        for row in all_findings:
            recommendations.append(
                {
                    "finding_id": str(row.get("finding_id", "")),
                    "severity": str(row.get("severity", "INFO")),
                    "component_or_module": str(row.get("component_or_module", "")),
                    "risk_type": str(row.get("risk_type", "")),
                    "recommended_actions": row.get("recommended_actions", []),
                }
            )

        fail_count = sum(1 for row in all_findings if str(row.get("severity", "INFO")).upper() == "FAIL")
        warning_count = sum(1 for row in all_findings if str(row.get("severity", "INFO")).upper() == "WARNING")
        status = "PASS"
        if fail_count > 0:
            status = "FAIL"
        elif warning_count > 0:
            status = "WARNING"

        self.analysis = {
            "status": status,
            "config": config,
            "totals": {
                "module_count": len(module_by_name),
                "total_module_size": round(total_size, 4),
            },
            "findings": {
                "nesting_depth": nesting_findings,
                "module_size": size_findings,
                "coupling": coupling_findings,
                "dependency_risk": dependency_findings,
            },
            "recommendations": recommendations,
            "summary": {
                "finding_count": len(all_findings),
                "fail_count": fail_count,
                "warning_count": warning_count,
            },
        }
        return self.analysis

    def generate_artifacts(self, output_dir: Path) -> list[str]:
        architecture_dir = output_dir.parent / "architecture" / "architecture"
        findings = self.analysis.get("findings", {}) if isinstance(self.analysis.get("findings", {}), dict) else {}
        totals = self.analysis.get("totals", {}) if isinstance(self.analysis.get("totals", {}), dict) else {}
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        nesting_rows = findings.get("nesting_depth", []) if isinstance(findings.get("nesting_depth", []), list) else []
        size_rows = findings.get("module_size", []) if isinstance(findings.get("module_size", []), list) else []
        coupling_rows = findings.get("coupling", []) if isinstance(findings.get("coupling", []), list) else []
        dependency_rows = findings.get("dependency_risk", []) if isinstance(findings.get("dependency_risk", []), list) else []
        recommendation_rows = self.analysis.get("recommendations", []) if isinstance(self.analysis.get("recommendations", []), list) else []

        write_json(architecture_dir / "250_nesting_depth_report.json", {"rows": nesting_rows, "totals": totals, "summary": summary})
        write_json(architecture_dir / "251_module_size_report.json", {"rows": size_rows, "totals": totals, "summary": summary})
        write_json(architecture_dir / "252_coupling_hotspots.json", {"rows": coupling_rows, "totals": totals, "summary": summary})
        write_json(architecture_dir / "253_dependency_risk_report.json", {"rows": dependency_rows, "totals": totals, "summary": summary})
        write_json(architecture_dir / "254_architecture_recommendations.json", {"rows": recommendation_rows, "summary": summary})

        lines = [
            "# Architectural Complexity Validation Summary",
            "",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- module_count: {totals.get('module_count', 0)}",
            f"- finding_count: {summary.get('finding_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Top Findings",
        ]
        top_rows = sorted(
            [*nesting_rows, *size_rows, *coupling_rows, *dependency_rows],
            key=lambda row: (
                str(row.get("severity", "INFO")) != "FAIL",
                str(row.get("severity", "INFO")) != "WARNING",
                -_safe_float(row.get("measured_value", 0.0)),
                str(row.get("finding_id", "")),
            ),
        )
        if top_rows:
            for row in top_rows[:15]:
                lines.append(
                    "- finding_id="
                    + str(row.get("finding_id", ""))
                    + " severity="
                    + str(row.get("severity", ""))
                    + " component_or_module="
                    + str(row.get("component_or_module", ""))
                    + " risk_type="
                    + str(row.get("risk_type", ""))
                    + " measured_value="
                    + str(row.get("measured_value", 0.0))
                )
        else:
            lines.append("- no architecture complexity risks detected")

        write_text(architecture_dir / "255_architecture_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/architecture/architecture/250_nesting_depth_report.json",
            "validation_plugins/architecture/architecture/251_module_size_report.json",
            "validation_plugins/architecture/architecture/252_coupling_hotspots.json",
            "validation_plugins/architecture/architecture/253_dependency_risk_report.json",
            "validation_plugins/architecture/architecture/254_architecture_recommendations.json",
            "validation_plugins/architecture/architecture/255_architecture_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"findings={summary.get('finding_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
