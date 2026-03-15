from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certify_compare import run_certification_comparison
from ngksdevfabric.ngk_fabric import connector_transport
from ngksdevfabric.ngk_fabric import delivery_reconciliation


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_profile(root: Path, profile_name: str) -> None:
    _write_json(root / "devfabeco_profile.json", {"execution_profile": profile_name})


def _make_baseline(root: Path) -> Path:
    baseline = root / "baseline_v1"
    _write_json(baseline / "baseline_manifest.json", {"baseline_version": "v1", "scenario_count": 2})
    _write_json(
        baseline / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": 1.0,
            "average_component_ownership_accuracy": 1.0,
            "average_root_cause_accuracy": 1.0,
            "average_remediation_quality": 1.0,
            "average_proof_quality": 1.0,
            "average_diagnostic_score": 0.9,
        },
    )
    _write_json(
        baseline / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "fault_missing_dependency_decl",
                    "scenario_name": "dep",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": 0.9,
                    "scores": {
                        "detection_accuracy": 1.0,
                        "component_ownership_accuracy": 1.0,
                        "root_cause_accuracy": 1.0,
                        "remediation_quality": 1.0,
                        "proof_quality": 1.0,
                    },
                },
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "base",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": 0.9,
                    "scores": {
                        "detection_accuracy": 1.0,
                        "component_ownership_accuracy": 1.0,
                        "root_cause_accuracy": 1.0,
                        "remediation_quality": 1.0,
                        "proof_quality": 1.0,
                    },
                },
            ]
        },
    )
    return baseline


def _make_current(root: Path, drops: list[float]) -> Path:
    current = root / "current"
    rows = []
    scenario_ids = ["fault_missing_dependency_decl", "baseline_pass"]
    for i, sid in enumerate(scenario_ids):
        d = drops[i]
        rows.append(
            {
                "scenario_id": sid,
                "scenario_name": sid,
                "expected_gate": "PASS",
                "actual_gate": "PASS",
                "diagnostic_score": round(0.9 - d, 4),
                "scores": {
                    "detection_accuracy": round(1.0 - d, 4),
                    "component_ownership_accuracy": round(1.0 - d, 4),
                    "root_cause_accuracy": round(1.0 - d, 4),
                    "remediation_quality": round(1.0 - d, 4),
                    "proof_quality": round(1.0 - d, 4),
                },
            }
        )

    avg_drop = sum(drops) / len(drops)
    _write_json(current / "baseline_manifest.json", {"baseline_version": "current_run", "scenario_count": 2})
    _write_json(
        current / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": round(1.0 - avg_drop, 4),
            "average_component_ownership_accuracy": round(1.0 - avg_drop, 4),
            "average_root_cause_accuracy": round(1.0 - avg_drop, 4),
            "average_remediation_quality": round(1.0 - avg_drop, 4),
            "average_proof_quality": round(1.0 - avg_drop, 4),
            "average_diagnostic_score": round(0.9 - avg_drop, 4),
        },
    )
    _write_json(current / "baseline_matrix.json", {"scenarios": rows})
    return current


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _prepare_compare_run(tmp_path: Path, drops: list[float], *, profile_name: str = "ENTERPRISE") -> Path:
    _write_profile(tmp_path, profile_name)
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, drops)
    pf = tmp_path / "proof" / "compare"
    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)
    return pf


def test_transport_dry_run_stable(tmp_path: Path) -> None:
    pf = _prepare_compare_run(tmp_path, [0.0, 0.0])

    result = connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="DRY_RUN")
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}

    assert str(summary.get("mode", "")) == "DRY_RUN"
    assert bool(summary.get("dry_run_boolean", False)) is True
    assert int(summary.get("total_request_count", -1)) == 0
    assert int(summary.get("total_failure_count", -1)) == 0

    assert (pf / "transport" / "90_transport_requests.json").is_file()
    assert (pf / "transport" / "91_transport_receipts.json").is_file()
    assert (pf / "transport" / "92_transport_failures.json").is_file()
    assert (pf / "transport" / "93_transport_summary.md").is_file()


def test_transport_dry_run_regression(tmp_path: Path) -> None:
    pf = _prepare_compare_run(tmp_path, [0.17, 0.0])

    result = connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="DRY_RUN")
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}

    assert str(summary.get("mode", "")) == "DRY_RUN"
    assert int(summary.get("total_request_count", 0)) >= 4
    assert int(summary.get("total_success_count", 0)) >= 4
    assert int(summary.get("total_failure_count", 0)) == 0

    receipts_payload = _load_json(pf / "transport" / "91_transport_receipts.json")
    receipts = receipts_payload.get("receipts", []) if isinstance(receipts_payload.get("receipts", []), list) else []
    assert receipts
    required_fields = {
        "transport_target",
        "mode",
        "request_count",
        "success_count",
        "failure_count",
        "skipped_count",
        "timestamp",
        "request_identifier",
        "dry_run_boolean",
        "response_summary_or_placeholder",
    }
    first = receipts[0] if isinstance(receipts[0], dict) else {}
    assert required_fields.issubset(set(first.keys()))


