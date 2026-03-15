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


def _write_profile(project_root: Path, profile_name: str = "STANDARD") -> None:
    _write_json(project_root / "devfabeco_profile.json", {"execution_profile": profile_name})


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def test_history_first_run_creates_store(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path / "run_one", [0.17, 0.0])
    pf = tmp_path / "proof" / "run_one"

    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current,
        pf=pf,
        profile_project_root=project_root,
    )

    run_record = _load_json(pf / "history" / "40_run_record.json")
    recurrence = _load_json(pf / "history" / "42_recurrence_matches.json")

    assert str(run_record.get("history_run_id", "")) == "run_000001"
    assert recurrence.get("rows", []) == []
    assert (project_root / "devfabeco_history" / "runs" / "run_000001.json").is_file()


def test_history_second_identical_run_increments_recurrence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    current1 = _make_current(tmp_path / "run_one", [0.17, 0.0])
    pf1 = tmp_path / "proof" / "run_one"
    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current1,
        pf=pf1,
        profile_project_root=project_root,
    )

    current2 = _make_current(tmp_path / "run_two", [0.17, 0.0])
    pf2 = tmp_path / "proof" / "run_two"
    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current2,
        pf=pf2,
        profile_project_root=project_root,
    )

    run_record = _load_json(pf2 / "history" / "40_run_record.json")
    recurrence = _load_json(pf2 / "history" / "42_recurrence_matches.json")
    rows = recurrence.get("rows", []) if isinstance(recurrence.get("rows", []), list) else []

    assert str(run_record.get("history_run_id", "")) == "run_000002"
    assert rows
    assert int((rows[0] if isinstance(rows[0], dict) else {}).get("occurrences", 0)) >= 2


def test_history_new_pattern_adds_fingerprint_without_recurrence(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    current1 = _make_current(tmp_path / "run_one", [0.17, 0.0])
    pf1 = tmp_path / "proof" / "run_one"
    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current1,
        pf=pf1,
        profile_project_root=project_root,
    )

    current3 = _make_current(tmp_path / "run_three", [0.0, 0.17])
    pf3 = tmp_path / "proof" / "run_three"
    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current3,
        pf=pf3,
        profile_project_root=project_root,
    )

    recurrence = _load_json(pf3 / "history" / "42_recurrence_matches.json")
    detected = _load_json(pf3 / "history" / "41_regression_fingerprints_detected.json")

    rows = recurrence.get("rows", []) if isinstance(recurrence.get("rows", []), list) else []
    detected_rows = detected.get("rows", []) if isinstance(detected.get("rows", []), list) else []
    assert detected_rows
    assert rows == []
