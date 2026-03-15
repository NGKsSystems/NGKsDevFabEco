from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certify_compare import run_certification_comparison


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_baseline(root: Path) -> Path:
    baseline = root / "baseline_v1"
    _write_json(
        baseline / "baseline_manifest.json",
        {
            "baseline_version": "v1",
            "creation_timestamp": "2026-03-13T00:00:00+00:00",
            "scenario_count": 2,
            "notes": [],
        },
    )
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
                    "scenario_name": "dependency",
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
                    "scenario_name": "baseline",
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


def _make_current(root: Path, *, drops: list[float]) -> Path:
    current = root / "current"
    rows = []
    for i, sid in enumerate(["fault_missing_dependency_decl", "baseline_pass"]):
        d = drops[i]
        score = round(0.9 - d, 4)
        rows.append(
            {
                "scenario_id": sid,
                "scenario_name": sid,
                "expected_gate": "PASS",
                "actual_gate": "PASS",
                "diagnostic_score": score,
                "scores": {
                    "detection_accuracy": round(1.0 - d, 4),
                    "component_ownership_accuracy": round(1.0 - d, 4),
                    "root_cause_accuracy": round(1.0 - d, 4),
                    "remediation_quality": round(1.0 - d, 4),
                    "proof_quality": round(1.0 - d, 4),
                },
            }
        )

    _write_json(
        current / "baseline_manifest.json",
        {
            "baseline_version": "current_run",
            "creation_timestamp": "2026-03-13T00:00:00+00:00",
            "scenario_count": 2,
            "notes": [],
        },
    )
    avg_drop = sum(drops) / 2.0
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


def _remediation_entries(pf: Path) -> list[dict[str, object]]:
    data = json.loads((pf / "hotspots" / "14_remediation_priority_list.json").read_text(encoding="utf-8"))
    return data.get("entries", []) if isinstance(data, dict) else []


def test_remediation_stable_minimal(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, drops=[0.0, 0.0])
    pf = tmp_path / "proof" / "stable"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _remediation_entries(pf)
    assert entries == []


def test_remediation_priority_single_regression(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, drops=[0.17, 0.0])
    pf = tmp_path / "proof" / "single"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _remediation_entries(pf)
    assert len(entries) == 1
    assert str(entries[0].get("scenario_id", "")) == "fault_missing_dependency_decl"
    assert int(entries[0].get("priority_rank", 0)) == 1


def test_remediation_priority_multi_regression_order(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, drops=[0.17, 0.09])
    pf = tmp_path / "proof" / "multi"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _remediation_entries(pf)
    assert len(entries) >= 2
    assert str(entries[0].get("scenario_id", "")) == "fault_missing_dependency_decl"
    assert str(entries[1].get("scenario_id", "")) == "baseline_pass"
    assert int(entries[0].get("priority_rank", 0)) == 1
    assert int(entries[1].get("priority_rank", 0)) == 2
