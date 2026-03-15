from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certify_compare import run_certification_comparison


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


def test_delivery_stable_zero_payload_entries(tmp_path: Path) -> None:
    _write_profile(tmp_path, "ENTERPRISE")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.0, 0.0])
    pf = tmp_path / "proof" / "stable"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    github = _load_json(pf / "hotspots" / "29_github_delivery_payload.json")
    jira = _load_json(pf / "hotspots" / "30_jira_delivery_payload.json")
    email = _load_json(pf / "hotspots" / "31_email_delivery_payload.json")
    webhook = _load_json(pf / "hotspots" / "32_webhook_delivery_payload.json")

    assert github.get("requests", []) == []
    assert jira.get("requests", []) == []
    assert email.get("messages", []) == []
    assert webhook.get("requests", []) == []


def test_delivery_single_one_entry_per_adapter(tmp_path: Path) -> None:
    _write_profile(tmp_path, "ENTERPRISE")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.0])
    pf = tmp_path / "proof" / "single"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    github = _load_json(pf / "hotspots" / "29_github_delivery_payload.json")
    jira = _load_json(pf / "hotspots" / "30_jira_delivery_payload.json")
    email = _load_json(pf / "hotspots" / "31_email_delivery_payload.json")
    webhook = _load_json(pf / "hotspots" / "32_webhook_delivery_payload.json")

    assert len(github.get("requests", [])) == 1
    assert len(jira.get("requests", [])) == 1
    assert len(email.get("messages", [])) == 1
    assert len(webhook.get("requests", [])) == 1


def test_delivery_multi_preserves_deterministic_order(tmp_path: Path) -> None:
    _write_profile(tmp_path, "ENTERPRISE")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "multi"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    github = _load_json(pf / "hotspots" / "29_github_delivery_payload.json")
    email = _load_json(pf / "hotspots" / "31_email_delivery_payload.json")

    github_requests = github.get("requests", [])
    email_messages = email.get("messages", [])
    assert len(github_requests) >= 2
    assert len(email_messages) >= 2
    first_body = (github_requests[0] if isinstance(github_requests[0], dict) else {}).get("body", {})
    second_body = (github_requests[1] if isinstance(github_requests[1], dict) else {}).get("body", {})
    assert "TRIAGE-0001-" in str(first_body.get("body", ""))
    assert "TRIAGE-0002-" in str(second_body.get("body", ""))
