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


def _ownership_entries(pf: Path) -> list[dict[str, object]]:
    data = json.loads((pf / "hotspots" / "16_ownership_confidence.json").read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    return entries if isinstance(entries, list) else []


def test_ownership_stable_minimal(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.0, 0.0])
    pf = tmp_path / "proof" / "stable"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _ownership_entries(pf)
    assert entries == []


def test_ownership_single_has_confidence(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.0])
    pf = tmp_path / "proof" / "single"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _ownership_entries(pf)
    assert len(entries) == 1
    entry = entries[0]
    assert str(entry.get("scenario_id", "")) == "fault_missing_dependency_decl"
    assert float(entry.get("confidence_score", 0.0)) >= 0.5
    assert str(entry.get("confidence_level", "")) in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"}
    assert entry.get("evidence_artifacts", [])


def test_ownership_multi_ordering(tmp_path: Path) -> None:
    baseline = _make_baseline(tmp_path / "baseline")
    current = _make_current(tmp_path, [0.17, 0.09])
    pf = tmp_path / "proof" / "multi"

    run_certification_comparison(repo_root=tmp_path, baseline_path=baseline, current_path=current, pf=pf)

    entries = _ownership_entries(pf)
    assert len(entries) >= 2
    assert int(entries[0].get("priority_rank", 0)) == 1
    assert int(entries[1].get("priority_rank", 0)) == 2
