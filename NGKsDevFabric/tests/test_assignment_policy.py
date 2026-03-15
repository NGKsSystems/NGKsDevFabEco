from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certify_compare import run_certification_comparison


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _assignment_entries(pf: Path) -> list[dict[str, object]]:
    data = json.loads((pf / "hotspots" / "19_assignment_policy.json").read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    return entries if isinstance(entries, list) else []


def test_assignment_policy_stable_no_actions(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.0, 0.0])
    pf = tmp_path / "proof" / "stable"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _assignment_entries(pf)
    assert entries == []
    summary = (pf / "hotspots" / "21_operator_action_summary.md").read_text(encoding="utf-8")
    assert "no operator actions required" in summary


def test_assignment_policy_single_auto_assign_safe(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.0])
    pf = tmp_path / "proof" / "single"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _assignment_entries(pf)
    assert len(entries) == 1
    top = entries[0]
    assert str(top.get("action_policy", "")) == "AUTO_ASSIGN_SAFE"
    assert str(top.get("recommended_operator_action", "")).startswith("assign issue")


def test_assignment_policy_multi_mix_safe_and_review(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "multi"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _assignment_entries(pf)
    assert len(entries) >= 2
    policies = {str(item.get("action_policy", "")) for item in entries}
    assert "AUTO_ASSIGN_SAFE" in policies
    assert "HUMAN_REVIEW_REQUIRED" in policies
