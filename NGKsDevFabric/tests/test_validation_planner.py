from __future__ import annotations

import json
from pathlib import Path

import pytest

from ngksdevfabric.ngk_fabric.main import DEVFABRIC_ROOT, main
from ngksdevfabric.ngk_fabric.validation_planner import plan_premerge_validation


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    history_root = project_root / "devfabeco_history"
    runs_root = project_root / "_proof" / "runs"

    (history_root / "components").mkdir(parents=True, exist_ok=True)
    (history_root / "regressions").mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)

    (history_root / "components" / "component_regression_stats.json").write_text(
        json.dumps(
            {
                "components": {
                    "stable": {"total_regression_occurrences": 12},
                    "unstable": {"total_regression_occurrences": 24},
                    "platform": {"total_regression_occurrences": 20},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (history_root / "regressions" / "regression_fingerprints.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"scenario_id": "S_LOGIN", "component": "stable"},
                    {"scenario_id": "S_EXPORT", "component": "unstable"},
                    {"scenario_id": "S_MIXED", "component": "stable"},
                    {"scenario_id": "S_MIXED", "component": "unstable"},
                    {"scenario_id": "S_PLATFORM", "component": "platform"},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    evidence_run = runs_root / "certification_compare_20260314_100000"
    (evidence_run / "intelligence").mkdir(parents=True, exist_ok=True)
    (evidence_run / "resolution").mkdir(parents=True, exist_ok=True)
    (evidence_run / "history").mkdir(parents=True, exist_ok=True)

    (evidence_run / "intelligence" / "110_component_watchlist.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"component": "stable", "watch_class": "NORMAL"},
                    {"component": "unstable", "watch_class": "HOT"},
                    {"component": "platform", "watch_class": "CRITICAL"},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (evidence_run / "intelligence" / "111_regression_pattern_memory.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"scenario_id": "S_EXPORT", "recurring_count": 8},
                    {"scenario_id": "S_LOGIN", "recurring_count": 2},
                    {"scenario_id": "S_PLATFORM", "recurring_count": 10},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (evidence_run / "intelligence" / "112_scenario_detection_value.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"scenario_id": "S_LOGIN", "severity_weighted_score": 1.0},
                    {"scenario_id": "S_EXPORT", "severity_weighted_score": 8.0},
                    {"scenario_id": "S_MIXED", "severity_weighted_score": 5.0},
                    {"scenario_id": "S_PLATFORM", "severity_weighted_score": 9.0},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (evidence_run / "intelligence" / "113_remediation_effectiveness.json").write_text(
        json.dumps({"rows": []}, indent=2),
        encoding="utf-8",
    )

    (evidence_run / "resolution" / "71_component_resolution_metrics.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"component": "stable", "unresolved_ratio": 0.05},
                    {"component": "unstable", "unresolved_ratio": 0.65},
                    {"component": "platform", "unresolved_ratio": 0.80},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (evidence_run / "history" / "53_recurring_regression_patterns.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"component": "stable", "occurrences": 2},
                    {"component": "unstable", "occurrences": 12},
                    {"component": "platform", "occurrences": 16},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    predictive_run = runs_root / "predictive_risk_20260314_100500"
    (predictive_run / "predictive").mkdir(parents=True, exist_ok=True)
    (predictive_run / "predictive" / "61_component_risk_scores.json").write_text(
        json.dumps(
            {
                "rows": [
                    {"component": "stable", "risk_score": 0.10},
                    {"component": "unstable", "risk_score": 0.84},
                    {"component": "platform", "risk_score": 0.92},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (predictive_run / "predictive" / "64_prediction_classification.json").write_text(
        json.dumps({"prediction": {"overall_risk_class": "HIGH"}}, indent=2),
        encoding="utf-8",
    )

    return project_root


def test_plan_validation_low_risk_fixture(seeded_project: Path, tmp_path: Path) -> None:
    pf = tmp_path / "pf_low"

    result = plan_premerge_validation(
        project_root=seeded_project,
        pf=pf,
        touched_components=["stable"],
    )

    assert result["plan"]["plan_class"] in {"MINIMAL", "STANDARD"}
    assert result["plan"]["required_scenario_count"] <= 1



def test_plan_validation_chronic_fixture(seeded_project: Path, tmp_path: Path) -> None:
    pf = tmp_path / "pf_chronic"

    result = plan_premerge_validation(
        project_root=seeded_project,
        pf=pf,
        touched_components=["unstable"],
    )

    assert result["plan"]["plan_class"] in {"HEIGHTENED", "CRITICAL"}
    ranking = json.loads((pf / "planning" / "121_scenario_plan_ranking.json").read_text(encoding="utf-8"))
    top = ranking["rows"][0]
    assert top["scenario_id"] == "S_EXPORT"
    assert top["required"] is True



def test_plan_validation_mixed_fixture(seeded_project: Path, tmp_path: Path) -> None:
    pf = tmp_path / "pf_mixed"

    result = plan_premerge_validation(
        project_root=seeded_project,
        pf=pf,
        touched_components=["stable", "unstable"],
    )

    assert result["plan"]["plan_class"] in {"STANDARD", "HEIGHTENED", "CRITICAL"}
    plan_sets = json.loads((pf / "planning" / "122_required_vs_optional_plan.json").read_text(encoding="utf-8"))
    assert len(plan_sets["required"]) >= 1
    assert len(plan_sets["optional"]) >= 1



def test_plan_validation_recurring_scenario_fixture(seeded_project: Path, tmp_path: Path) -> None:
    pf = tmp_path / "pf_recurring"

    result = plan_premerge_validation(
        project_root=seeded_project,
        pf=pf,
        touched_components=["platform"],
    )

    assert result["plan"]["plan_class"] in {"HEIGHTENED", "CRITICAL"}
    ranking = json.loads((pf / "planning" / "121_scenario_plan_ranking.json").read_text(encoding="utf-8"))
    top = ranking["rows"][0]
    assert top["scenario_id"] == "S_PLATFORM"
    assert top["required"] is True



def test_plan_validation_cli_entrypoint(seeded_project: Path, tmp_path: Path) -> None:
    pf = tmp_path / "pf_cli"
    rc = main(
        [
            "plan-validation",
            "--project",
            str(seeded_project),
            "--component",
            "unstable",
            "--pf",
            str(pf),
        ]
    )
    assert rc == 0
    expected_pf = (DEVFABRIC_ROOT.parent.resolve() / "_proof" / "runs" / "pf_cli")
    assert (expected_pf / "planning" / "124_plan_classification.json").is_file()