def test_transport_live_mode_missing_config(tmp_path: Path) -> None:
    pf = _prepare_compare_run(tmp_path, [0.17, 0.0])

    _write_json(
        tmp_path / "connector_transport.json",
        {
            "mode": "LIVE",
            "github": {
                "enabled": True,
                "repo_owner": "",
                "repo_name": "",
                "token_env_var": "MISSING_GITHUB_TOKEN",
            },
            "jira": {
                "enabled": True,
                "base_url": "",
                "project_key": "",
                "token_env_var": "MISSING_JIRA_TOKEN",
            },
            "email": {
                "enabled": True,
                "smtp_host": "",
                "port": 587,
                "sender": "",
            },
            "webhook": {
                "enabled": True,
                "endpoint_env_var": "MISSING_DEVFABECO_WEBHOOK_URL",
            },
        },
    )

    result = connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="LIVE")
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}

    assert str(summary.get("mode", "")) == "LIVE"
    assert int(summary.get("total_failure_count", 0)) >= 1

    failures_payload = _load_json(pf / "transport" / "92_transport_failures.json")
    failures = failures_payload.get("failures", []) if isinstance(failures_payload.get("failures", []), list) else []
    assert failures

    receipts_payload = _load_json(pf / "transport" / "91_transport_receipts.json")
    receipts = receipts_payload.get("receipts", []) if isinstance(receipts_payload.get("receipts", []), list) else []
    assert any(str(row.get("transport_target", "")) == "github" for row in receipts if isinstance(row, dict))
    assert any(str(row.get("transport_target", "")) == "jira" for row in receipts if isinstance(row, dict))
    assert any(str(row.get("transport_target", "")) == "email" for row in receipts if isinstance(row, dict))
    assert any(str(row.get("transport_target", "")) == "webhook" for row in receipts if isinstance(row, dict))


def test_transport_acknowledgment_artifacts_created(tmp_path: Path) -> None:
    pf = _prepare_compare_run(tmp_path, [0.17, 0.0])

    result = connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="DRY_RUN")
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert int(summary.get("acknowledgment_count", 0)) >= 1

    ack_payload = _load_json(pf / "transport" / "94_delivery_acknowledgments.json")
    acknowledgments = ack_payload.get("rows", []) if isinstance(ack_payload.get("rows", []), list) else []
    assert acknowledgments

    required_fields = {
        "delivery_target",
        "issue_id",
        "connector_name",
        "mode",
        "transport_status",
        "external_id",
        "external_url",
        "request_identifier",
        "timestamp",
        "reconciliation_key",
    }
    first = acknowledgments[0] if isinstance(acknowledgments[0], dict) else {}
    assert required_fields.issubset(set(first.keys()))

    assert (pf / "transport" / "95_reconciliation_matches.json").is_file()
    assert (pf / "transport" / "96_reconciliation_decisions.json").is_file()
    assert (pf / "transport" / "97_reconciliation_summary.md").is_file()


def test_transport_reconciliation_hit_skips_duplicate_create(tmp_path: Path) -> None:
    pf = _prepare_compare_run(tmp_path, [0.17, 0.0])
    connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="DRY_RUN")

    github_payloads = _load_json(pf / "hotspots" / "29_github_delivery_payload.json")
    rows = github_payloads.get("requests", []) if isinstance(github_payloads.get("requests", []), list) else []
    assert rows
    first_payload = rows[0] if isinstance(rows[0], dict) else {}

    issue_ctx = delivery_reconciliation.extract_issue_context(pf=pf, target="github", payload=first_payload)
    issue_id = str(issue_ctx.get("issue_id", "")).strip()
    rec_key = str(issue_ctx.get("reconciliation_key", "")).strip()
    assert issue_id
    assert rec_key

    _write_json(
        tmp_path / "devfabeco_delivery_history" / "acknowledgment_index.json",
        {
            "updated_at": "2026-03-01T00:00:00+00:00",
            "row_count": 1,
            "rows": [
                {
                    "delivery_target": "github",
                    "issue_id": issue_id,
                    "connector_name": "github",
                    "mode": "LIVE",
                    "transport_status": "DELIVERED",
                    "external_id": "GH-123",
                    "external_url": "https://example.invalid/issues/GH-123",
                    "request_identifier": "previous-request",
                    "timestamp": "2026-03-01T00:00:00+00:00",
                    "reconciliation_key": rec_key,
                }
            ],
        },
    )

    result = connector_transport.run_connector_transport(project_root=tmp_path, pf=pf, mode_override="DRY_RUN")
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert int(summary.get("reconciliation_match_count", 0)) >= 1

    matches_payload = _load_json(pf / "transport" / "95_reconciliation_matches.json")
    matches = matches_payload.get("rows", []) if isinstance(matches_payload.get("rows", []), list) else []
    assert any(str(row.get("connector_name", "")) == "github" for row in matches if isinstance(row, dict))

    receipts_payload = _load_json(pf / "transport" / "91_transport_receipts.json")
    receipts = receipts_payload.get("receipts", []) if isinstance(receipts_payload.get("receipts", []), list) else []
    assert any(
        str(row.get("transport_target", "")) == "github" and int(row.get("skipped_count", 0)) == 1
        for row in receipts
        if isinstance(row, dict)
    )
