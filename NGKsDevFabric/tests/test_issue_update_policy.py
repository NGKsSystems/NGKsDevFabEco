from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.issue_update_policy import run_bidirectional_issue_update_policy


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _ack(issue_id: str, connector_name: str = "github", external_id: str = "GH-100") -> dict[str, object]:
    return {
        "delivery_target": connector_name,
        "issue_id": issue_id,
        "connector_name": connector_name,
        "mode": "DRY_RUN",
        "transport_status": "SIMULATED",
        "external_id": external_id,
        "external_url": "https://example.invalid/issues/" + external_id,
        "request_identifier": "req-001",
        "timestamp": "2026-03-14T00:00:00+00:00",
        "reconciliation_key": "fault_missing_dependency_decl|diagnostic_score|dependency_graph_resolver",
    }


def _set_connector_config(project_root: Path, mode: str = "DRY_RUN") -> None:
    _write_json(
        project_root / "connector_transport.json",
        {
            "mode": mode,
            "github": {
                "enabled": True,
                "repo_owner": "example-org",
                "repo_name": "example-repo",
                "token_env_var": "GITHUB_TOKEN",
            },
            "jira": {
                "enabled": True,
                "base_url": "https://jira.example.com",
                "project_key": "ENG",
                "token_env_var": "JIRA_TOKEN",
            },
            "email": {
                "enabled": True,
                "smtp_host": "smtp.example.com",
                "port": 587,
                "sender": "devfabeco@example.com",
            },
            "webhook": {
                "enabled": True,
                "endpoint_env_var": "DEVFABECO_WEBHOOK_URL",
            },
        },
    )


def _set_delivery_payloads(pf: Path, issue_id: str) -> None:
    _write_json(
        pf / "hotspots" / "29_github_delivery_payload.json",
        {
            "requests": [
                {
                    "method": "POST",
                    "endpoint_template": "/repos/{owner}/{repo}/issues",
                    "body": {
                        "title": "Regression " + issue_id,
                        "body": "Issue " + issue_id,
                        "labels": ["regression"],
                        "assignees": ["owner"],
                    },
                }
            ]
        },
    )
    _write_json(
        pf / "hotspots" / "30_jira_delivery_payload.json",
        {
            "requests": [
                {
                    "method": "POST",
                    "endpoint_template": "/rest/api/3/issue",
                    "body": {"fields": {"summary": "Regression " + issue_id, "description": issue_id}},
                }
            ]
        },
    )
    _write_json(
        pf / "hotspots" / "31_email_delivery_payload.json",
        {
            "messages": [
                {
                    "subject": "Regression " + issue_id,
                    "body_text": "Issue " + issue_id,
                    "recipients_placeholder": ["triage@example.invalid"],
                }
            ]
        },
    )
    _write_json(
        pf / "hotspots" / "32_webhook_delivery_payload.json",
        {
            "requests": [
                {
                    "method": "POST",
                    "endpoint_placeholder": "https://example.invalid/devfabeco/webhook",
                    "body": {"issues": [{"issue_id": issue_id}]},
                }
            ]
        },
    )


def _set_transport_inputs(
    pf: Path,
    *,
    issue_id: str,
    closure_state: str,
    external_status: str,
    internal_state: str,
    external_id: str = "GH-100",
) -> None:
    ack = _ack(issue_id=issue_id, external_id=external_id)
    _write_json(pf / "transport" / "94_delivery_acknowledgments.json", {"rows": [ack]})
    _write_json(
        pf / "transport" / "100_closure_reconciliation.json",
        {
            "rows": [
                {
                    "connector_name": "github",
                    "issue_id": issue_id,
                    "reconciliation_key": "fault_missing_dependency_decl|diagnostic_score|dependency_graph_resolver",
                    "external_id": external_id,
                    "external_url": "https://example.invalid/issues/" + external_id,
                    "external_status_raw": external_status.lower(),
                    "external_status_normalized": external_status,
                    "internal_regression_state": internal_state,
                    "closure_reconciliation_state": closure_state,
                    "match_strategy": "issue_id",
                    "timestamp": "2026-03-14T00:00:00+00:00",
                }
            ]
        },
    )


def _decision_actions(pf: Path) -> set[str]:
    payload = json.loads((pf / "transport" / "103_update_policy_decisions.json").read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload.get("rows", []), list) else []
    return {str(row.get("selected_action", "")) for row in rows if isinstance(row, dict)}


def test_append_evidence_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "append"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _set_connector_config(project_root)
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        external_status="OPEN",
        internal_state="ACTIVE",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")
    assert "APPEND_EVIDENCE" in _decision_actions(pf)


def test_reopen_issue_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "reopen"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _set_connector_config(project_root)
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH",
        external_status="CLOSED",
        internal_state="ACTIVE",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")
    assert "REOPEN_ISSUE" in _decision_actions(pf)


def test_no_action_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "no_action"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _set_connector_config(project_root)
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="EXTERNAL_CLOSED_INTERNAL_RESOLVED",
        external_status="CLOSED",
        internal_state="RESOLVED",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")
    assert "NO_ACTION" in _decision_actions(pf)


def test_create_new_issue_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "create_new"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _set_connector_config(project_root)
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="NO_EXTERNAL_MATCH",
        external_status="UNKNOWN",
        internal_state="ACTIVE",
        external_id="",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")
    assert "CREATE_NEW_ISSUE" in _decision_actions(pf)


def test_dry_run_simulated_update_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "dry_run_simulated"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _set_connector_config(project_root, mode="DRY_RUN")
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        external_status="OPEN",
        internal_state="ACTIVE",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")

    payload = json.loads((pf / "transport" / "103_update_policy_decisions.json").read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload.get("rows", []), list) else []
    first = rows[0] if rows and isinstance(rows[0], dict) else {}

    assert str(first.get("selected_action", "")) == "APPEND_EVIDENCE"
    assert bool(first.get("simulated_update", False)) is True
    assert bool(first.get("live_update_performed", True)) is False

    assert (pf / "transport" / "103_update_policy_decisions.json").is_file()
    assert (pf / "transport" / "104_update_payloads.json").is_file()
    assert (pf / "transport" / "105_reopen_candidates.json").is_file()
    assert (pf / "transport" / "106_update_skip_log.json").is_file()
    assert (pf / "transport" / "107_bidirectional_update_summary.md").is_file()


def test_optional_supersede_case(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "supersede"
    issue_id = "TRIAGE-0001-BASELINE_PASS-ROOT_CAUSE_ACCURACY"

    _set_connector_config(project_root, mode="DRY_RUN")
    _set_delivery_payloads(pf, issue_id)
    _set_transport_inputs(
        pf,
        issue_id=issue_id,
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        external_status="OPEN",
        internal_state="ACTIVE",
    )

    run_bidirectional_issue_update_policy(project_root=project_root, pf=pf, mode="DRY_RUN")
    assert "SUPERSEDE_WITH_NEW" in _decision_actions(pf)
