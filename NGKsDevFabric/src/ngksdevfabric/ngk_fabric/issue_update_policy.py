from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_UPDATE_FILE_RE = re.compile(r"^update_(\d{6})\.json$")

_ACTIONABLE_STATES = {
    "APPEND_EVIDENCE",
    "REOPEN_ISSUE",
    "CREATE_NEW_ISSUE",
    "SUPERSEDE_WITH_NEW",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_lower(value: object) -> str:
    return str(value or "").strip().lower()


def _load_connector_config(project_root: Path) -> dict[str, Any]:
    config = _read_json(project_root / "connector_transport.json")
    if not config:
        return {
            "mode": "DRY_RUN",
            "github": {"enabled": True},
            "jira": {"enabled": True},
            "email": {"enabled": True},
            "webhook": {"enabled": True},
        }
    return config


def _is_connector_live_ready(*, connector_name: str, connector_cfg: dict[str, Any], project_root: Path) -> tuple[bool, str]:
    if not bool(connector_cfg.get("enabled", True)):
        return False, "connector_disabled"

    if connector_name == "github":
        owner = str(connector_cfg.get("repo_owner", "")).strip()
        repo = str(connector_cfg.get("repo_name", "")).strip()
        token_env = str(connector_cfg.get("token_env_var", "")).strip()
        if not owner or not repo or not token_env:
            return False, "missing_live_config"
        return True, "live_config_ok"

    if connector_name == "jira":
        base_url = str(connector_cfg.get("base_url", "")).strip()
        project_key = str(connector_cfg.get("project_key", "")).strip()
        token_env = str(connector_cfg.get("token_env_var", "")).strip()
        if not base_url or not project_key or not token_env:
            return False, "missing_live_config"
        return True, "live_config_ok"

    if connector_name == "email":
        host = str(connector_cfg.get("smtp_host", "")).strip()
        sender = str(connector_cfg.get("sender", "")).strip()
        if not host or not sender:
            return False, "missing_live_config"
        return True, "live_config_ok"

    if connector_name == "webhook":
        endpoint_env = str(connector_cfg.get("endpoint_env_var", "")).strip()
        if not endpoint_env:
            return False, "missing_live_config"
        return True, "live_config_ok"

    return False, "unsupported_connector"


def _has_material_divergence(closure_row: dict[str, Any]) -> bool:
    reconciliation_key = str(closure_row.get("reconciliation_key", "")).strip().lower()
    issue_id = str(closure_row.get("issue_id", "")).strip().upper()
    if not reconciliation_key or not issue_id:
        return False
    parts = issue_id.split("-")
    if len(parts) < 4:
        return False
    scenario = _safe_lower(parts[2])
    metric = _safe_lower("_".join(parts[3:]))
    key_parts = reconciliation_key.split("|")
    if len(key_parts) < 2:
        return False
    return scenario != _safe_lower(key_parts[0]) or metric != _safe_lower(key_parts[1])


def _decide_update_action(closure_row: dict[str, Any]) -> tuple[str, str]:
    closure_state = str(closure_row.get("closure_reconciliation_state", "NO_EXTERNAL_MATCH"))
    internal_state = str(closure_row.get("internal_regression_state", "UNKNOWN"))
    external_state = str(closure_row.get("external_status_normalized", "UNKNOWN"))
    has_divergence = _has_material_divergence(closure_row)

    if has_divergence:
        return "SUPERSEDE_WITH_NEW", "material_divergence_detected"

    if closure_state == "NO_EXTERNAL_MATCH":
        return "CREATE_NEW_ISSUE", "no_prior_external_match"

    if closure_state == "EXTERNAL_OPEN_INTERNAL_ACTIVE":
        return "APPEND_EVIDENCE", "external_open_and_internal_active"

    if closure_state == "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH":
        return "REOPEN_ISSUE", "external_closed_and_internal_active"

    if closure_state == "EXTERNAL_CLOSED_INTERNAL_RESOLVED":
        return "NO_ACTION", "external_closed_and_internal_resolved"

    if closure_state == "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH":
        return "NO_ACTION", "internal_resolved_no_update_required"

    if closure_state == "UNKNOWN_EXTERNAL_STATUS":
        if internal_state == "ACTIVE":
            return "APPEND_EVIDENCE", "unknown_external_status_internal_active"
        return "NO_ACTION", "unknown_external_status_internal_not_active"

    if external_state in {"OPEN", "IN_PROGRESS"} and internal_state == "ACTIVE":
        return "APPEND_EVIDENCE", "external_open_and_internal_active_fallback"

    if external_state in {"RESOLVED", "CLOSED"} and internal_state == "ACTIVE":
        return "REOPEN_ISSUE", "external_closed_and_internal_active_fallback"

    if external_state in {"RESOLVED", "CLOSED"} and internal_state == "RESOLVED":
        return "NO_ACTION", "resolved_alignment"

    return "CREATE_NEW_ISSUE", "default_create_new"


def _ack_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    idx: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        connector = _safe_lower(row.get("connector_name", ""))
        issue_id = str(row.get("issue_id", "")).strip().upper()
        rec_key = str(row.get("reconciliation_key", "")).strip()
        idx[(connector, issue_id, rec_key)] = row
    return idx


def _payload_source_map(pf: Path) -> dict[str, list[dict[str, Any]]]:
    hot = pf / "hotspots"
    github = _read_json(hot / "29_github_delivery_payload.json")
    jira = _read_json(hot / "30_jira_delivery_payload.json")
    email = _read_json(hot / "31_email_delivery_payload.json")
    webhook = _read_json(hot / "32_webhook_delivery_payload.json")

    return {
        "github": [row for row in github.get("requests", []) if isinstance(row, dict)],
        "jira": [row for row in jira.get("requests", []) if isinstance(row, dict)],
        "email": [row for row in email.get("messages", []) if isinstance(row, dict)],
        "webhook": [row for row in webhook.get("requests", []) if isinstance(row, dict)],
    }


def _find_create_payload(*, connector_name: str, payload_sources: dict[str, list[dict[str, Any]]], issue_id: str) -> dict[str, Any]:
    rows = payload_sources.get(connector_name, [])
    for row in rows:
        body = row.get("body", {}) if isinstance(row.get("body", {}), dict) else {}
        subject = str(row.get("subject", ""))
        body_text = str(body.get("body", "")) + " " + str(body.get("title", "")) + " " + subject
        if issue_id and issue_id in body_text.upper():
            return row
    return rows[0] if rows else {}


def _build_update_payload(
    *,
    action: str,
    connector_name: str,
    closure_row: dict[str, Any],
    payload_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    issue_id = str(closure_row.get("issue_id", "")).strip().upper()
    external_id = str(closure_row.get("external_id", "")).strip()
    external_url = str(closure_row.get("external_url", "")).strip()
    evidence_note = (
        "DevFabEco update policy evidence: "
        + f"issue_id={issue_id} action={action} closure_state={str(closure_row.get('closure_reconciliation_state', ''))} "
        + "artifacts=[transport/100_closure_reconciliation.json,transport/101_external_issue_state_summary.json]"
    )

    if connector_name == "github":
        if action == "APPEND_EVIDENCE":
            return {
                "method": "POST",
                "endpoint_template": f"/repos/{{owner}}/{{repo}}/issues/{external_id or '{issue_number}'}/comments",
                "body": {"body": evidence_note},
            }
        if action == "REOPEN_ISSUE":
            return {
                "method": "PATCH",
                "endpoint_template": f"/repos/{{owner}}/{{repo}}/issues/{external_id or '{issue_number}'}",
                "body": {"state": "open", "body": evidence_note},
            }
        if action in {"CREATE_NEW_ISSUE", "SUPERSEDE_WITH_NEW"}:
            payload = _find_create_payload(
                connector_name=connector_name,
                payload_sources=payload_sources,
                issue_id=issue_id,
            )
            return payload
        return {}

    if connector_name == "jira":
        if action == "APPEND_EVIDENCE":
            return {
                "method": "POST",
                "endpoint_template": f"/rest/api/3/issue/{external_id or '{issue_key}'}/comment",
                "body": {"body": evidence_note},
            }
        if action == "REOPEN_ISSUE":
            return {
                "method": "POST",
                "endpoint_template": f"/rest/api/3/issue/{external_id or '{issue_key}'}/transitions",
                "body": {"transition": {"id": "reopen"}, "update_note": evidence_note},
            }
        if action in {"CREATE_NEW_ISSUE", "SUPERSEDE_WITH_NEW"}:
            payload = _find_create_payload(
                connector_name=connector_name,
                payload_sources=payload_sources,
                issue_id=issue_id,
            )
            return payload
        return {}

    if connector_name == "email":
        if action in {"APPEND_EVIDENCE", "REOPEN_ISSUE", "CREATE_NEW_ISSUE", "SUPERSEDE_WITH_NEW"}:
            return {
                "subject": f"[DevFabEco Update] {action} {issue_id}",
                "body_text": evidence_note + f" external_url={external_url}",
                "recipients_placeholder": ["triage@example.invalid"],
            }
        return {}

    if connector_name == "webhook":
        if action in {"APPEND_EVIDENCE", "REOPEN_ISSUE", "CREATE_NEW_ISSUE", "SUPERSEDE_WITH_NEW"}:
            return {
                "method": "POST",
                "endpoint_placeholder": "https://example.invalid/devfabeco/webhook",
                "body": {
                    "event": "issue_update_policy",
                    "action": action,
                    "issue_id": issue_id,
                    "external_id": external_id,
                    "external_url": external_url,
                    "evidence": evidence_note,
                },
            }
        return {}

    return {}


def _next_update_path(project_root: Path) -> Path:
    updates_dir = (project_root / "devfabeco_delivery_history" / "updates").resolve()
    updates_dir.mkdir(parents=True, exist_ok=True)
    max_id = 0
    for child in updates_dir.iterdir():
        if not child.is_file():
            continue
        match = _UPDATE_FILE_RE.match(child.name)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
    return updates_dir / f"update_{max_id + 1:06d}.json"


def _write_delivery_history_summary(*, project_root: Path, latest_update_file: str, action_counts: dict[str, int]) -> None:
    summary_path = (project_root / "devfabeco_delivery_history" / "summary" / "delivery_history_summary.md").resolve()
    lines = [
        "# Delivery History Summary",
        "",
        f"- latest_update_file: {latest_update_file}",
        f"- NO_ACTION: {action_counts.get('NO_ACTION', 0)}",
        f"- APPEND_EVIDENCE: {action_counts.get('APPEND_EVIDENCE', 0)}",
        f"- REOPEN_ISSUE: {action_counts.get('REOPEN_ISSUE', 0)}",
        f"- CREATE_NEW_ISSUE: {action_counts.get('CREATE_NEW_ISSUE', 0)}",
        f"- SUPERSEDE_WITH_NEW: {action_counts.get('SUPERSEDE_WITH_NEW', 0)}",
        f"- SKIP_UPDATE: {action_counts.get('SKIP_UPDATE', 0)}",
        "",
    ]
    _write_text(summary_path, "\n".join(lines))


def run_bidirectional_issue_update_policy(*, project_root: Path, pf: Path, mode: str) -> dict[str, Any]:
    transport_dir = pf / "transport"
    run_timestamp = _iso_now()
    mode_upper = str(mode or "DRY_RUN").strip().upper()
    dry_run = mode_upper == "DRY_RUN"

    acknowledgment_payload = _read_json(transport_dir / "94_delivery_acknowledgments.json")
    closure_payload = _read_json(transport_dir / "100_closure_reconciliation.json")

    acknowledgments = [row for row in acknowledgment_payload.get("rows", []) if isinstance(row, dict)]
    closure_rows = [row for row in closure_payload.get("rows", []) if isinstance(row, dict)]

    ack_idx = _ack_index(acknowledgments)
    connector_cfg = _load_connector_config(project_root)
    payload_sources = _payload_source_map(pf)

    decisions: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    skip_rows: list[dict[str, Any]] = []
    reopen_rows: list[dict[str, Any]] = []
    action_counts = {
        "NO_ACTION": 0,
        "APPEND_EVIDENCE": 0,
        "REOPEN_ISSUE": 0,
        "CREATE_NEW_ISSUE": 0,
        "SUPERSEDE_WITH_NEW": 0,
        "SKIP_UPDATE": 0,
    }

    for closure_row in closure_rows:
        connector_name = str(closure_row.get("connector_name", "")).strip().lower()
        issue_id = str(closure_row.get("issue_id", "")).strip().upper()
        rec_key = str(closure_row.get("reconciliation_key", "")).strip()

        ack = ack_idx.get((connector_name, issue_id, rec_key), {})
        action, reason = _decide_update_action(closure_row)
        material_divergence = _has_material_divergence(closure_row)
        recurrence_signal = str(closure_row.get("internal_regression_state", "")) == "ACTIVE"

        cfg = connector_cfg.get(connector_name, {}) if isinstance(connector_cfg.get(connector_name, {}), dict) else {}
        live_ready, live_reason = _is_connector_live_ready(
            connector_name=connector_name,
            connector_cfg=cfg,
            project_root=project_root,
        )

        selected_action = action
        execution = "NOT_APPLICABLE"
        live_update_performed = False
        simulated_update = False

        if action in _ACTIONABLE_STATES:
            if dry_run:
                execution = "SIMULATED_DRY_RUN"
                simulated_update = True
            else:
                if live_ready:
                    execution = "LIVE_ATTEMPTED"
                    live_update_performed = True
                else:
                    selected_action = "SKIP_UPDATE"
                    reason = "skip_missing_live_config_or_disabled"
                    execution = "SKIPPED"
                    skip_rows.append(
                        {
                            "connector_name": connector_name,
                            "issue_id": issue_id,
                            "reason": live_reason,
                        }
                    )
        elif selected_action == "NO_ACTION":
            execution = "NO_ACTION"

        if selected_action == "SKIP_UPDATE":
            action_counts["SKIP_UPDATE"] += 1
        else:
            action_counts[selected_action] = int(action_counts.get(selected_action, 0)) + 1

        payload = _build_update_payload(
            action=selected_action,
            connector_name=connector_name,
            closure_row=closure_row,
            payload_sources=payload_sources,
        )

        if payload:
            payload_rows.append(
                {
                    "connector_name": connector_name,
                    "issue_id": issue_id,
                    "selected_action": selected_action,
                    "payload": payload,
                }
            )

        if selected_action == "REOPEN_ISSUE":
            reopen_rows.append(
                {
                    "connector_name": connector_name,
                    "issue_id": issue_id,
                    "external_id": str(closure_row.get("external_id", "")),
                    "external_url": str(closure_row.get("external_url", "")),
                    "reason": reason,
                }
            )

        decisions.append(
            {
                "connector_name": connector_name,
                "issue_id": issue_id,
                "reconciliation_key": rec_key,
                "external_id": str(closure_row.get("external_id", "")),
                "external_url": str(closure_row.get("external_url", "")),
                "external_status_normalized": str(closure_row.get("external_status_normalized", "UNKNOWN")),
                "internal_regression_state": str(closure_row.get("internal_regression_state", "UNKNOWN")),
                "closure_reconciliation_state": str(closure_row.get("closure_reconciliation_state", "NO_EXTERNAL_MATCH")),
                "selected_action": selected_action,
                "decision_reason": reason,
                "material_divergence": material_divergence,
                "recurrence_signal": recurrence_signal,
                "mode": mode_upper,
                "execution": execution,
                "live_update_performed": live_update_performed,
                "simulated_update": simulated_update,
                "request_identifier": str(ack.get("request_identifier", "")),
                "timestamp": run_timestamp,
            }
        )

    _write_json(
        transport_dir / "103_update_policy_decisions.json",
        {
            "timestamp": run_timestamp,
            "mode": mode_upper,
            "rows": decisions,
        },
    )
    _write_json(
        transport_dir / "104_update_payloads.json",
        {
            "timestamp": run_timestamp,
            "mode": mode_upper,
            "rows": payload_rows,
        },
    )
    _write_json(
        transport_dir / "105_reopen_candidates.json",
        {
            "timestamp": run_timestamp,
            "mode": mode_upper,
            "rows": reopen_rows,
        },
    )
    _write_json(
        transport_dir / "106_update_skip_log.json",
        {
            "timestamp": run_timestamp,
            "mode": mode_upper,
            "rows": skip_rows,
        },
    )

    summary_lines = [
        "# Bidirectional Issue Update Summary",
        "",
        f"- mode: {mode_upper}",
        f"- tracked_issue_count: {len(decisions)}",
        f"- NO_ACTION: {action_counts.get('NO_ACTION', 0)}",
        f"- APPEND_EVIDENCE: {action_counts.get('APPEND_EVIDENCE', 0)}",
        f"- REOPEN_ISSUE: {action_counts.get('REOPEN_ISSUE', 0)}",
        f"- CREATE_NEW_ISSUE: {action_counts.get('CREATE_NEW_ISSUE', 0)}",
        f"- SUPERSEDE_WITH_NEW: {action_counts.get('SUPERSEDE_WITH_NEW', 0)}",
        f"- SKIP_UPDATE: {action_counts.get('SKIP_UPDATE', 0)}",
        f"- simulated_update_count: {sum(1 for row in decisions if bool(row.get('simulated_update', False)))}",
        f"- live_update_attempt_count: {sum(1 for row in decisions if bool(row.get('live_update_performed', False)))}",
        "",
        "## Selected Actions",
    ]
    for row in decisions[:50]:
        summary_lines.append(
            "- connector="
            + str(row.get("connector_name", ""))
            + " issue_id="
            + str(row.get("issue_id", ""))
            + " action="
            + str(row.get("selected_action", ""))
            + " reason="
            + str(row.get("decision_reason", ""))
            + " execution="
            + str(row.get("execution", ""))
        )
    _write_text(transport_dir / "107_bidirectional_update_summary.md", "\n".join(summary_lines) + "\n")

    update_path = _next_update_path(project_root)
    _write_json(
        update_path,
        {
            "timestamp": run_timestamp,
            "pf": str(pf.resolve()),
            "mode": mode_upper,
            "rows": decisions,
            "summary": {
                "tracked_issue_count": len(decisions),
                "action_counts": action_counts,
            },
        },
    )
    _write_delivery_history_summary(
        project_root=project_root,
        latest_update_file=update_path.name,
        action_counts=action_counts,
    )

    return {
        "summary": {
            "tracked_issue_count": len(decisions),
            "action_counts": action_counts,
            "simulated_update_count": sum(1 for row in decisions if bool(row.get("simulated_update", False))),
            "live_update_attempt_count": sum(1 for row in decisions if bool(row.get("live_update_performed", False))),
            "update_history_file": str(update_path),
        },
        "artifacts": [
            "transport/103_update_policy_decisions.json",
            "transport/104_update_payloads.json",
            "transport/105_reopen_candidates.json",
            "transport/106_update_skip_log.json",
            "transport/107_bidirectional_update_summary.md",
        ],
    }