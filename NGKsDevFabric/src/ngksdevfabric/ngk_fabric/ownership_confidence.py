from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIDENCE_THRESHOLDS = {
    "HIGH_CONFIDENCE": 0.75,
    "MEDIUM_CONFIDENCE": 0.50,
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


def _normalized(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


def _component_mapping_strength(scenario_id: str, likely_component: str) -> float:
    sid = scenario_id.lower()
    lc = likely_component.lower()

    if "dependency" in sid and "dependency" in lc:
        return 1.0
    if ("ownership" in sid or "owner" in sid) and "ownership" in lc:
        return 1.0
    if ("diagnostic" in sid or "baseline_pass" in sid or "score" in sid) and "scoring" in lc:
        return 0.9
    if ("config" in sid or "contract" in sid or "parse" in sid) and ("parser" in lc or "contract" in lc):
        return 0.85
    return 0.6


def _confidence_level(score: float) -> str:
    if score >= _CONFIDENCE_THRESHOLDS["HIGH_CONFIDENCE"]:
        return "HIGH_CONFIDENCE"
    if score >= _CONFIDENCE_THRESHOLDS["MEDIUM_CONFIDENCE"]:
        return "MEDIUM_CONFIDENCE"
    return "LOW_CONFIDENCE"


def generate_ownership_confidence_evidence(
    *,
    pf: Path,
    classification: str,
    remediation_guidance: dict[str, Any],
    hotspot_analysis: dict[str, Any],
) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    remediation_entries = remediation_guidance.get("entries", [])
    if not isinstance(remediation_entries, list):
        remediation_entries = []

    scenario_rows = hotspot_analysis.get("scenario_rows", [])
    if not isinstance(scenario_rows, list):
        scenario_rows = []
    metric_rows = hotspot_analysis.get("metric_rows", [])
    if not isinstance(metric_rows, list):
        metric_rows = []

    scenario_index = {
        str(row.get("scenario_id", "")): row
        for row in scenario_rows
        if isinstance(row, dict) and str(row.get("scenario_id", ""))
    }
    metric_index = {
        str(row.get("metric", "")): row
        for row in metric_rows
        if isinstance(row, dict) and str(row.get("metric", ""))
    }

    ownership_entries: list[dict[str, Any]] = []
    evidence_links: list[dict[str, Any]] = []

    for entry in remediation_entries:
        if not isinstance(entry, dict):
            continue

        scenario_id = str(entry.get("scenario_id", ""))
        metric = str(entry.get("metric", ""))
        likely_component = str(entry.get("likely_component", ""))
        priority_rank = int(entry.get("priority_rank", len(ownership_entries) + 1) or (len(ownership_entries) + 1))
        severity_score = _safe_float(entry.get("severity_score", 0.0))
        metric_delta = _safe_float(entry.get("delta", 0.0))

        scenario_row = scenario_index.get(scenario_id, {})
        metric_row = metric_index.get(metric, {})

        metric_signal_strength = _normalized(abs(metric_delta), 0.20)
        scenario_signal_strength = _normalized(severity_score, 0.25)
        component_mapping_strength = _component_mapping_strength(scenario_id, likely_component)

        scenario_confirm = bool(scenario_row)
        metric_confirm = bool(metric_row)
        delta_sign_confirm = metric_delta <= 0.0
        cross_artifact_confirmation = 1.0 if (scenario_confirm and metric_confirm and delta_sign_confirm) else 0.5

        confidence_score = round(
            0.35 * metric_signal_strength
            + 0.35 * scenario_signal_strength
            + 0.20 * component_mapping_strength
            + 0.10 * cross_artifact_confirmation,
            6,
        )
        confidence_level = _confidence_level(confidence_score)

        evidence_sources = {
            "scenario_id": scenario_id,
            "metric": metric,
            "severity_score": round(severity_score, 6),
            "metric_delta": round(metric_delta, 4),
            "scenario_rank": int(scenario_row.get("rank", 0) or 0),
            "metric_rank": int(metric_row.get("rank", 0) or 0),
            "artifact_source": [
                "hotspots/10_scenario_regression_ranking.json",
                "hotspots/11_metric_regression_ranking.json",
                "hotspots/13_remediation_guidance.json",
                "baseline_matrix.json",
                "diagnostic_metrics.json",
            ],
            "component_mapping_strength": round(component_mapping_strength, 6),
            "metric_signal_strength": round(metric_signal_strength, 6),
            "scenario_signal_strength": round(scenario_signal_strength, 6),
            "cross_artifact_confirmation": round(cross_artifact_confirmation, 6),
        }

        ownership_entry = {
            "scenario_id": scenario_id,
            "metric": metric,
            "severity_score": round(severity_score, 6),
            "priority_rank": priority_rank,
            "likely_component": likely_component,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "evidence_sources": evidence_sources,
            "evidence_artifacts": evidence_sources["artifact_source"],
        }
        ownership_entries.append(ownership_entry)

        evidence_links.append(
            {
                "scenario_id": scenario_id,
                "metric": metric,
                "priority_rank": priority_rank,
                "artifact_links": evidence_sources["artifact_source"],
                "supporting_rows": {
                    "scenario_ranking_row": scenario_row,
                    "metric_ranking_row": metric_row,
                },
            }
        )

    ownership_entries = sorted(
        ownership_entries,
        key=lambda item: (
            int(item.get("priority_rank", 999999)),
            -_safe_float(item.get("confidence_score", 0.0)),
            str(item.get("scenario_id", "")),
        ),
    )
    for index, item in enumerate(ownership_entries, start=1):
        item["priority_rank"] = index

    summary_payload = {
        "classification": classification,
        "entry_count": len(ownership_entries),
        "top_entry": ownership_entries[0] if ownership_entries else {},
        "confidence_thresholds": {
            "HIGH_CONFIDENCE": ">=0.75",
            "MEDIUM_CONFIDENCE": "0.50-0.74",
            "LOW_CONFIDENCE": "<0.50",
        },
        "confidence_formula": {
            "metric_signal_weight": 0.35,
            "scenario_signal_weight": 0.35,
            "component_mapping_weight": 0.20,
            "cross_artifact_confirmation_weight": 0.10,
        },
    }

    _write_json(
        out_dir / "16_ownership_confidence.json",
        {
            "summary": summary_payload,
            "entries": ownership_entries,
        },
    )
    _write_json(
        out_dir / "17_evidence_links.json",
        {
            "entries": evidence_links,
        },
    )

    lines = [
        "# Remediation Evidence Summary",
        "",
        f"- classification: {classification}",
        f"- entry_count: {len(ownership_entries)}",
    ]
    if ownership_entries:
        top = ownership_entries[0]
        lines.append(
            f"- top_entry: scenario={top.get('scenario_id', '')} metric={top.get('metric', '')} confidence={top.get('confidence_score', 0.0)}"
        )
    else:
        lines.append("- top_entry: none")

    lines.append("")
    lines.append("## Ownership Confidence")
    if ownership_entries:
        for item in ownership_entries[:10]:
            lines.extend(
                [
                    f"- rank {item.get('priority_rank', 0)} scenario={item.get('scenario_id', '')}",
                    f"  component={item.get('likely_component', '')}",
                    f"  confidence={item.get('confidence_score', 0.0)} ({item.get('confidence_level', '')})",
                    f"  evidence_artifacts={', '.join(item.get('evidence_artifacts', []))}",
                ]
            )
    else:
        lines.append("- no evidence-linked remediation entries")

    _write_text(out_dir / "18_remediation_evidence_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": summary_payload,
        "entries": ownership_entries,
        "artifacts": [
            "hotspots/16_ownership_confidence.json",
            "hotspots/17_evidence_links.json",
            "hotspots/18_remediation_evidence_summary.md",
        ],
    }
