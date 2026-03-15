from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PRIORITY_THRESHOLDS = {
    "P1_CRITICAL": 0.15,
    "P2_HIGH": 0.10,
    "P3_MEDIUM": 0.05,
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


def _priority_class(severity_score: float) -> str:
    if severity_score >= _PRIORITY_THRESHOLDS["P1_CRITICAL"]:
        return "P1_CRITICAL"
    if severity_score >= _PRIORITY_THRESHOLDS["P2_HIGH"]:
        return "P2_HIGH"
    if severity_score >= _PRIORITY_THRESHOLDS["P3_MEDIUM"]:
        return "P3_MEDIUM"
    return "P4_LOW"


def _issue_id(priority_rank: int, scenario_id: str, metric: str) -> str:
    sid = "".join(ch if ch.isalnum() else "_" for ch in scenario_id).strip("_") or "scenario"
    met = "".join(ch if ch.isalnum() else "_" for ch in metric).strip("_") or "metric"
    return f"TRIAGE-{priority_rank:04d}-{sid}-{met}".upper()


def _issue_title(likely_component: str) -> str:
    component = likely_component.strip() or "unknown component"
    return f"Regression detected in {component}"


def generate_auto_triage_tickets(
    *,
    pf: Path,
    classification: str,
    assignment_policy: dict[str, Any],
    ownership_confidence: dict[str, Any],
) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    policy_entries = assignment_policy.get("entries", [])
    if not isinstance(policy_entries, list):
        policy_entries = []

    ownership_entries = ownership_confidence.get("entries", [])
    if not isinstance(ownership_entries, list):
        ownership_entries = []

    ownership_index: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in ownership_entries:
        if not isinstance(entry, dict):
            continue
        key = (str(entry.get("scenario_id", "")), str(entry.get("metric", "")))
        ownership_index[key] = entry

    tickets: list[dict[str, Any]] = []
    for item in policy_entries:
        if not isinstance(item, dict):
            continue

        scenario_id = str(item.get("scenario_id", ""))
        metric = str(item.get("metric", ""))
        priority_rank = int(item.get("priority_rank", len(tickets) + 1) or (len(tickets) + 1))
        severity_score = round(_safe_float(item.get("severity_score", 0.0)), 6)
        priority_class = _priority_class(severity_score)
        owner_entry = ownership_index.get((scenario_id, metric), {})

        evidence_sources = owner_entry.get("evidence_artifacts", [])
        if not isinstance(evidence_sources, list):
            evidence_sources = []

        ticket = {
            "issue_id": _issue_id(priority_rank, scenario_id, metric),
            "issue_title": _issue_title(str(item.get("likely_component", ""))),
            "scenario_id": scenario_id,
            "metric": metric,
            "severity_score": severity_score,
            "priority_rank": priority_rank,
            "priority_class": priority_class,
            "likely_component": str(item.get("likely_component", "")),
            "team": str(item.get("team", "")),
            "resolved_assignee": str(item.get("resolved_assignee", "")),
            "assignee_resolution_source": str(item.get("assignee_resolution_source", "")),
            "escalation_owner": str(item.get("escalation_owner", "")),
            "confidence_score": round(_safe_float(item.get("confidence_score", 0.0)), 6),
            "confidence_level": str(item.get("confidence_level", "LOW_CONFIDENCE")),
            "action_policy": str(item.get("action_policy", "INSUFFICIENT_CONFIDENCE")),
            "recommended_operator_action": str(item.get("recommended_operator_action", "")),
            "evidence_sources": evidence_sources,
        }
        tickets.append(ticket)

    def _priority_order(value: str) -> int:
        return {"P1_CRITICAL": 1, "P2_HIGH": 2, "P3_MEDIUM": 3, "P4_LOW": 4}.get(value, 9)

    tickets = sorted(
        tickets,
        key=lambda row: (
            int(row.get("priority_rank", 999999)),
            _priority_order(str(row.get("priority_class", "P4_LOW"))),
            -_safe_float(row.get("severity_score", 0.0)),
            str(row.get("scenario_id", "")),
        ),
    )
    for idx, row in enumerate(tickets, start=1):
        row["priority_rank"] = idx
        row["issue_id"] = _issue_id(idx, str(row.get("scenario_id", "")), str(row.get("metric", "")))

    index_rows = [
        {
            "issue_id": row["issue_id"],
            "priority_rank": row["priority_rank"],
            "priority_class": row["priority_class"],
            "scenario_id": row["scenario_id"],
            "metric": row["metric"],
        }
        for row in tickets
    ]

    counts = {
        "P1_CRITICAL": sum(1 for row in tickets if row.get("priority_class") == "P1_CRITICAL"),
        "P2_HIGH": sum(1 for row in tickets if row.get("priority_class") == "P2_HIGH"),
        "P3_MEDIUM": sum(1 for row in tickets if row.get("priority_class") == "P3_MEDIUM"),
        "P4_LOW": sum(1 for row in tickets if row.get("priority_class") == "P4_LOW"),
    }

    summary = {
        "classification": classification,
        "ticket_count": len(tickets),
        "top_ticket": tickets[0] if tickets else {},
        "priority_thresholds": {
            "P1_CRITICAL": ">=0.15",
            "P2_HIGH": "0.10-0.1499",
            "P3_MEDIUM": "0.05-0.0999",
            "P4_LOW": "<0.05",
        },
        "priority_counts": counts,
    }

    _write_json(out_dir / "22_triage_tickets.json", {"summary": summary, "tickets": tickets})
    _write_json(out_dir / "23_triage_ticket_index.json", {"index": index_rows})

    lines = [
        "# Auto-Triage Summary",
        "",
        f"- classification: {classification}",
        f"- ticket_count: {len(tickets)}",
        f"- p1_critical: {counts['P1_CRITICAL']}",
        f"- p2_high: {counts['P2_HIGH']}",
        f"- p3_medium: {counts['P3_MEDIUM']}",
        f"- p4_low: {counts['P4_LOW']}",
        "",
        "## Tickets",
    ]
    if tickets:
        for row in tickets[:20]:
            lines.extend(
                [
                    f"- {row.get('issue_id', '')} priority={row.get('priority_class', '')} rank={row.get('priority_rank', 0)}",
                    f"  title={row.get('issue_title', '')}",
                    f"  scenario={row.get('scenario_id', '')} metric={row.get('metric', '')} severity={row.get('severity_score', 0.0)}",
                    f"  owner={row.get('likely_component', '')}",
                    f"  team={row.get('team', '')}",
                    f"  resolved_assignee={row.get('resolved_assignee', '')} source={row.get('assignee_resolution_source', '')}",
                    f"  confidence={row.get('confidence_score', 0.0)} ({row.get('confidence_level', '')})",
                    f"  action_policy={row.get('action_policy', '')}",
                    f"  recommended_operator_action={row.get('recommended_operator_action', '')}",
                    f"  evidence_sources={', '.join(row.get('evidence_sources', []))}",
                ]
            )
    else:
        lines.append("- no triage tickets generated")

    _write_text(out_dir / "24_triage_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": summary,
        "tickets": tickets,
        "artifacts": [
            "hotspots/22_triage_tickets.json",
            "hotspots/23_triage_ticket_index.json",
            "hotspots/24_triage_summary.md",
        ],
    }
