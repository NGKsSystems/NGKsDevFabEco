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
                    "scenario_id": "s1",
                    "scenario_name": "Scenario 1",
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
                    "scenario_id": "s2",
                    "scenario_name": "Scenario 2",
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


def _make_current(root: Path, *, s1_drop: float, s2_drop: float) -> Path:
    current = root / "current"

    s1_score = round(0.9 - s1_drop, 4)
    s2_score = round(0.9 - s2_drop, 4)

    _write_json(
        current / "baseline_manifest.json",
        {
            "baseline_version": "current_run",
            "creation_timestamp": "2026-03-13T00:00:00+00:00",
            "scenario_count": 2,
            "notes": [],
        },
    )
    _write_json(
        current / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": round((1.0 - s1_drop + 1.0 - s2_drop) / 2.0, 4),
            "average_component_ownership_accuracy": round((1.0 - s1_drop + 1.0 - s2_drop) / 2.0, 4),
            "average_root_cause_accuracy": round((1.0 - s1_drop + 1.0 - s2_drop) / 2.0, 4),
            "average_remediation_quality": round((1.0 - s1_drop + 1.0 - s2_drop) / 2.0, 4),
            "average_proof_quality": round((1.0 - s1_drop + 1.0 - s2_drop) / 2.0, 4),
            "average_diagnostic_score": round((s1_score + s2_score) / 2.0, 4),
        },
    )
    _write_json(
        current / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "s1",
                    "scenario_name": "Scenario 1",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": s1_score,
                    "scores": {
                        "detection_accuracy": round(1.0 - s1_drop, 4),
                        "component_ownership_accuracy": round(1.0 - s1_drop, 4),
                        "root_cause_accuracy": round(1.0 - s1_drop, 4),
                        "remediation_quality": round(1.0 - s1_drop, 4),
                        "proof_quality": round(1.0 - s1_drop, 4),
                    },
                },
                {
                    "scenario_id": "s2",
                    "scenario_name": "Scenario 2",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": s2_score,
                    "scores": {
                        "detection_accuracy": round(1.0 - s2_drop, 4),
                        "component_ownership_accuracy": round(1.0 - s2_drop, 4),
                        "root_cause_accuracy": round(1.0 - s2_drop, 4),
                        "remediation_quality": round(1.0 - s2_drop, 4),
                        "proof_quality": round(1.0 - s2_drop, 4),
                    },
                },
            ]
        },
    )
    return current


def _scenario_rows(pf: Path) -> list[dict[str, object]]:
    data = json.loads((pf / "hotspots" / "10_scenario_regression_ranking.json").read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    return rows if isinstance(rows, list) else []


def test_hotspot_stable_near_zero(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, s1_drop=0.0, s2_drop=0.0)
    pf = tmp_path / "proof" / "stable_case"

    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current,
        pf=pf,
    )

    rows = _scenario_rows(pf)
    assert rows
    assert float(rows[0].get("severity_score", 1.0)) == 0.0


def test_hotspot_single_regression_rank1(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, s1_drop=0.0, s2_drop=0.2)
    pf = tmp_path / "proof" / "single_regression_case"

    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current,
        pf=pf,
    )

    rows = _scenario_rows(pf)
    assert rows
    assert str(rows[0].get("scenario_id", "")) == "s2"
    assert float(rows[0].get("severity_score", 0.0)) > 0.0


def test_hotspot_multi_regression_ranking(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, s1_drop=0.1, s2_drop=0.2)
    pf = tmp_path / "proof" / "multi_regression_case"

    run_certification_comparison(
        repo_root=tmp_path,
        baseline_path=baseline,
        current_path=current,
        pf=pf,
    )

    rows = _scenario_rows(pf)
    assert len(rows) >= 2
    assert str(rows[0].get("scenario_id", "")) == "s2"
    assert str(rows[1].get("scenario_id", "")) == "s1"
