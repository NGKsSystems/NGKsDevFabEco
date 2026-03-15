from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric import certify_compare


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
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _states(path: Path) -> list[str]:
    payload = _load_json(path)
    rows = payload.get("rows", []) if isinstance(payload.get("rows", []), list) else []
    return [str(row.get("state", "")) for row in rows if isinstance(row, dict)]


def test_new_regression_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    current = _make_current(tmp_path / "run_one", [0.17, 0.0])
    pf = tmp_path / "proof" / "run_one"
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current,
        pf=pf,
        profile_project_root=project_root,
    )

    states = _states(pf / "resolution" / "70_regression_lifecycle_states.json")
    assert "NEW" in states


def test_recurring_regression_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    current1 = _make_current(tmp_path / "run_one", [0.17, 0.0])
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current1,
        pf=tmp_path / "proof" / "run_one",
        profile_project_root=project_root,
    )

    current2 = _make_current(tmp_path / "run_two", [0.17, 0.0])
    pf2 = tmp_path / "proof" / "run_two"
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current2,
        pf=pf2,
        profile_project_root=project_root,
    )

    states = _states(pf2 / "resolution" / "70_regression_lifecycle_states.json")
    assert "RECURRING" in states


def test_persistent_regression_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=_make_current(tmp_path / "run_one", [0.17, 0.0]),
        pf=tmp_path / "proof" / "run_one",
        profile_project_root=project_root,
    )
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=_make_current(tmp_path / "run_two", [0.17, 0.0]),
        pf=tmp_path / "proof" / "run_two",
        profile_project_root=project_root,
    )

    pf3 = tmp_path / "proof" / "run_three"
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=_make_current(tmp_path / "run_three", [0.17, 0.0]),
        pf=pf3,
        profile_project_root=project_root,
    )

    states = _states(pf3 / "resolution" / "70_regression_lifecycle_states.json")
    assert "PERSISTING" in states


def test_resolved_regression_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_profile(project_root, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")

    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=_make_current(tmp_path / "run_one", [0.17, 0.0]),
        pf=tmp_path / "proof" / "run_one",
        profile_project_root=project_root,
    )

    pf2 = tmp_path / "proof" / "run_two"
    certify_compare.run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=_make_current(tmp_path / "run_two", [0.0, 0.0]),
        pf=pf2,
        profile_project_root=project_root,
    )

    states = _states(pf2 / "resolution" / "70_regression_lifecycle_states.json")
    assert "RESOLVED" in states

    resolved = _load_json(pf2 / "resolution" / "72_resolved_regressions.json")
    resolved_rows = resolved.get("rows", []) if isinstance(resolved.get("rows", []), list) else []
    assert resolved_rows
    assert (pf2 / "resolution" / "71_component_resolution_metrics.json").is_file()
    assert (pf2 / "resolution" / "73_unresolved_regressions.json").is_file()
    assert (pf2 / "resolution" / "74_resolution_summary.md").is_file()
