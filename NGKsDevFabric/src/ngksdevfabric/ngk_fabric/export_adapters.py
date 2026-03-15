from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_JIRA_PRIORITY_MAP = {
    "P1_CRITICAL": "Highest",
    "P2_HIGH": "High",
    "P3_MEDIUM": "Medium",
    "P4_LOW": "Low",
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


def _owner_slug(component: str) -> str:
    raw = component.strip().lower()
    if not raw:
        return "unassigned"
    parts = ["".join(ch for ch in chunk if ch.isalnum()) for chunk in raw.replace("-", " ").split()]
    compact = "_".join(part for part in parts if part)
    return compact or "unassigned"


def _github_body(ticket: dict[str, Any]) -> str:
    lines = [
        "## Regression Ticket",
        "",
        f"- Issue ID: {ticket.get('issue_id', '')}",
        f"- Scenario: {ticket.get('scenario_id', '')}",
        f"- Metric: {ticket.get('metric', '')}",
        f"- Team: {ticket.get('team', '')}",
        f"- Resolved Assignee: {ticket.get('resolved_assignee', '')}",
        f"- Severity: {ticket.get('severity_score', 0.0)}",
        f"- Confidence: {ticket.get('confidence_score', 0.0)} ({ticket.get('confidence_level', '')})",
        f"- Action Policy: {ticket.get('action_policy', '')}",
        f"- Recommended Action: {ticket.get('recommended_operator_action', '')}",
        "",
        "### Evidence References",
    ]
    evidence = ticket.get("evidence_sources", [])
    if isinstance(evidence, list) and evidence:
        lines.extend([f"- {item}" for item in evidence])
    else:
        lines.append("- none")
    return "\n".join(lines)


def generate_ticket_export_adapters(
    *,
    pf: Path,
    classification: str,
    triage_tickets: dict[str, Any],
) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    tickets = triage_tickets.get("tickets", [])
    if not isinstance(tickets, list):
        tickets = []

    github_issues: list[dict[str, Any]] = []
    jira_issues: list[dict[str, Any]] = []
    generic_feed: list[dict[str, Any]] = []

    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue

        issue_title = str(ticket.get("issue_title", "Regression detected"))
        priority_class = str(ticket.get("priority_class", "P4_LOW"))
        likely_component = str(ticket.get("likely_component", ""))
        resolved_assignee = str(ticket.get("resolved_assignee", "")).strip()
        owner = resolved_assignee if resolved_assignee else _owner_slug(likely_component)
        team = str(ticket.get("team", "")).strip()
        evidence_sources = ticket.get("evidence_sources", [])
        if not isinstance(evidence_sources, list):
            evidence_sources = []

        github_issues.append(
            {
                "title": issue_title,
                "body": _github_body(ticket),
                "labels": ["regression", priority_class],
                "assignee": owner,
            }
        )

        jira_issues.append(
            {
                "fields": {
                    "summary": issue_title,
                    "description": _github_body(ticket),
                    "priority": _JIRA_PRIORITY_MAP.get(priority_class, "Low"),
                    "labels": ["regression", priority_class],
                    "components": [team] if team else [owner],
                    "assignee": owner,
                }
            }
        )

        generic_feed.append(
            {
                "issue_id": str(ticket.get("issue_id", "")),
                "title": issue_title,
                "priority": priority_class,
                "owner": likely_component,
                "team": team,
                "assignee": owner,
                "severity_score": round(_safe_float(ticket.get("severity_score", 0.0)), 6),
                "confidence": {
                    "score": round(_safe_float(ticket.get("confidence_score", 0.0)), 6),
                    "level": str(ticket.get("confidence_level", "LOW_CONFIDENCE")),
                },
                "recommended_action": str(ticket.get("recommended_operator_action", "")),
                "evidence": evidence_sources,
            }
        )

    _write_json(
        out_dir / "25_github_issue_export.json",
        {
            "classification": classification,
            "issues": github_issues,
        },
    )
    _write_json(
        out_dir / "26_jira_issue_export.json",
        {
            "classification": classification,
            "issues": jira_issues,
        },
    )
    _write_json(
        out_dir / "27_issue_feed.json",
        {
            "issues": generic_feed,
        },
    )

    lines = [
        "# Issue Export Summary",
        "",
        f"- classification: {classification}",
        f"- exported_ticket_count: {len(github_issues)}",
        "",
        "## Exported Tickets",
    ]
    if generic_feed:
        for row in generic_feed:
            confidence = row.get("confidence", {})
            lines.extend(
                [
                    f"- title={row.get('title', '')}",
                    f"  priority={row.get('priority', '')}",
                    f"  component={row.get('owner', '')}",
                    f"  team={row.get('team', '')}",
                    f"  assignee={row.get('assignee', '')}",
                    f"  confidence={confidence.get('score', 0.0)} ({confidence.get('level', '')})",
                    f"  recommended_action={row.get('recommended_action', '')}",
                ]
            )
    else:
        lines.append("- no tickets exported")

    _write_text(out_dir / "28_issue_export_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": {
            "classification": classification,
            "exported_ticket_count": len(github_issues),
            "top_exported_issue": generic_feed[0] if generic_feed else {},
        },
        "artifacts": [
            "hotspots/25_github_issue_export.json",
            "hotspots/26_jira_issue_export.json",
            "hotspots/27_issue_feed.json",
            "hotspots/28_issue_export_summary.md",
        ],
    }
