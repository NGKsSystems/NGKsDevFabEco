from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.external_status_sync import run_external_status_sync_and_closure_reconciliation


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


def _setup_resolution(pf: Path, state: str) -> None:
    rows: list[dict[str, object]] = []
    if state:
        rows.append(
            {
                "fingerprint": "fp-1",
                "state": state,
                "component": "dependency_graph_resolver",
                "scenario_id": "fault_missing_dependency_decl",
                "metric": "diagnostic_score",
                "severity_bucket": "HIGH",
                "previous_occurrences": 0,
                "current_occurrences": 1,
                "history_run_id": "run_000001",
            }
        )
    _write_json(pf / "resolution" / "70_regression_lifecycle_states.json", {"rows": rows})


def _setup_config(project_root: Path, github_snapshot: Path) -> None:
    _write_json(
        project_root / "external_status_sync.json",
        {
            "github": {
                "enabled": True,
                "status_snapshot_path": str(github_snapshot.relative_to(project_root)).replace("\\", "/"),
            },
            "jira": {
                "enabled": False,
                "status_snapshot_path": "fixtures/jira_status_snapshot.json",
            },
        },
    )


def _state_rows(pf: Path) -> list[dict[str, object]]:
    payload = json.loads((pf / "transport" / "100_closure_reconciliation.json").read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    return rows if isinstance(rows, list) else []


def test_external_open_internal_active(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "case1"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _setup_resolution(pf, "PERSISTING")
    snap = project_root / "fixtures" / "github_status_snapshot.json"
    _write_json(snap, {"issues": [{"issue_id": issue_id, "status": "open", "external_id": "GH-100"}]})
    _setup_config(project_root, snap)

    run_external_status_sync_and_closure_reconciliation(project_root=project_root, pf=pf, acknowledgments=[_ack(issue_id)])

    rows = _state_rows(pf)
    assert rows
    first = rows[0] if isinstance(rows[0], dict) else {}
    assert str(first.get("closure_reconciliation_state", "")) == "EXTERNAL_OPEN_INTERNAL_ACTIVE"


def test_external_closed_internal_resolved(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "case2"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _setup_resolution(pf, "RESOLVED")
    snap = project_root / "fixtures" / "github_status_snapshot.json"
    _write_json(snap, {"issues": [{"issue_id": issue_id, "status": "closed", "external_id": "GH-100"}]})
    _setup_config(project_root, snap)

    run_external_status_sync_and_closure_reconciliation(project_root=project_root, pf=pf, acknowledgments=[_ack(issue_id)])

    rows = _state_rows(pf)
    first = rows[0] if isinstance(rows[0], dict) else {}
    assert str(first.get("closure_reconciliation_state", "")) == "EXTERNAL_CLOSED_INTERNAL_RESOLVED"


def test_external_closed_internal_active_mismatch(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "case3"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _setup_resolution(pf, "RECURRING")
    snap = project_root / "fixtures" / "github_status_snapshot.json"
    _write_json(snap, {"issues": [{"issue_id": issue_id, "status": "closed", "external_id": "GH-100"}]})
    _setup_config(project_root, snap)

    run_external_status_sync_and_closure_reconciliation(project_root=project_root, pf=pf, acknowledgments=[_ack(issue_id)])

    rows = _state_rows(pf)
    first = rows[0] if isinstance(rows[0], dict) else {}
    assert str(first.get("closure_reconciliation_state", "")) == "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH"


def test_external_open_internal_resolved_mismatch(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "case4"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _setup_resolution(pf, "RESOLVED")
    snap = project_root / "fixtures" / "github_status_snapshot.json"
    _write_json(snap, {"issues": [{"issue_id": issue_id, "status": "open", "external_id": "GH-100"}]})
    _setup_config(project_root, snap)

    run_external_status_sync_and_closure_reconciliation(project_root=project_root, pf=pf, acknowledgments=[_ack(issue_id)])

    rows = _state_rows(pf)
    first = rows[0] if isinstance(rows[0], dict) else {}
    assert str(first.get("closure_reconciliation_state", "")) == "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH"


def test_no_external_match_or_unknown(tmp_path: Path) -> None:
    project_root = tmp_path
    pf = tmp_path / "proof" / "case5"
    issue_id = "TRIAGE-0001-FAULT_MISSING_DEPENDENCY_DECL-DIAGNOSTIC_SCORE"

    _setup_resolution(pf, "RECURRING")
    snap = project_root / "fixtures" / "github_status_snapshot.json"
    _write_json(
        snap,
        {
            "issues": [
                {"issue_id": "TRIAGE-9999-OTHER-METRIC", "status": "open", "external_id": "GH-999"},
                {"issue_id": issue_id, "status": "mystery_state", "external_id": "GH-100"},
            ]
        },
    )
    _setup_config(project_root, snap)

    run_external_status_sync_and_closure_reconciliation(
        project_root=project_root,
        pf=pf,
        acknowledgments=[_ack(issue_id), _ack("TRIAGE-0002-BASELINE_PASS-DIAGNOSTIC_SCORE", external_id="GH-200")],
    )

    rows = _state_rows(pf)
    states = {str(row.get("closure_reconciliation_state", "")) for row in rows if isinstance(row, dict)}
    assert "UNKNOWN_EXTERNAL_STATUS" in states
    assert "NO_EXTERNAL_MATCH" in states

    assert (pf / "transport" / "98_external_status_sync.json").is_file()
    assert (pf / "transport" / "99_status_normalization.json").is_file()
    assert (pf / "transport" / "100_closure_reconciliation.json").is_file()
    assert (pf / "transport" / "101_external_issue_state_summary.json").is_file()
    assert (pf / "transport" / "102_closure_reconciliation_summary.md").is_file()
