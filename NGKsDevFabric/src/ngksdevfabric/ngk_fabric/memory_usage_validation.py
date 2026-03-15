from __future__ import annotations

from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_DEFAULT_CONFIG = {
    "peak_memory_warning_mb": 512.0,
    "peak_memory_fail_mb": 1024.0,
    "stage_memory_share_warning_ratio": 0.45,
    "memory_growth_warning_mb": 128.0,
    "repeated_high_memory_threshold": 3,
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


def _share(part: float, total: float) -> float:
    if total <= 0.0:
        return 0.0
    return max(0.0, min(1.0, part / total))


def _slug(value: str) -> str:
    text = str(value).strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    compact = "".join(chars)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_") or "item"


def _row_memory_mb(row: dict[str, Any]) -> float:
    for key in ("peak_memory_mb", "memory_peak_mb", "max_rss_mb", "working_set_peak_mb", "memory_mb"):
        if key in row:
            return _safe_float(row.get(key, 0.0))
    return 0.0


def _stage_memory_map(stage_summary: dict[str, Any]) -> dict[str, float]:
    candidates = [
        stage_summary.get("stage_peak_memory_mb", {}),
        stage_summary.get("stage_memory_mb", {}),
        stage_summary.get("stage_memory_usage_mb", {}),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return {str(name): _safe_float(value) for name, value in candidate.items()}
    return {}


class MemoryUsageValidationPlugin(ValidationPlugin):
    plugin_name = "memory_usage_validation"
    plugin_version = "1.0.0"
    plugin_category = "MEMORY_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        project_root = Path(str(context.get("project_root", "."))).resolve()
        pf = Path(str(context.get("pf", "."))).resolve()

        config_path = (project_root / "memory_validation_config.json").resolve()
        loaded_config = read_json(config_path)
        config = dict(_DEFAULT_CONFIG)
        for key in _DEFAULT_CONFIG:
            if key not in loaded_config:
                continue
            if key == "repeated_high_memory_threshold":
                config[key] = _safe_int(loaded_config.get(key, config[key]))
            else:
                config[key] = _safe_float(loaded_config.get(key, config[key]))

        self.inputs = {
            "config": config,
            "config_path": str(config_path),
            "execution_receipts": read_json(pf / "execution" / "132_execution_receipts.json"),
            "execution_failures": read_json(pf / "execution" / "133_execution_failures.json"),
            "execution_stage_summary": read_json(pf / "pipeline" / "141_execution_stage_summary.json"),
            "rerun_summary": read_json(pf / "pipeline" / "142_certification_rerun_summary.json"),
            "run_record": read_json(pf / "history" / "40_run_record.json"),
            "component_history_context": read_json(pf / "history" / "43_component_history_context.json"),
            "watchlist": read_json(pf / "intelligence" / "110_component_watchlist.json"),
        }
        return self.inputs

    def _finding(
        self,
        *,
        finding_id: str,
        severity: str,
        stage_or_component: str,
        peak_memory_mb: float,
        memory_growth_mb: float,
        share_of_total: float,
        threshold_triggered: str,
        historical_recurrence_count: int,
        recommended_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "stage_or_component": stage_or_component,
            "peak_memory_mb": round(peak_memory_mb, 4),
            "memory_growth_mb": round(memory_growth_mb, 4),
            "share_of_total": round(share_of_total, 4),
            "threshold_triggered": threshold_triggered,
            "historical_recurrence_count": int(historical_recurrence_count),
            "recommended_actions": list(recommended_actions),
        }

    def run_analysis(self) -> dict[str, Any]:
        config = self.inputs.get("config", {}) if isinstance(self.inputs.get("config", {}), dict) else {}
        peak_warn = _safe_float(config.get("peak_memory_warning_mb", _DEFAULT_CONFIG["peak_memory_warning_mb"]))
        peak_fail = _safe_float(config.get("peak_memory_fail_mb", _DEFAULT_CONFIG["peak_memory_fail_mb"]))
        stage_share_warn = _safe_float(config.get("stage_memory_share_warning_ratio", _DEFAULT_CONFIG["stage_memory_share_warning_ratio"]))
        growth_warn = _safe_float(config.get("memory_growth_warning_mb", _DEFAULT_CONFIG["memory_growth_warning_mb"]))
        repeated_threshold = _safe_int(config.get("repeated_high_memory_threshold", _DEFAULT_CONFIG["repeated_high_memory_threshold"]))

        execution_payload = self.inputs.get("execution_receipts", {}) if isinstance(self.inputs.get("execution_receipts", {}), dict) else {}
        execution_rows = [row for row in execution_payload.get("rows", []) if isinstance(row, dict)]
        completed_rows = [row for row in execution_rows if str(row.get("execution_status", "")).upper() == "COMPLETED"]

        stage_summary = self.inputs.get("execution_stage_summary", {}) if isinstance(self.inputs.get("execution_stage_summary", {}), dict) else {}
        stage_memory = _stage_memory_map(stage_summary)
        if not stage_memory and completed_rows:
            execution_peak = max([_row_memory_mb(row) for row in completed_rows] + [0.0])
            if execution_peak > 0.0:
                stage_memory["execution"] = execution_peak

        total_memory = sum(value for value in stage_memory.values() if value > 0.0)
        global_peak_memory = max([_row_memory_mb(row) for row in completed_rows] + list(stage_memory.values()) + [0.0])

        watch_payload = self.inputs.get("watchlist", {}) if isinstance(self.inputs.get("watchlist", {}), dict) else {}
        watch_rows = [row for row in watch_payload.get("rows", []) if isinstance(row, dict)]
        watch_by_component = {
            str(row.get("component", "")).strip(): str(row.get("watch_class", "NORMAL")).upper()
            for row in watch_rows
            if str(row.get("component", "")).strip()
        }

        component_ctx_payload = self.inputs.get("component_history_context", {}) if isinstance(self.inputs.get("component_history_context", {}), dict) else {}
        component_ctx_rows = [row for row in component_ctx_payload.get("rows", []) if isinstance(row, dict)]

        peak_findings: list[dict[str, Any]] = []
        stage_hotspot_findings: list[dict[str, Any]] = []
        growth_findings: list[dict[str, Any]] = []
        repeated_findings: list[dict[str, Any]] = []

        if global_peak_memory >= peak_warn:
            severity = "FAIL" if global_peak_memory >= peak_fail else "WARNING"
            peak_findings.append(
                self._finding(
                    finding_id="PEAK_MEMORY_BUDGET_EXCEEDED_total",
                    severity=severity,
                    stage_or_component="pipeline_total",
                    peak_memory_mb=global_peak_memory,
                    memory_growth_mb=0.0,
                    share_of_total=1.0,
                    threshold_triggered=(
                        f"peak_memory_fail_mb:{peak_fail}"
                        if severity == "FAIL"
                        else f"peak_memory_warning_mb:{peak_warn}"
                    ),
                    historical_recurrence_count=0,
                    recommended_actions=[
                        "release temporary buffers earlier",
                        "cache less aggressively",
                        "move large allocations out of the main execution path",
                    ],
                )
            )

        if total_memory > 0.0 and stage_memory:
            ordered_stages = sorted(stage_memory.items(), key=lambda item: (-item[1], item[0]))
            dominant_stage, dominant_memory = ordered_stages[0]
            dominant_share = _share(dominant_memory, total_memory)
            for stage_name, stage_peak in ordered_stages:
                share = _share(stage_peak, total_memory)
                if share >= stage_share_warn:
                    stage_hotspot_findings.append(
                        self._finding(
                            finding_id=f"STAGE_MEMORY_HOTSPOT_{_slug(stage_name)}",
                            severity="WARNING",
                            stage_or_component=stage_name,
                            peak_memory_mb=stage_peak,
                            memory_growth_mb=0.0,
                            share_of_total=share,
                            threshold_triggered=f"stage_memory_share_warning_ratio:{stage_share_warn}",
                            historical_recurrence_count=0,
                            recommended_actions=[
                                "reduce retained objects in this stage",
                                "split this stage into smaller memory-bounded substeps",
                                "release temporary buffers earlier",
                            ],
                        )
                    )

            if dominant_share >= min(0.95, stage_share_warn * 1.7):
                stage_hotspot_findings.append(
                    self._finding(
                        finding_id=f"MEMORY_IMBALANCE_WARNING_{_slug(dominant_stage)}",
                        severity="WARNING",
                        stage_or_component=dominant_stage,
                        peak_memory_mb=dominant_memory,
                        memory_growth_mb=0.0,
                        share_of_total=dominant_share,
                        threshold_triggered=f"stage_memory_share_warning_ratio:{stage_share_warn}",
                        historical_recurrence_count=0,
                        recommended_actions=[
                            "split this stage into smaller memory-bounded substeps",
                            "move large allocations out of the main execution path",
                            "investigate possible leak or accumulation pattern",
                        ],
                    )
                )

            stage_names_order = stage_summary.get("stage_order", []) if isinstance(stage_summary.get("stage_order", []), list) else []
            ordered_names = [str(name) for name in stage_names_order if str(name) in stage_memory]
            if not ordered_names:
                ordered_names = [name for name in stage_memory.keys()]

            for idx in range(1, len(ordered_names)):
                prev_name = ordered_names[idx - 1]
                curr_name = ordered_names[idx]
                growth = _safe_float(stage_memory.get(curr_name, 0.0)) - _safe_float(stage_memory.get(prev_name, 0.0))
                if growth >= growth_warn:
                    severity = "FAIL" if growth >= growth_warn * 2.0 else "WARNING"
                    growth_findings.append(
                        self._finding(
                            finding_id=f"MEMORY_GROWTH_WARNING_{_slug(prev_name)}_to_{_slug(curr_name)}",
                            severity=severity,
                            stage_or_component=f"{prev_name}->{curr_name}",
                            peak_memory_mb=_safe_float(stage_memory.get(curr_name, 0.0)),
                            memory_growth_mb=growth,
                            share_of_total=_share(_safe_float(stage_memory.get(curr_name, 0.0)), total_memory),
                            threshold_triggered=f"memory_growth_warning_mb:{growth_warn}",
                            historical_recurrence_count=0,
                            recommended_actions=[
                                "release temporary buffers earlier",
                                "reduce retained objects in this stage",
                                "investigate possible leak or accumulation pattern",
                            ],
                        )
                    )

        for row in component_ctx_rows:
            component = str(row.get("component", "")).strip()
            if not component:
                continue
            recurrence = max(
                _safe_int(row.get("high_memory_recurrence_count", 0)),
                _safe_int(row.get("memory_recurrence_count", 0)),
                _safe_int(row.get("total_regression_occurrences", 0)),
            )
            peak_memory = _safe_float(row.get("peak_memory_mb", row.get("mean_peak_memory_mb", row.get("mean_runtime_seconds", 0.0))))
            watch_class = watch_by_component.get(component, "NORMAL")
            if recurrence >= repeated_threshold and (peak_memory >= peak_warn or watch_class in {"HOT", "CRITICAL"}):
                repeated_findings.append(
                    self._finding(
                        finding_id=f"REPEATED_HIGH_MEMORY_PATH_{_slug(component)}",
                        severity="FAIL" if recurrence >= repeated_threshold * 2 else "WARNING",
                        stage_or_component=component,
                        peak_memory_mb=peak_memory,
                        memory_growth_mb=0.0,
                        share_of_total=_share(peak_memory, total_memory if total_memory > 0.0 else peak_memory),
                        threshold_triggered=f"repeated_high_memory_threshold:{repeated_threshold}",
                        historical_recurrence_count=recurrence,
                        recommended_actions=[
                            "investigate possible leak or accumulation pattern",
                            "cache less aggressively",
                            "run this analysis only under ENTERPRISE profile if appropriate",
                        ],
                    )
                )

        recommendations: list[dict[str, Any]] = []
        all_findings = [*peak_findings, *stage_hotspot_findings, *growth_findings, *repeated_findings]
        for row in all_findings:
            recommendations.append(
                {
                    "finding_id": str(row.get("finding_id", "")),
                    "severity": str(row.get("severity", "INFO")),
                    "stage_or_component": str(row.get("stage_or_component", "")),
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
                "global_peak_memory_mb": round(global_peak_memory, 4),
                "total_stage_memory_mb": round(total_memory, 4),
                "stage_memory": {key: round(value, 4) for key, value in sorted(stage_memory.items())},
            },
            "findings": {
                "peak_memory": peak_findings,
                "stage_memory_hotspots": stage_hotspot_findings,
                "memory_growth": growth_findings,
                "repeated_high_memory_paths": repeated_findings,
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
        memory_dir = output_dir.parent / "memory" / "memory"
        findings = self.analysis.get("findings", {}) if isinstance(self.analysis.get("findings", {}), dict) else {}
        totals = self.analysis.get("totals", {}) if isinstance(self.analysis.get("totals", {}), dict) else {}
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        peak_rows = findings.get("peak_memory", []) if isinstance(findings.get("peak_memory", []), list) else []
        stage_rows = findings.get("stage_memory_hotspots", []) if isinstance(findings.get("stage_memory_hotspots", []), list) else []
        growth_rows = findings.get("memory_growth", []) if isinstance(findings.get("memory_growth", []), list) else []
        repeated_rows = findings.get("repeated_high_memory_paths", []) if isinstance(findings.get("repeated_high_memory_paths", []), list) else []
        recommendation_rows = self.analysis.get("recommendations", []) if isinstance(self.analysis.get("recommendations", []), list) else []

        write_json(memory_dir / "240_peak_memory_report.json", {"rows": peak_rows, "totals": totals, "summary": summary})
        write_json(memory_dir / "241_stage_memory_hotspots.json", {"rows": stage_rows, "totals": totals, "summary": summary})
        write_json(memory_dir / "242_memory_growth_report.json", {"rows": growth_rows, "totals": totals, "summary": summary})
        write_json(memory_dir / "243_repeated_high_memory_paths.json", {"rows": repeated_rows, "totals": totals, "summary": summary})
        write_json(memory_dir / "244_memory_recommendations.json", {"rows": recommendation_rows, "summary": summary})

        lines = [
            "# Memory Usage Validation Summary",
            "",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- global_peak_memory_mb: {totals.get('global_peak_memory_mb', 0.0)}",
            f"- finding_count: {summary.get('finding_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Top Findings",
        ]
        top_rows = sorted(
            [*peak_rows, *stage_rows, *growth_rows, *repeated_rows],
            key=lambda row: (
                str(row.get("severity", "INFO")) != "FAIL",
                str(row.get("severity", "INFO")) != "WARNING",
                -_safe_float(row.get("peak_memory_mb", 0.0)),
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
                    + " stage_or_component="
                    + str(row.get("stage_or_component", ""))
                    + " peak_memory_mb="
                    + str(row.get("peak_memory_mb", 0.0))
                    + " growth_mb="
                    + str(row.get("memory_growth_mb", 0.0))
                )
        else:
            lines.append("- no memory pressure issues detected")

        write_text(memory_dir / "245_memory_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/memory/memory/240_peak_memory_report.json",
            "validation_plugins/memory/memory/241_stage_memory_hotspots.json",
            "validation_plugins/memory/memory/242_memory_growth_report.json",
            "validation_plugins/memory/memory/243_repeated_high_memory_paths.json",
            "validation_plugins/memory/memory/244_memory_recommendations.json",
            "validation_plugins/memory/memory/245_memory_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"findings={summary.get('finding_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
