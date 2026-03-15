from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_METRIC_CRITICALITY: dict[str, int] = {
    "diagnostic_score": 5,
    "detection_accuracy": 5,
    "root_cause_accuracy": 4,
    "ownership_accuracy": 4,
    "remediation_quality": 3,
    "proof_quality": 2,
}

_METRIC_COMPONENT_HINTS: dict[str, str] = {
    "diagnostic_score": "diagnostic scoring pipeline",
    "detection_accuracy": "diagnostic detection evaluator",
    "root_cause_accuracy": "root cause inference engine",
    "ownership_accuracy": "component ownership mapper",
    "remediation_quality": "remediation quality evaluator",
    "proof_quality": "proof quality validator",
}

_METRIC_IMPACT_CONTEXT: dict[str, str] = {
    "diagnostic_score": "diagnostic score regression reduces overall certification confidence",
    "detection_accuracy": "detection accuracy regression reduces diagnostic reliability",
    "root_cause_accuracy": "root cause accuracy regression increases misdiagnosis risk",
    "ownership_accuracy": "ownership accuracy regression degrades component attribution quality",
    "remediation_quality": "remediation quality regression weakens fix recommendations",
    "proof_quality": "proof quality regression reduces evidence trust",
}

_COMPONENT_ACTIONS: dict[str, str] = {
    "dependency graph resolver": "inspect dependency contract resolution logic",
    "component ownership mapper": "verify component ownership mapping rules",
    "diagnostic scoring pipeline": "verify score normalization and weighted aggregation logic",
    "scenario contract parser": "check scenario contract parsing and validation logic",
    "runtime host policy parser": "review host policy parsing and route gating logic",
    "diagnostic detection evaluator": "inspect detection scoring calibration and thresholding",
    "root cause inference engine": "review root cause inference scoring inputs and weighting",
    "remediation quality evaluator": "inspect remediation quality rubric and score extraction",
    "proof quality validator": "verify proof evidence extraction and validation scoring",
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


def _scenario_component_hint(scenario_id: str, dominant_metric: str) -> str:
    sid = scenario_id.lower()
    if "dependency" in sid:
        return "dependency graph resolver"
    if "ownership" in sid or "owner" in sid:
        return "component ownership mapper"
    if "diagnostic" in sid or "baseline_pass" in sid or "score" in sid:
        return "diagnostic scoring pipeline"
    if "config" in sid or "parse" in sid or "contract" in sid:
        return "scenario contract parser"
    if "host" in sid or "runtime" in sid:
        return "runtime host policy parser"
    return _METRIC_COMPONENT_HINTS.get(dominant_metric, "diagnostic scoring pipeline")


def _dominant_metric(metric_drops: dict[str, Any]) -> str:
    if not metric_drops:
        return "diagnostic_score"
    ranked = sorted(
        [(str(k), _safe_float(v)) for k, v in metric_drops.items()],
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[0][0] if ranked else "diagnostic_score"


def generate_remediation_guidance(
    *,
    pf: Path,
    classification: str,
    hotspot_analysis: dict[str, Any],
) -> dict[str, Any]:
    out_dir = pf / "hotspots"
    scenario_rows = hotspot_analysis.get("scenario_rows", [])
    if not isinstance(scenario_rows, list):
        scenario_rows = []

    guidance_entries: list[dict[str, Any]] = []
    for row in scenario_rows:
        if not isinstance(row, dict):
            continue

        severity = _safe_float(row.get("severity_score", 0.0))
        if severity <= 0.0:
            continue

        metric_drops = row.get("metric_drops", {}) if isinstance(row.get("metric_drops"), dict) else {}
        dominant_metric = _dominant_metric(metric_drops)
        scenario_id = str(row.get("scenario_id", ""))
        likely_component = _scenario_component_hint(scenario_id, dominant_metric)

        metric_context = _METRIC_IMPACT_CONTEXT.get(
            dominant_metric,
            "regression in this metric decreases certification confidence",
        )
        suggested_investigation = _COMPONENT_ACTIONS.get(
            likely_component,
            "review comparison inputs and scoring pipeline assumptions",
        )

        hotspot_rank = int(row.get("rank", len(guidance_entries) + 1) or (len(guidance_entries) + 1))
        metric_criticality = _METRIC_CRITICALITY.get(dominant_metric, 1)
        scenario_criticality = 2 if str(row.get("expected_gate", "")).upper() == "PASS" else 1

        guidance_entries.append(
            {
                "scenario_id": scenario_id,
                "metric": dominant_metric,
                "delta": round(_safe_float(row.get("delta", 0.0)), 4),
                "severity_score": round(severity, 6),
                "priority_rank": hotspot_rank,
                "hotspot_rank": hotspot_rank,
                "metric_criticality": metric_criticality,
                "scenario_criticality": scenario_criticality,
                "likely_component": likely_component,
                "suggested_investigation": suggested_investigation,
                "explanation": metric_context,
            }
        )

    guidance_entries = sorted(
        guidance_entries,
        key=lambda item: (
            int(item.get("priority_rank", 999999)),
            -_safe_float(item.get("severity_score", 0.0)),
            str(item.get("scenario_id", "")),
        ),
    )
    for index, entry in enumerate(guidance_entries, start=1):
        entry["priority_rank"] = index

    summary_payload = {
        "classification": classification,
        "guidance_count": len(guidance_entries),
        "top_priority": guidance_entries[0] if guidance_entries else {},
        "model": {
            "base_ordering": "hotspot_rank",
            "priority_rank_formula": "priority_rank = hotspot_rank (stable deterministic ordering)",
            "supporting_signals": ["metric_criticality", "scenario_criticality", "severity_score"],
            "component_hint_strategy": "scenario_id_keyword_mapping_then_metric_fallback",
        },
    }

    _write_json(
        out_dir / "13_remediation_guidance.json",
        {
            "summary": summary_payload,
            "entries": guidance_entries,
        },
    )
    _write_json(out_dir / "14_remediation_priority_list.json", {"entries": guidance_entries})

    summary_lines = [
        "# Remediation Guidance Summary",
        "",
        f"- classification: {classification}",
        f"- guidance_count: {len(guidance_entries)}",
    ]
    if guidance_entries:
        top = guidance_entries[0]
        summary_lines.append(
            f"- top_priority: {top.get('scenario_id', 'none')} metric={top.get('metric', '')} severity={top.get('severity_score', 0.0)}"
        )
    else:
        summary_lines.append("- top_priority: none")

    summary_lines.append("")
    summary_lines.append("## Priority Fixes")
    if guidance_entries:
        for entry in guidance_entries[:10]:
            summary_lines.extend(
                [
                    f"{entry['priority_rank']}. scenario={entry.get('scenario_id', '')}",
                    f"   metric={entry.get('metric', '')}",
                    f"   impact_delta={entry.get('delta', 0.0)}",
                    f"   severity_score={entry.get('severity_score', 0.0)}",
                    f"   likely_component={entry.get('likely_component', '')}",
                    f"   suggested_investigation={entry.get('suggested_investigation', '')}",
                    f"   explanation={entry.get('explanation', '')}",
                ]
            )
    else:
        summary_lines.append("- no remediation required for current run")

    _write_text(out_dir / "15_remediation_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "summary": summary_payload,
        "top_priority": guidance_entries[0] if guidance_entries else {},
        "entries": guidance_entries,
        "artifacts": [
            "hotspots/13_remediation_guidance.json",
            "hotspots/14_remediation_priority_list.json",
            "hotspots/15_remediation_summary.md",
        ],
    }
