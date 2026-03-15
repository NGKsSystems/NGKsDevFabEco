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


def test_small_profile_minimal_pipeline(tmp_path: Path) -> None:
    _write_profile(tmp_path, "SMALL")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "small"

    result = run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    assert result.get("execution_profile") == "SMALL"
    assert result.get("hotspot_artifacts", []) == []
    assert result.get("remediation_artifacts", []) == []
    assert result.get("ownership_artifacts", []) == []
    assert result.get("assignment_policy_artifacts", []) == []
    assert result.get("triage_artifacts", []) == []
    assert result.get("export_artifacts", []) == []
    assert result.get("delivery_artifacts", []) == []
    assert not (pf / "hotspots").exists()


def test_standard_profile_runs_through_exports(tmp_path: Path) -> None:
    _write_profile(tmp_path, "STANDARD")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "standard"

    result = run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    assert result.get("execution_profile") == "STANDARD"
    assert result.get("hotspot_artifacts", [])
    assert result.get("remediation_artifacts", [])
    assert result.get("ownership_artifacts", [])
    assert result.get("assignment_policy_artifacts", [])
    assert result.get("triage_artifacts", [])
    assert result.get("export_artifacts", [])
    assert result.get("delivery_artifacts", []) == []
    assert not (pf / "hotspots" / "29_github_delivery_payload.json").exists()


def test_enterprise_profile_runs_delivery(tmp_path: Path) -> None:
    _write_profile(tmp_path, "ENTERPRISE")
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "enterprise"

    result = run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    assert result.get("execution_profile") == "ENTERPRISE"
    assert result.get("export_artifacts", [])
    assert result.get("delivery_artifacts", [])
    assert (pf / "hotspots" / "29_github_delivery_payload.json").is_file()


def test_missing_profile_config_defaults_to_standard(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "default_standard"

    result = run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    assert result.get("execution_profile") == "STANDARD"
    assert result.get("export_artifacts", [])
    assert result.get("delivery_artifacts", []) == []
