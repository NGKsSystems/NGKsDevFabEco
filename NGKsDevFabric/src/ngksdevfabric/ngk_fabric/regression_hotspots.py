from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCENARIO_METRIC_WEIGHTS: dict[str, float] = {
    "diagnostic_score": 0.40,
    "detection_accuracy": 0.20,
    "root_cause_accuracy": 0.15,
    "ownership_accuracy": 0.15,
    "remediation_quality": 0.05,
    "proof_quality": 0.05,
}

_AGGREGATE_METRIC_WEIGHTS: dict[str, float] = {
    "average_diagnostic_score": 0.40,
    "average_detection_accuracy": 0.20,
    "average_root_cause_accuracy": 0.15,
    "average_component_ownership_accuracy": 0.15,
    "average_remediation_quality": 0.05,
    "average_proof_quality": 0.05,
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _scenario_weight(row: dict[str, Any]) -> float:
    # Scenarios expected to PASS are weighted slightly higher because regressions there
    # are typically more user-facing and operationally expensive.
    expected_gate = str(row.get("expected_gate", "")).upper()
    return 1.25 if expected_gate == "PASS" else 1.0


def analyze_regression_hotspots(
    *,
    pf: Path,
    scenario_diff_rows: list[dict[str, Any]],
    aggregate_diff: dict[str, Any],
    classification: str,
) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    scenario_rows: list[dict[str, Any]] = []
    for row in scenario_diff_rows:
        if row.get("status") == "missing":
            continue

        drops = {
            "diagnostic_score": max(0.0, -_safe_float(row.get("delta_diagnostic_score", 0.0))),
            "detection_accuracy": max(0.0, -_safe_float(row.get("delta_detection_accuracy", 0.0))),
            "root_cause_accuracy": max(0.0, -_safe_float(row.get("delta_root_cause_accuracy", 0.0))),
            "ownership_accuracy": max(0.0, -_safe_float(row.get("delta_ownership_accuracy", 0.0))),
            "remediation_quality": max(0.0, -_safe_float(row.get("delta_remediation_quality", 0.0))),
            "proof_quality": max(0.0, -_safe_float(row.get("delta_proof_quality", 0.0))),
        }
        weighted_drop = sum(_SCENARIO_METRIC_WEIGHTS[key] * value for key, value in drops.items())
        scenario_weight = _scenario_weight(row)
        severity_score = round(weighted_drop * scenario_weight, 6)
        normalized_severity = round(min(1.0, severity_score / 0.25), 6)

        scenario_rows.append(
            {
                "scenario_id": str(row.get("scenario_id", "")),
                "scenario_name": str(row.get("scenario_name", "")),
                "expected_gate": str(row.get("expected_gate", "")),
                "baseline_score": round(_safe_float(row.get("baseline_diagnostic_score", 0.0)), 4),
                "current_score": round(_safe_float(row.get("current_diagnostic_score", 0.0)), 4),
                "delta": round(_safe_float(row.get("delta_diagnostic_score", 0.0)), 4),
                "metric_drops": {key: round(value, 6) for key, value in drops.items()},
                "scenario_weight": scenario_weight,
                "severity_score": severity_score,
                "normalized_severity": normalized_severity,
            }
        )

    scenario_rows = sorted(
        scenario_rows,
        key=lambda item: (
            -_safe_float(item.get("severity_score", 0.0)),
            str(item.get("scenario_id", "")),
        ),
    )
    for index, row in enumerate(scenario_rows, start=1):
        row["rank"] = index

    metric_rows: list[dict[str, Any]] = []
    for metric_name, metric_payload in aggregate_diff.items():
        delta = _safe_float(metric_payload.get("delta", 0.0)) if isinstance(metric_payload, dict) else 0.0
        drop_magnitude = max(0.0, -delta)
        metric_weight = _AGGREGATE_METRIC_WEIGHTS.get(metric_name, 0.05)
        severity_score = round(metric_weight * drop_magnitude, 6)
        metric_rows.append(
            {
                "metric": metric_name,
                "baseline": round(_safe_float(metric_payload.get("baseline", 0.0)), 4) if isinstance(metric_payload, dict) else 0.0,
                "current": round(_safe_float(metric_payload.get("current", 0.0)), 4) if isinstance(metric_payload, dict) else 0.0,
                "delta": round(delta, 4),
                "drop_magnitude": round(drop_magnitude, 6),
                "metric_weight": metric_weight,
                "severity_score": severity_score,
            }
        )

    metric_rows = sorted(
        metric_rows,
        key=lambda item: (
            -_safe_float(item.get("severity_score", 0.0)),
            str(item.get("metric", "")),
        ),
    )
    for index, row in enumerate(metric_rows, start=1):
        row["rank"] = index

    regressed_scenarios = [row for row in scenario_rows if _safe_float(row.get("severity_score", 0.0)) > 0.0]
    average_regression_magnitude = (
        round(sum(max(0.0, -_safe_float(row.get("delta", 0.0))) for row in regressed_scenarios) / len(regressed_scenarios), 6)
        if regressed_scenarios
        else 0.0
    )
    largest_single = regressed_scenarios[0] if regressed_scenarios else {}

    aggregate_impact = {
        "classification": classification,
        "total_regressed_scenarios": len(regressed_scenarios),
        "average_regression_magnitude": average_regression_magnitude,
        "largest_single_regression": {
            "scenario_id": str(largest_single.get("scenario_id", "none")),
            "severity_score": round(_safe_float(largest_single.get("severity_score", 0.0)), 6),
            "delta": round(_safe_float(largest_single.get("delta", 0.0)), 4),
        },
        "top_metric_regression": {
            "metric": str(metric_rows[0].get("metric", "none")) if metric_rows else "none",
            "severity_score": round(_safe_float(metric_rows[0].get("severity_score", 0.0)), 6) if metric_rows else 0.0,
            "delta": round(_safe_float(metric_rows[0].get("delta", 0.0)), 4) if metric_rows else 0.0,
        },
    }

    hotspot_payload = {
        "severity_model": {
            "scenario_metric_weights": _SCENARIO_METRIC_WEIGHTS,
            "aggregate_metric_weights": _AGGREGATE_METRIC_WEIGHTS,
            "scenario_weight_policy": "expected_gate_PASS=1.25_else_1.0",
            "scenario_severity_formula": "scenario_weight * sum(metric_weight * max(0, -delta_metric))",
            "scenario_normalized_severity_formula": "min(1.0, severity_score / 0.25)",
            "metric_severity_formula": "metric_weight * max(0, -delta)",
        },
        "aggregate_impact": aggregate_impact,
        "top_scenarios": scenario_rows[:5],
        "top_metrics": metric_rows[:5],
    }

    _write_json(out_dir / "09_regression_hotspots.json", hotspot_payload)
    _write_json(out_dir / "10_scenario_regression_ranking.json", {"rows": scenario_rows})
    _write_json(out_dir / "11_metric_regression_ranking.json", {"rows": metric_rows})

    summary_lines = [
        "# Regression Hotspot Summary",
        "",
        f"- classification: {classification}",
        f"- total_regressed_scenarios: {aggregate_impact['total_regressed_scenarios']}",
        f"- average_regression_magnitude: {aggregate_impact['average_regression_magnitude']}",
        f"- largest_single_regression: {aggregate_impact['largest_single_regression']['scenario_id']} (delta={aggregate_impact['largest_single_regression']['delta']})",
        f"- top_metric_regression: {aggregate_impact['top_metric_regression']['metric']} (delta={aggregate_impact['top_metric_regression']['delta']})",
        "",
        "## Top Scenario Hotspots",
    ]
    if scenario_rows:
        for row in scenario_rows[:5]:
            summary_lines.append(
                f"- rank {row['rank']}: {row['scenario_id']} delta={row['delta']} severity={row['severity_score']}"
            )
    else:
        summary_lines.append("- none")

    summary_lines.append("")
    summary_lines.append("## Top Metric Hotspots")
    if metric_rows:
        for row in metric_rows[:5]:
            summary_lines.append(
                f"- rank {row['rank']}: {row['metric']} delta={row['delta']} severity={row['severity_score']}"
            )
    else:
        summary_lines.append("- none")

    _write_text(out_dir / "12_hotspot_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "aggregate_impact": aggregate_impact,
        "top_scenario": scenario_rows[0] if scenario_rows else {},
        "top_metric": metric_rows[0] if metric_rows else {},
        "scenario_rows": scenario_rows,
        "metric_rows": metric_rows,
        "artifacts": [
            "hotspots/09_regression_hotspots.json",
            "hotspots/10_scenario_regression_ranking.json",
            "hotspots/11_metric_regression_ranking.json",
            "hotspots/12_hotspot_summary.md",
        ],
    }
