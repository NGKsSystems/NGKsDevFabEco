from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.certify_compare import ComparisonPolicy, run_certification_comparison


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
            "average_diagnostic_score": 0.5,
        },
    )
    _write_json(
        baseline / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "s1",
                    "scenario_name": "Scenario 1",
                    "expected_gate": "FAIL",
                    "actual_gate": "FAIL",
                    "diagnostic_score": 0.5,
                    "scores": {
                        "detection_accuracy": 1,
                        "component_ownership_accuracy": 1,
                        "root_cause_accuracy": 1,
                        "remediation_quality": 1,
                        "proof_quality": 1,
                    },
                },
                {
                    "scenario_id": "s2",
                    "scenario_name": "Scenario 2",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": 0.5,
                    "scores": {
                        "detection_accuracy": 1,
                        "component_ownership_accuracy": 1,
                        "root_cause_accuracy": 1,
                        "remediation_quality": 1,
                        "proof_quality": 1,
                    },
                },
            ]
        },
    )
    return baseline


def _make_current_from_scenarios(project_root: Path, include_s2: bool = True) -> Path:
    proof_root = project_root / "certification" / "_proof"

    def make_packet(stamp: str, scenario_id: str, expected_gate: str, actual_gate: str, score_total: int) -> None:
        packet = proof_root / f"{stamp}_{scenario_id}"
        _write_json(
            packet / "00_scenario_manifest.json",
            {
                "scenario_id": scenario_id,
                "scenario_name": scenario_id,
                "expected_gate": expected_gate,
            },
        )
        _write_json(
            packet / "05_actual_outcome.json",
            {
                "scenario_id": scenario_id,
                "actual_result": actual_gate,
            },
        )
        _write_json(
            packet / "06_diagnostic_scorecard.json",
            {
                "detection_accuracy": {"score": 2, "max": 2},
                "component_ownership_accuracy": {"score": 2, "max": 2},
                "root_cause_accuracy": {"score": 2, "max": 2},
                "remediation_quality": {"score": 2, "max": 2},
                "proof_quality": {"score": 2, "max": 2},
                "total": score_total,
                "max_total": 10,
            },
        )

    make_packet("20260313_100000", "s1", "FAIL", "FAIL", 8)
    if include_s2:
        make_packet("20260313_100100", "s2", "PASS", "PASS", 9)

    return project_root


def _make_current_aggregate(root: Path, *, omit_metric_key: str | None = None) -> Path:
    metrics = {
        "average_detection_accuracy": 1.0,
        "average_component_ownership_accuracy": 1.0,
        "average_root_cause_accuracy": 1.0,
        "average_remediation_quality": 1.0,
        "average_proof_quality": 1.0,
        "average_diagnostic_score": 0.6,
    }
    if omit_metric_key:
        metrics.pop(omit_metric_key, None)

    _write_json(
        root / "baseline_manifest.json",
        {
            "baseline_version": "current_run",
            "creation_timestamp": "2026-03-13T00:00:00+00:00",
            "scenario_count": 2,
            "notes": [],
        },
    )
    _write_json(root / "diagnostic_metrics.json", metrics)
    _write_json(
        root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "s1",
                    "scenario_name": "Scenario 1",
                    "expected_gate": "FAIL",
                    "actual_gate": "FAIL",
                    "diagnostic_score": 0.6,
                    "scores": {
                        "detection_accuracy": 1,
                        "component_ownership_accuracy": 1,
                        "root_cause_accuracy": 1,
                        "remediation_quality": 1,
                        "proof_quality": 1,
                    },
                },
                {
                    "scenario_id": "s2",
                    "scenario_name": "Scenario 2",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": 0.6,
                    "scores": {
                        "detection_accuracy": 1,
                        "component_ownership_accuracy": 1,
                        "root_cause_accuracy": 1,
                        "remediation_quality": 1,
                        "proof_quality": 1,
                    },
                },
            ]
        },
    )
    return root


def test_certification_compare_improved(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "source")
    current_project = _make_current_from_scenarios(tmp_path / "current", include_s2=True)
    pf = tmp_path / "proof" / "cert_compare_20260313_101010"

    result = run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current_project,
        pf=pf,
        policy=ComparisonPolicy(diagnostic_score_tolerance=0.01, diagnostic_score_improvement_threshold=0.02, severe_core_drop_threshold=0.5),
    )

    assert result["classification"] == "IMPROVED"
    assert result["certification_decision"] == "CERTIFIED_IMPROVEMENT"
    assert result["gate"] == "PASS"
    assert result["compatibility_state"] in {"COMPATIBLE", "COMPATIBLE_WITH_WARNINGS"}
    assert (pf / "07_certification_report.md").is_file()
    assert (pf / "05_scenario_diff.json").is_file()
    assert (pf / "09_decision_policy.json").is_file()
    assert (pf / "10_decision_evaluation.json").is_file()
    assert (pf / "11_regression_hotspots.json").is_file()
    assert (pf / "12_certification_decision.md").is_file()
    assert (pf / "compatibility" / "00_compatibility_inputs.json").is_file()
    assert (pf / "compatibility" / "07_compatibility_classification.json").is_file()
    assert (pf / "compatibility" / "08_compatibility_report.md").is_file()


def test_certification_compare_inconclusive_on_missing_scenarios(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "source")
    current_project = _make_current_from_scenarios(tmp_path / "current", include_s2=False)
    pf = tmp_path / "proof" / "cert_compare_20260313_111111"

    result = run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current_project,
        pf=pf,
    )

    assert result["classification"] == "INCONCLUSIVE"
    assert result["certification_decision"] == "CERTIFICATION_INCONCLUSIVE"
    assert result["gate"] == "FAIL"
    classification = json.loads((pf / "06_classification.json").read_text(encoding="utf-8"))
    assert any("missing_scenarios_in_current" in item for item in classification.get("validation_errors", []))


def test_certification_compare_incompatible_missing_metric_fixture(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "source")
    current_bundle = _make_current_aggregate(tmp_path / "current_aggregate", omit_metric_key="average_proof_quality")
    pf = tmp_path / "proof" / "cert_compare_20260313_121212"

    result = run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current_bundle,
        pf=pf,
    )

    assert result["compatibility_state"] == "INCOMPATIBLE"
    assert result["certification_decision"] == "CERTIFICATION_INCONCLUSIVE"
    assert result["gate"] == "FAIL"
    assert any("current_missing_metric_key:average_proof_quality" in item for item in result.get("compatibility_errors", []))


def test_certification_compare_incompatible_unsupported_baseline_version(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "source")
    manifest_path = baseline / "baseline_manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["baseline_version"] = "v9_unsupported"
    _write_json(manifest_path, manifest_data)

    current_bundle = _make_current_aggregate(tmp_path / "current_aggregate")
    pf = tmp_path / "proof" / "cert_compare_20260313_131313"

    result = run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current_bundle,
        pf=pf,
    )

    assert result["compatibility_state"] == "INCOMPATIBLE"
    assert result["certification_decision"] == "CERTIFICATION_INCONCLUSIVE"
    assert result["gate"] == "FAIL"
    assert any("unsupported_baseline_version" in item for item in result.get("compatibility_errors", []))
