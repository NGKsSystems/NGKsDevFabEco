from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ACTION_POLICY_THRESHOLDS = {
    "AUTO_ASSIGN_SAFE_MIN_CONFIDENCE": 0.75,
    "HUMAN_REVIEW_REQUIRED_MIN_CONFIDENCE": 0.50,
    "STRONG_EVIDENCE_MIN_ARTIFACTS": 4,
    "STRONG_EVIDENCE_MIN_CONFIRMATION": 0.50,
}

_POLICY_ACTIONS = {
    "AUTO_ASSIGN_SAFE": "assign issue to component owner and begin remediation",
    "HUMAN_REVIEW_REQUIRED": "route to engineering triage for confirmation",
    "INSUFFICIENT_CONFIDENCE": "investigate regression manually before assignment",
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


def _is_strong_evidence(entry: dict[str, Any]) -> bool:
    artifacts = entry.get("evidence_artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    confirmation = _safe_float((entry.get("evidence_sources", {}) or {}).get("cross_artifact_confirmation", 0.0))
    return len(artifacts) >= _ACTION_POLICY_THRESHOLDS["STRONG_EVIDENCE_MIN_ARTIFACTS"] and confirmation >= _ACTION_POLICY_THRESHOLDS["STRONG_EVIDENCE_MIN_CONFIRMATION"]


def _classify_policy(entry: dict[str, Any]) -> str:
    confidence_score = _safe_float(entry.get("confidence_score", 0.0))
    strong_evidence = _is_strong_evidence(entry)

    if confidence_score >= _ACTION_POLICY_THRESHOLDS["AUTO_ASSIGN_SAFE_MIN_CONFIDENCE"] and strong_evidence:
        return "AUTO_ASSIGN_SAFE"
    if confidence_score >= _ACTION_POLICY_THRESHOLDS["HUMAN_REVIEW_REQUIRED_MIN_CONFIDENCE"]:
        return "HUMAN_REVIEW_REQUIRED"
    return "INSUFFICIENT_CONFIDENCE"


def _resolve_assignee(entry: dict[str, Any], action_policy: str) -> tuple[str, str]:
    primary = str(entry.get("primary_assignee", "")).strip()
    fallback = str(entry.get("fallback_assignee", "")).strip()
    inferred = str(entry.get("ownership_inference_assignee", "")).strip()
    escalation = str(entry.get("escalation_owner", "")).strip()

    if action_policy == "HUMAN_REVIEW_REQUIRED" and escalation:
        return escalation, "escalation_owner_human_review"
    if primary:
        return primary, "primary_assignee"
    if fallback:
        return fallback, "fallback_assignee"
    if inferred:
        return inferred, "ownership_inference_assignee"
    if escalation:
        return escalation, "escalation_owner_default"
    return "", "unresolved"


def generate_assignment_safety_operator_actions(
    *,
    pf: Path,
    classification: str,
    ownership_confidence: dict[str, Any],
) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    ownership_entries = ownership_confidence.get("entries", [])
    if not isinstance(ownership_entries, list):
        ownership_entries = []

    policy_entries: list[dict[str, Any]] = []
    for entry in ownership_entries:
        if not isinstance(entry, dict):
            continue

        action_policy = _classify_policy(entry)
        resolved_assignee, resolution_source = _resolve_assignee(entry, action_policy)
        policy_entry = {
            "scenario_id": str(entry.get("scenario_id", "")),
            "metric": str(entry.get("metric", "")),
            "severity_score": round(_safe_float(entry.get("severity_score", 0.0)), 6),
            "priority_rank": int(entry.get("priority_rank", len(policy_entries) + 1) or (len(policy_entries) + 1)),
            "likely_component": str(entry.get("likely_component", "")),
            "team": str(entry.get("team", "")),
            "primary_assignee": str(entry.get("primary_assignee", "")),
            "fallback_assignee": str(entry.get("fallback_assignee", "")),
            "escalation_owner": str(entry.get("escalation_owner", "")),
            "ownership_inference_assignee": str(entry.get("ownership_inference_assignee", "")),
            "resolved_assignee": resolved_assignee,
            "assignee_resolution_source": resolution_source,
            "mapping_source": str(entry.get("mapping_source", "inferred")),
            "confidence_score": round(_safe_float(entry.get("confidence_score", 0.0)), 6),
            "confidence_level": str(entry.get("confidence_level", "LOW_CONFIDENCE")),
            "action_policy": action_policy,
            "recommended_operator_action": _POLICY_ACTIONS[action_policy],
        }
        policy_entries.append(policy_entry)

    policy_entries = sorted(
        policy_entries,
        key=lambda item: (
            int(item.get("priority_rank", 999999)),
            -_safe_float(item.get("confidence_score", 0.0)),
            str(item.get("scenario_id", "")),
        ),
    )
    for index, item in enumerate(policy_entries, start=1):
        item["priority_rank"] = index

    policy_counts = {
        "AUTO_ASSIGN_SAFE": sum(1 for item in policy_entries if item.get("action_policy") == "AUTO_ASSIGN_SAFE"),
        "HUMAN_REVIEW_REQUIRED": sum(1 for item in policy_entries if item.get("action_policy") == "HUMAN_REVIEW_REQUIRED"),
        "INSUFFICIENT_CONFIDENCE": sum(
            1 for item in policy_entries if item.get("action_policy") == "INSUFFICIENT_CONFIDENCE"
        ),
    }

    summary = {
        "classification": classification,
        "entry_count": len(policy_entries),
        "top_entry": policy_entries[0] if policy_entries else {},
        "thresholds": {
            "AUTO_ASSIGN_SAFE": ">=0.75 with strong evidence",
            "HUMAN_REVIEW_REQUIRED": "0.50-0.74",
            "INSUFFICIENT_CONFIDENCE": "<0.50",
            "strong_evidence_min_artifacts": _ACTION_POLICY_THRESHOLDS["STRONG_EVIDENCE_MIN_ARTIFACTS"],
            "strong_evidence_min_confirmation": _ACTION_POLICY_THRESHOLDS["STRONG_EVIDENCE_MIN_CONFIRMATION"],
        },
        "policy_counts": policy_counts,
    }

    _write_json(
        out_dir / "19_assignment_policy.json",
        {
            "summary": summary,
            "entries": policy_entries,
        },
    )
    _write_json(
        out_dir / "20_operator_action_plan.json",
        {
            "classification": classification,
            "operator_actions": policy_entries,
        },
    )

    lines = [
        "# Operator Action Summary",
        "",
        f"- classification: {classification}",
        f"- entry_count: {len(policy_entries)}",
        f"- auto_assign_safe: {policy_counts['AUTO_ASSIGN_SAFE']}",
        f"- human_review_required: {policy_counts['HUMAN_REVIEW_REQUIRED']}",
        f"- insufficient_confidence: {policy_counts['INSUFFICIENT_CONFIDENCE']}",
        "",
        "## Priority Fixes",
    ]
    if policy_entries:
        for item in policy_entries[:10]:
            lines.extend(
                [
                    f"- rank {item.get('priority_rank', 0)} scenario={item.get('scenario_id', '')} metric={item.get('metric', '')}",
                    f"  likely_component={item.get('likely_component', '')}",
                    f"  team={item.get('team', '')}",
                    f"  resolved_assignee={item.get('resolved_assignee', '')} source={item.get('assignee_resolution_source', '')}",
                    f"  confidence={item.get('confidence_score', 0.0)} ({item.get('confidence_level', '')})",
                    f"  action_policy={item.get('action_policy', '')}",
                    f"  recommended_operator_action={item.get('recommended_operator_action', '')}",
                ]
            )
    else:
        lines.append("- no operator actions required")

    _write_text(out_dir / "21_operator_action_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": summary,
        "entries": policy_entries,
        "artifacts": [
            "hotspots/19_assignment_policy.json",
            "hotspots/20_operator_action_plan.json",
            "hotspots/21_operator_action_summary.md",
        ],
    }
