from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certification_rollup import run_subtarget_rollup_comparison, run_subtarget_rollup_gate
from ngksdevfabric.ngk_fabric.certification_target import run_target_validation_precheck
from ngksdevfabric.ngk_fabric.certify_compare import ComparisonPolicy, run_certification_comparison
from ngksdevfabric.ngk_fabric.certify_gate import GateEnforcementPolicy


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_baseline(root: Path, score: float) -> Path:
    baseline = root / "certification" / "baseline_v1"
    _write_json(
        baseline / "baseline_manifest.json",
        {
            "baseline_version": "v1",
            "scenario_count": 1,
        },
    )
    _write_json(
        baseline / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": score,
            "average_component_ownership_accuracy": score,
            "average_root_cause_accuracy": score,
            "average_remediation_quality": score,
            "average_proof_quality": score,
            "average_diagnostic_score": score,
        },
    )
    _write_json(
        baseline / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": score,
                    "scores": {
                        "detection_accuracy": score,
                        "component_ownership_accuracy": score,
                        "root_cause_accuracy": score,
                        "remediation_quality": score,
                        "proof_quality": score,
                    },
                }
            ]
        },
    )
    _write_json(root / "certification" / "scenario_index.json", {"scenario_ids": ["baseline_pass"]})
    return baseline


def _make_current(root: Path, score: float, version: str = "current_run") -> None:
    _write_json(root / "baseline_manifest.json", {"baseline_version": version, "scenario_count": 1})
    _write_json(
        root / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": score,
            "average_component_ownership_accuracy": score,
            "average_root_cause_accuracy": score,
            "average_remediation_quality": score,
            "average_proof_quality": score,
            "average_diagnostic_score": score,
        },
    )
    _write_json(
        root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": score,
                    "scores": {
                        "detection_accuracy": score,
                        "component_ownership_accuracy": score,
                        "root_cause_accuracy": score,
                        "remediation_quality": score,
                        "proof_quality": score,
                    },
                }
            ]
        },
    )


def _make_subtarget(project_root: Path, subtarget_id: str, baseline_score: float, current_score: float) -> Path:
    subtarget_root = project_root / subtarget_id
    _make_baseline(subtarget_root, baseline_score)
    _make_current(subtarget_root, current_score)
    return subtarget_root


def _write_subtarget_contract(project_root: Path, subtargets: list[dict[str, object]]) -> None:
    _write_json(
        project_root / "certification_target.json",
        {
            "project_name": "RollupFixture",
            "target_root": ".",
            "certification_root": "certification",
            "baseline_root": "certification/baseline_v1",
            "scenario_index_path": "certification/scenario_index.json",
            "supported_baseline_versions": ["v1", "current_run"],
            "required_artifacts": [
                "baseline_manifest",
                "baseline_matrix",
                "diagnostic_metrics",
                "scenario_index",
            ],
            "optional_artifacts": [],
            "target_type": "ngks_project",
            "schema_version": "certification_target_v1",
            "subtargets": subtargets,
        },
    )


def test_single_target_backward_compat(tmp_path: Path) -> None:
    project_root = tmp_path / "single"
    baseline = _make_baseline(project_root, 0.9)
    _make_current(project_root, 0.9)

    result = run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=project_root,
        pf=tmp_path / "proof" / "single_target",
        policy=ComparisonPolicy(),
        profile_project_root=project_root,
    )

    assert result.get("classification") in {"STABLE", "UNCHANGED"}
    assert result.get("gate") == "PASS"


def test_two_subtarget_fixture_stable(tmp_path: Path) -> None:
    project_root = tmp_path / "two_stable"
    (project_root / "certification").mkdir(parents=True, exist_ok=True)
    _make_subtarget(project_root, "core", 0.9, 0.9)
    _make_subtarget(project_root, "panel", 0.9, 0.9)

    _write_subtarget_contract(
        project_root,
        [
            {"subtarget_id": "core", "target_root": "core", "baseline_root": "certification/baseline_v1", "required": True},
            {"subtarget_id": "panel", "target_root": "panel", "baseline_root": "certification/baseline_v1", "required": True},
        ],
    )

    target = run_target_validation_precheck(project_root=project_root, pf=tmp_path / "proof" / "target_two")
    result = run_subtarget_rollup_gate(
        repo_root=tmp_path,
        project_root=project_root,
        pf=tmp_path / "proof" / "rollup_two",
        target_result=target,
        comparison_policy=ComparisonPolicy(),
        enforcement_policy=GateEnforcementPolicy(),
    )

    assert result.get("decision") == "CERTIFIED_STABLE"
    assert result.get("enforced_gate") == "PASS"


def test_mixed_subtarget_fixture_required_regression(tmp_path: Path) -> None:
    project_root = tmp_path / "mixed_required"
    (project_root / "certification").mkdir(parents=True, exist_ok=True)
    _make_subtarget(project_root, "core", 0.9, 0.9)
    _make_subtarget(project_root, "panel", 0.9, 0.6)

    _write_subtarget_contract(
        project_root,
        [
            {"subtarget_id": "core", "target_root": "core", "baseline_root": "certification/baseline_v1", "required": True},
            {"subtarget_id": "panel", "target_root": "panel", "baseline_root": "certification/baseline_v1", "required": True},
        ],
    )

    target = run_target_validation_precheck(project_root=project_root, pf=tmp_path / "proof" / "target_mixed")
    result = run_subtarget_rollup_gate(
        repo_root=tmp_path,
        project_root=project_root,
        pf=tmp_path / "proof" / "rollup_mixed",
        target_result=target,
        comparison_policy=ComparisonPolicy(),
        enforcement_policy=GateEnforcementPolicy(),
    )

    assert result.get("decision") == "CERTIFIED_REGRESSION"
    assert result.get("enforced_gate") == "FAIL"


def test_optional_subtarget_warning_fixture_non_blocking(tmp_path: Path) -> None:
    project_root = tmp_path / "optional_warning"
    (project_root / "certification").mkdir(parents=True, exist_ok=True)
    _make_subtarget(project_root, "core", 0.9, 0.9)

    # optional subtarget intentionally incomplete
    optional_root = project_root / "optional_panel"
    optional_root.mkdir(parents=True, exist_ok=True)

    _write_subtarget_contract(
        project_root,
        [
            {"subtarget_id": "core", "target_root": "core", "baseline_root": "certification/baseline_v1", "required": True},
            {
                "subtarget_id": "optional_panel",
                "target_root": "optional_panel",
                "baseline_root": "certification/baseline_v1",
                "required": False,
            },
        ],
    )

    target = run_target_validation_precheck(project_root=project_root, pf=tmp_path / "proof" / "target_optional")
    assert target.state in {"CERTIFICATION_READY", "CERTIFICATION_READY_WITH_WARNINGS"}

    compare = run_subtarget_rollup_comparison(
        repo_root=tmp_path,
        project_root=project_root,
        pf=tmp_path / "proof" / "rollup_optional_compare",
        target_result=target,
        comparison_policy=ComparisonPolicy(),
    )
    gate = run_subtarget_rollup_gate(
        repo_root=tmp_path,
        project_root=project_root,
        pf=tmp_path / "proof" / "rollup_optional_gate",
        target_result=target,
        comparison_policy=ComparisonPolicy(),
        enforcement_policy=GateEnforcementPolicy(),
    )

    assert compare.get("compatibility_state") == "COMPATIBLE_WITH_WARNINGS"
    assert gate.get("enforced_gate") == "PASS"
