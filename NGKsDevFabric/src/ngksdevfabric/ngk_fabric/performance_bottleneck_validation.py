from __future__ import annotations

from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_DEFAULT_CONFIG = {
    "total_runtime_warning_seconds": 30.0,
    "total_runtime_fail_seconds": 60.0,
    "stage_share_warning_ratio": 0.45,
    "scenario_runtime_warning_seconds": 10.0,
    "repeated_slow_path_threshold": 3,
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


class PerformanceBottleneckValidationPlugin(ValidationPlugin):
    plugin_name = "performance_bottleneck_validation"
    plugin_version = "1.0.0"
    plugin_category = "PERFORMANCE_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        project_root = Path(str(context.get("project_root", "."))).resolve()
        pf = Path(str(context.get("pf", "."))).resolve()

        config_path = (project_root / "performance_validation_config.json").resolve()
        loaded_config = read_json(config_path)
        config = dict(_DEFAULT_CONFIG)
        for key in _DEFAULT_CONFIG:
            if key not in loaded_config:
                continue
            if key == "repeated_slow_path_threshold":
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
            "transport_receipts": read_json(pf / "transport" / "91_transport_receipts.json"),
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
        runtime_seconds: float,
        share_of_total: float,
        threshold_triggered: str,
        historical_recurrence_count: int,
        recommended_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "stage_or_component": stage_or_component,
            "runtime_seconds": round(runtime_seconds, 4),
            "share_of_total": round(share_of_total, 4),
            "threshold_triggered": threshold_triggered,
            "historical_recurrence_count": int(historical_recurrence_count),
            "recommended_actions": list(recommended_actions),
        }

    def run_analysis(self) -> dict[str, Any]:
        config = self.inputs.get("config", {}) if isinstance(self.inputs.get("config", {}), dict) else {}
        total_runtime_warning = _safe_float(config.get("total_runtime_warning_seconds", _DEFAULT_CONFIG["total_runtime_warning_seconds"]))
        total_runtime_fail = _safe_float(config.get("total_runtime_fail_seconds", _DEFAULT_CONFIG["total_runtime_fail_seconds"]))
        stage_share_warning_ratio = _safe_float(config.get("stage_share_warning_ratio", _DEFAULT_CONFIG["stage_share_warning_ratio"]))
        scenario_runtime_warning = _safe_float(config.get("scenario_runtime_warning_seconds", _DEFAULT_CONFIG["scenario_runtime_warning_seconds"]))
        repeated_slow_path_threshold = _safe_int(config.get("repeated_slow_path_threshold", _DEFAULT_CONFIG["repeated_slow_path_threshold"]))

        execution_receipts_payload = self.inputs.get("execution_receipts", {}) if isinstance(self.inputs.get("execution_receipts", {}), dict) else {}
        execution_receipt_rows = [row for row in execution_receipts_payload.get("rows", []) if isinstance(row, dict)]
        completed_receipts = [row for row in execution_receipt_rows if str(row.get("execution_status", "")).upper() == "COMPLETED"]

        scenario_runtime_rows: list[dict[str, Any]] = []
        for row in completed_receipts:
            scenario_runtime_rows.append(
                {
                    "scenario_id": str(row.get("scenario_id", "")),
                    "runtime_seconds": _safe_float(row.get("runtime_seconds", 0.0)),
                    "result_classification": str(row.get("result_classification", "")),
                }
            )
        total_execution_runtime = sum(_safe_float(row.get("runtime_seconds", 0.0)) for row in scenario_runtime_rows)

        stage_runtimes: dict[str, float] = {}
        if total_execution_runtime > 0.0:
            stage_runtimes["execution"] = total_execution_runtime

        execution_stage_summary = self.inputs.get("execution_stage_summary", {}) if isinstance(self.inputs.get("execution_stage_summary", {}), dict) else {}
        stage_map = execution_stage_summary.get("stage_runtime_seconds", {}) if isinstance(execution_stage_summary.get("stage_runtime_seconds", {}), dict) else {}
        for stage_name, value in stage_map.items():
            stage_runtimes[str(stage_name)] = max(stage_runtimes.get(str(stage_name), 0.0), _safe_float(value))

        rerun_summary = self.inputs.get("rerun_summary", {}) if isinstance(self.inputs.get("rerun_summary", {}), dict) else {}
        rerun_runtime = _safe_float(rerun_summary.get("runtime_seconds", 0.0))
        if rerun_runtime > 0.0:
            stage_runtimes["certification_rerun"] = rerun_runtime

        transport_receipts_payload = self.inputs.get("transport_receipts", {}) if isinstance(self.inputs.get("transport_receipts", {}), dict) else {}
        transport_receipt_rows = [row for row in transport_receipts_payload.get("receipts", []) if isinstance(row, dict)]
        transport_runtime = sum(_safe_float(row.get("runtime_seconds", 0.0)) for row in transport_receipt_rows)
        if transport_runtime > 0.0:
            stage_runtimes["transport"] = transport_runtime

        total_runtime = sum(value for value in stage_runtimes.values() if value > 0.0)
        if total_runtime <= 0.0:
            total_runtime = total_execution_runtime

        watch_payload = self.inputs.get("watchlist", {}) if isinstance(self.inputs.get("watchlist", {}), dict) else {}
        watch_rows = [row for row in watch_payload.get("rows", []) if isinstance(row, dict)]
        watch_by_component = {
            str(row.get("component", "")).strip(): str(row.get("watch_class", "NORMAL")).upper()
            for row in watch_rows
            if str(row.get("component", "")).strip()
        }

        component_ctx_payload = self.inputs.get("component_history_context", {}) if isinstance(self.inputs.get("component_history_context", {}), dict) else {}
        component_ctx_rows = [row for row in component_ctx_payload.get("rows", []) if isinstance(row, dict)]

        total_runtime_findings: list[dict[str, Any]] = []
        stage_hotspot_findings: list[dict[str, Any]] = []
        scenario_hotspot_findings: list[dict[str, Any]] = []
        repeated_slow_path_findings: list[dict[str, Any]] = []

        if total_runtime >= total_runtime_warning:
            severity = "FAIL" if total_runtime >= total_runtime_fail else "WARNING"
            total_runtime_findings.append(
                self._finding(
                    finding_id="TOTAL_RUNTIME_BOTTLENECK_total",
                    severity=severity,
                    stage_or_component="pipeline_total",
                    runtime_seconds=total_runtime,
                    share_of_total=1.0,
                    threshold_triggered=(
                        f"total_runtime_fail_seconds:{total_runtime_fail}"
                        if severity == "FAIL"
                        else f"total_runtime_warning_seconds:{total_runtime_warning}"
                    ),
                    historical_recurrence_count=0,
                    recommended_actions=[
                        "profile this stage with finer-grained instrumentation",
                        "move noncritical work out of the main path",
                        "cache repeated expensive inputs",
                    ],
                )
            )

        active_stages = [(name, runtime) for name, runtime in stage_runtimes.items() if runtime > 0.0]
        if len(active_stages) >= 2 and total_runtime > 0.0:
            ordered_stages = sorted(active_stages, key=lambda item: (-item[1], item[0]))
            dominant_stage, dominant_runtime = ordered_stages[0]
            dominant_share = _share(dominant_runtime, total_runtime)

            for stage_name, stage_runtime in ordered_stages:
                stage_share = _share(stage_runtime, total_runtime)
                if stage_share >= stage_share_warning_ratio:
                    stage_hotspot_findings.append(
                        self._finding(
                            finding_id=f"STAGE_HOTSPOT_{_slug(stage_name)}",
                            severity="WARNING",
                            stage_or_component=stage_name,
                            runtime_seconds=stage_runtime,
                            share_of_total=stage_share,
                            threshold_triggered=f"stage_share_warning_ratio:{stage_share_warning_ratio}",
                            historical_recurrence_count=0,
                            recommended_actions=[
                                "split this stage into substeps",
                                "cache repeated expensive inputs",
                                "profile this stage with finer-grained instrumentation",
                            ],
                        )
                    )

            if dominant_share >= min(0.95, stage_share_warning_ratio * 1.7):
                stage_hotspot_findings.append(
                    self._finding(
                        finding_id=f"EXECUTION_IMBALANCE_WARNING_{_slug(dominant_stage)}",
                        severity="WARNING",
                        stage_or_component=dominant_stage,
                        runtime_seconds=dominant_runtime,
                        share_of_total=dominant_share,
                        threshold_triggered=f"stage_share_warning_ratio:{stage_share_warning_ratio}",
                        historical_recurrence_count=0,
                        recommended_actions=[
                            "split this stage into substeps",
                            "reduce nested validation work in this stage",
                            "move noncritical work out of the main path",
                        ],
                    )
                )

        if total_execution_runtime > 0.0:
            ordered_scenarios = sorted(scenario_runtime_rows, key=lambda item: (-_safe_float(item.get("runtime_seconds", 0.0)), str(item.get("scenario_id", ""))))
            for row in ordered_scenarios:
                runtime = _safe_float(row.get("runtime_seconds", 0.0))
                if runtime >= scenario_runtime_warning:
                    severity = "FAIL" if runtime >= scenario_runtime_warning * 2.0 else "WARNING"
                    scenario_hotspot_findings.append(
                        self._finding(
                            finding_id=f"SCENARIO_PERFORMANCE_HOTSPOT_{_slug(str(row.get('scenario_id', '')))}",
                            severity=severity,
                            stage_or_component=str(row.get("scenario_id", "")),
                            runtime_seconds=runtime,
                            share_of_total=_share(runtime, total_execution_runtime),
                            threshold_triggered=f"scenario_runtime_warning_seconds:{scenario_runtime_warning}",
                            historical_recurrence_count=0,
                            recommended_actions=[
                                "reduce nested validation work in this scenario",
                                "cache repeated expensive inputs",
                                "run this analysis only under ENTERPRISE profile if appropriate",
                            ],
                        )
                    )

        for row in component_ctx_rows:
            component = str(row.get("component", "")).strip()
            if not component:
                continue
            recurrence = max(_safe_int(row.get("slow_path_recurrence_count", 0)), _safe_int(row.get("total_regression_occurrences", 0)))
            mean_runtime = _safe_float(row.get("mean_runtime_seconds", row.get("runtime_seconds", 0.0)))
            watch_class = watch_by_component.get(component, "NORMAL")
            if recurrence >= repeated_slow_path_threshold and (mean_runtime >= scenario_runtime_warning or watch_class in {"HOT", "CRITICAL"}):
                repeated_slow_path_findings.append(
                    self._finding(
                        finding_id=f"REPEATED_SLOW_PATH_{_slug(component)}",
                        severity="FAIL" if recurrence >= repeated_slow_path_threshold * 2 else "WARNING",
                        stage_or_component=component,
                        runtime_seconds=mean_runtime,
                        share_of_total=_share(mean_runtime, total_runtime),
                        threshold_triggered=f"repeated_slow_path_threshold:{repeated_slow_path_threshold}",
                        historical_recurrence_count=recurrence,
                        recommended_actions=[
                            "profile this stage with finer-grained instrumentation",
                            "cache repeated expensive inputs",
                            "move noncritical work out of the main path",
                        ],
                    )
                )

        recommendations: list[dict[str, Any]] = []
        all_findings = [
            *total_runtime_findings,
            *stage_hotspot_findings,
            *scenario_hotspot_findings,
            *repeated_slow_path_findings,
        ]
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
                "total_runtime_seconds": round(total_runtime, 4),
                "total_execution_runtime_seconds": round(total_execution_runtime, 4),
                "stage_runtimes": {key: round(value, 4) for key, value in sorted(stage_runtimes.items())},
            },
            "findings": {
                "total_runtime": total_runtime_findings,
                "stage_hotspots": stage_hotspot_findings,
                "scenario_hotspots": scenario_hotspot_findings,
                "repeated_slow_paths": repeated_slow_path_findings,
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
        performance_dir = output_dir.parent / "performance" / "performance"
        findings = self.analysis.get("findings", {}) if isinstance(self.analysis.get("findings", {}), dict) else {}
        totals = self.analysis.get("totals", {}) if isinstance(self.analysis.get("totals", {}), dict) else {}
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        total_runtime_rows = findings.get("total_runtime", []) if isinstance(findings.get("total_runtime", []), list) else []
        stage_rows = findings.get("stage_hotspots", []) if isinstance(findings.get("stage_hotspots", []), list) else []
        scenario_rows = findings.get("scenario_hotspots", []) if isinstance(findings.get("scenario_hotspots", []), list) else []
        repeated_rows = findings.get("repeated_slow_paths", []) if isinstance(findings.get("repeated_slow_paths", []), list) else []
        recommendation_rows = self.analysis.get("recommendations", []) if isinstance(self.analysis.get("recommendations", []), list) else []

        write_json(performance_dir / "230_total_runtime_report.json", {"rows": total_runtime_rows, "totals": totals, "summary": summary})
        write_json(performance_dir / "231_stage_hotspots.json", {"rows": stage_rows, "totals": totals, "summary": summary})
        write_json(performance_dir / "232_scenario_hotspots.json", {"rows": scenario_rows, "totals": totals, "summary": summary})
        write_json(performance_dir / "233_repeated_slow_paths.json", {"rows": repeated_rows, "totals": totals, "summary": summary})
        write_json(performance_dir / "234_performance_recommendations.json", {"rows": recommendation_rows, "summary": summary})

        lines = [
            "# Performance Bottleneck Validation Summary",
            "",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- total_runtime_seconds: {totals.get('total_runtime_seconds', 0.0)}",
            f"- finding_count: {summary.get('finding_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Top Findings",
        ]
        top_rows = sorted(
            [*total_runtime_rows, *stage_rows, *scenario_rows, *repeated_rows],
            key=lambda row: (
                str(row.get("severity", "INFO")) != "FAIL",
                str(row.get("severity", "INFO")) != "WARNING",
                -_safe_float(row.get("runtime_seconds", 0.0)),
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
                    + " runtime_seconds="
                    + str(row.get("runtime_seconds", 0.0))
                    + " share="
                    + str(row.get("share_of_total", 0.0))
                )
        else:
            lines.append("- no performance bottlenecks detected")

        write_text(performance_dir / "235_performance_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/performance/performance/230_total_runtime_report.json",
            "validation_plugins/performance/performance/231_stage_hotspots.json",
            "validation_plugins/performance/performance/232_scenario_hotspots.json",
            "validation_plugins/performance/performance/233_repeated_slow_paths.json",
            "validation_plugins/performance/performance/234_performance_recommendations.json",
            "validation_plugins/performance/performance/235_performance_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"findings={summary.get('finding_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
