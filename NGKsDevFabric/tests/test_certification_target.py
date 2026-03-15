from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certification_target import run_target_validation_precheck


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_target_contract(project_root: Path) -> Path:
    contract_path = project_root / "certification_target.json"
    _write_json(
        contract_path,
        {
            "project_name": "FixtureProject",
            "target_root": ".",
            "certification_root": "certification",
            "baseline_root": "certification/baseline_v1",
            "scenario_index_path": "certification/scenario_index.json",
            "supported_baseline_versions": ["v1"],
            "required_artifacts": [
                "baseline_manifest",
                "baseline_matrix",
                "diagnostic_metrics",
                "scenario_index",
            ],
            "optional_artifacts": ["compatibility_classification"],
            "target_type": "ngks_project",
            "schema_version": "certification_target_v1",
        },
    )
    return contract_path


def _make_target_layout(project_root: Path) -> None:
    baseline = project_root / "certification" / "baseline_v1"
    _write_json(baseline / "baseline_manifest.json", {"baseline_version": "v1"})
    _write_json(baseline / "baseline_matrix.json", {"scenarios": []})
    _write_json(
        baseline / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": 1.0,
            "average_component_ownership_accuracy": 1.0,
            "average_root_cause_accuracy": 1.0,
            "average_remediation_quality": 1.0,
            "average_proof_quality": 1.0,
            "average_diagnostic_score": 1.0,
        },
    )
    _write_json(project_root / "certification" / "scenario_index.json", {"scenario_ids": []})


def test_target_ready(tmp_path: Path) -> None:
    project_root = tmp_path / "project_ready"
    _make_target_layout(project_root)
    _make_target_contract(project_root)
    pf = tmp_path / "proof" / "target_ready"

    result = run_target_validation_precheck(project_root=project_root, pf=pf, require_contract=True)

    assert result.state in {"CERTIFICATION_READY", "CERTIFICATION_READY_WITH_WARNINGS"}
    assert (pf / "target_validation" / "00_target_inputs.json").is_file()
    assert (pf / "target_validation" / "04_target_capability_classification.json").is_file()


def test_target_not_ready_missing_contract(tmp_path: Path) -> None:
    project_root = tmp_path / "project_missing_contract"
    _make_target_layout(project_root)
    pf = tmp_path / "proof" / "target_missing_contract"

    result = run_target_validation_precheck(project_root=project_root, pf=pf, require_contract=True)

    assert result.state == "CERTIFICATION_NOT_READY"
    assert any("target_contract_missing" in item for item in result.errors)


def test_target_not_ready_missing_scenario_index(tmp_path: Path) -> None:
    project_root = tmp_path / "project_missing_scenario_index"
    _make_target_layout(project_root)
    _make_target_contract(project_root)
    (project_root / "certification" / "scenario_index.json").unlink()
    pf = tmp_path / "proof" / "target_missing_scenario_index"

    result = run_target_validation_precheck(project_root=project_root, pf=pf, require_contract=True)

    assert result.state == "CERTIFICATION_NOT_READY"
    assert any("missing_required_artifact:scenario_index" in item for item in result.errors)
