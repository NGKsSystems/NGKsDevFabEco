from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def generate_connector_ready_delivery_payloads(*, pf: Path) -> dict[str, Any]:
    out_dir = pf / "hotspots"

    github_export = _read_json(out_dir / "25_github_issue_export.json")
    jira_export = _read_json(out_dir / "26_jira_issue_export.json")
    feed_export = _read_json(out_dir / "27_issue_feed.json")
    export_summary_md = _read_text(out_dir / "28_issue_export_summary.md")

    github_issues = github_export.get("issues", [])
    if not isinstance(github_issues, list):
        github_issues = []
    jira_issues = jira_export.get("issues", [])
    if not isinstance(jira_issues, list):
        jira_issues = []
    generic_issues = feed_export.get("issues", [])
    if not isinstance(generic_issues, list):
        generic_issues = []

    github_requests: list[dict[str, Any]] = []
    for item in github_issues:
        if not isinstance(item, dict):
            continue
        assignee = str(item.get("assignee", "")).strip()
        github_requests.append(
            {
                "method": "POST",
                "endpoint_template": "/repos/{owner}/{repo}/issues",
                "headers": {
                    "Accept": "application/vnd.github+json",
                },
                "body": {
                    "title": str(item.get("title", "")),
                    "body": str(item.get("body", "")),
                    "labels": item.get("labels", []) if isinstance(item.get("labels", []), list) else [],
                    "assignees": [assignee] if assignee else [],
                },
            }
        )

    jira_requests: list[dict[str, Any]] = []
    for item in jira_issues:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        jira_requests.append(
            {
                "method": "POST",
                "endpoint_template": "/rest/api/3/issue",
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": {
                    "fields": {
                        "summary": str(fields.get("summary", "")),
                        "description": str(fields.get("description", "")),
                        "priority": {
                            "name": str(fields.get("priority", "Low")),
                        },
                        "labels": fields.get("labels", []) if isinstance(fields.get("labels", []), list) else [],
                        "components": fields.get("components", [])
                        if isinstance(fields.get("components", []), list)
                        else [],
                    }
                },
            }
        )

    email_messages: list[dict[str, Any]] = []
    for item in generic_issues:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "Regression ticket"))
        issue_id = str(item.get("issue_id", ""))
        subject = f"[DevFabEco Triage] {title}"
        markdown_lines = [
            f"# {title}",
            "",
            f"- issue_id: {issue_id}",
            f"- priority: {item.get('priority', '')}",
            f"- owner: {item.get('owner', '')}",
            f"- team: {item.get('team', '')}",
            f"- assignee: {item.get('assignee', '')}",
            f"- severity_score: {item.get('severity_score', 0.0)}",
            f"- recommended_action: {item.get('recommended_action', '')}",
            "",
            "## Evidence",
        ]
        evidence = item.get("evidence", [])
        if isinstance(evidence, list) and evidence:
            markdown_lines.extend([f"- {str(e)}" for e in evidence])
        else:
            markdown_lines.append("- none")
        body_markdown = "\n".join(markdown_lines)
        body_text = body_markdown.replace("# ", "").replace("## ", "")
        email_messages.append(
            {
                "subject": subject,
                "body_markdown": body_markdown,
                "body_text": body_text,
                "recipients_placeholder": ["triage@example.invalid"],
            }
        )

    webhook_requests = []
    if generic_issues:
        webhook_requests.append(
            {
                "method": "POST",
                "endpoint_placeholder": "https://example.invalid/devfabeco/webhook",
                "headers": {
                    "Content-Type": "application/json",
                },
                "body": {
                    "issues": generic_issues,
                },
            }
        )

    _write_json(
        out_dir / "29_github_delivery_payload.json",
        {
            "requests": github_requests,
        },
    )
    _write_json(
        out_dir / "30_jira_delivery_payload.json",
        {
            "requests": jira_requests,
        },
    )
    _write_json(
        out_dir / "31_email_delivery_payload.json",
        {
            "messages": email_messages,
        },
    )
    _write_json(
        out_dir / "32_webhook_delivery_payload.json",
        {
            "requests": webhook_requests,
        },
    )

    contract = {
        "supported_adapters": ["github", "jira", "email", "webhook"],
        "required_input_artifacts": [
            "hotspots/25_github_issue_export.json",
            "hotspots/26_jira_issue_export.json",
            "hotspots/27_issue_feed.json",
            "hotspots/28_issue_export_summary.md",
        ],
        "output_payload_artifacts": [
            "hotspots/29_github_delivery_payload.json",
            "hotspots/30_jira_delivery_payload.json",
            "hotspots/31_email_delivery_payload.json",
            "hotspots/32_webhook_delivery_payload.json",
        ],
        "placeholder_auth_expectations": {
            "github": "token not included in payload; connector injects Authorization header",
            "jira": "token not included in payload; connector injects Authorization header",
            "email": "smtp credentials not included; connector injects transport config",
            "webhook": "secret/signature not included; connector injects signing and endpoint",
        },
        "send_not_send_guarantee": "NOT_SENT_DELIVERY_STAGE_ONLY",
        "future_transport_integration_expectations": [
            "transport layer resolves endpoint placeholders",
            "transport layer injects auth and retry policy",
            "transport layer records delivery receipts and errors",
            "delivery adapter payload order must be preserved",
        ],
    }
    _write_json(out_dir / "33_delivery_contract.json", contract)

    lines = [
        "# Delivery Adapter Summary",
        "",
        "- payloads_produced:",
        "  - hotspots/29_github_delivery_payload.json",
        "  - hotspots/30_jira_delivery_payload.json",
        "  - hotspots/31_email_delivery_payload.json",
        "  - hotspots/32_webhook_delivery_payload.json",
        "- source_exports:",
        "  - hotspots/25_github_issue_export.json",
        "  - hotspots/26_jira_issue_export.json",
        "  - hotspots/27_issue_feed.json",
        "  - hotspots/28_issue_export_summary.md",
        "- future_connector_requirements:",
        "  - resolve endpoint templates/placeholders",
        "  - inject authentication/authorization",
        "  - apply retry/backoff and receipt logging",
        "- live_delivery_status: NO_LIVE_DELIVERY_PERFORMED",
    ]
    if export_summary_md.strip():
        lines.extend(["", "## Source Export Summary Snapshot", export_summary_md.strip()])
    _write_text(out_dir / "34_delivery_adapter_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": {
            "github_request_count": len(github_requests),
            "jira_request_count": len(jira_requests),
            "email_message_count": len(email_messages),
            "webhook_request_count": len(webhook_requests),
            "top_issue_id": str(generic_issues[0].get("issue_id", "")) if generic_issues else "",
            "send_status": "NOT_SENT",
        },
        "artifacts": [
            "hotspots/29_github_delivery_payload.json",
            "hotspots/30_jira_delivery_payload.json",
            "hotspots/31_email_delivery_payload.json",
            "hotspots/32_webhook_delivery_payload.json",
            "hotspots/33_delivery_contract.json",
            "hotspots/34_delivery_adapter_summary.md",
        ],
    }
