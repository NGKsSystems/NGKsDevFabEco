from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric import main as fabric_main
from ngksdevfabric.ngk_fabric import predictive_risk


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_history(project_root: Path) -> Path:
    history_root = project_root / "devfabeco_history"

    runs = history_root / "runs"
    _write_json(runs / "run_000001.json", {"history_run_id": "run_000001", "regression_count": 1})
    _write_json(runs / "run_000002.json", {"history_run_id": "run_000002", "regression_count": 3})
    _write_json(runs / "run_000003.json", {"history_run_id": "run_000003", "regression_count": 4})

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_stable",
                    "scenario_id": "baseline_pass",
                    "metric": "diagnostic_score",
                    "component": "stable_component",
                    "severity_bucket": "LOW",
                    "occurrences": 1,
                    "first_seen_run": "run_000001",
                    "last_seen_run": "run_000001",
                },
                {
                    "fingerprint": "fp_unstable_1",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "detection_accuracy",
                    "component": "unstable_component",
                    "severity_bucket": "HIGH",
                    "occurrences": 8,
                    "first_seen_run": "run_000001",
                    "last_seen_run": "run_000003",
                },
                {
                    "fingerprint": "fp_unstable_2",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "component": "unstable_component",
                    "severity_bucket": "MEDIUM",
                    "occurrences": 6,
                    "first_seen_run": "run_000001",
                    "last_seen_run": "run_000003",
                },
            ]
        },
    )

    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                "stable_component": {
                    "component": "stable_component",
                    "total_regression_occurrences": 1,
                    "unique_fingerprints": 1,
                    "last_seen_run": "run_000001",
                },
                "unstable_component": {
                    "component": "unstable_component",
                    "total_regression_occurrences": 14,
                    "unique_fingerprints": 2,
                    "last_seen_run": "run_000003",
                },
            }
        },
    )

    trend_root = project_root / "_proof" / "runs" / "certification_compare_20260313_120000" / "history"
    _write_json(
        trend_root / "50_component_health_scores.json",
        {
            "rows": [
                {
                    "component": "stable_component",
                    "health_score": 0.92,
                    "health_class": "HEALTHY",
                    "regression_count": 1,
                    "recent_regressions": 0,
                    "recurrence_rate": 0.0,
                    "severity_distribution": 0.3,
                },
                {
                    "component": "unstable_component",
                    "health_score": 0.28,
                    "health_class": "CRITICAL",
                    "regression_count": 14,
                    "recent_regressions": 4,
                    "recurrence_rate": 0.857,
                    "severity_distribution": 0.82,
                },
            ]
        },
    )
    _write_json(trend_root / "51_component_regression_ranking.json", {"rows": []})
    _write_json(
        trend_root / "52_regression_trend_analysis.json",
        {
            "run_count": 3,
            "trend_classification": "RISING",
            "trend_reason": "latest_regression_count_above_baseline",
            "latest_run_id": "run_000003",
            "recurring_pattern_count": 2,
            "component_count": 2,
        },
    )
    _write_json(
        trend_root / "53_recurring_regression_patterns.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_unstable_1",
                    "component": "unstable_component",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "detection_accuracy",
                    "severity_bucket": "HIGH",
                    "occurrences": 8,
                    "last_seen_run": "run_000003",
                },
                {
                    "fingerprint": "fp_unstable_2",
                    "component": "unstable_component",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "severity_bucket": "MEDIUM",
                    "occurrences": 6,
                    "last_seen_run": "run_000003",
                },
            ]
        },
    )

    return trend_root


def _load_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def test_low_risk_component_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_history(project_root)

    manifest = tmp_path / "low_risk_manifest.json"
    _write_json(
        manifest,
        {
            "change_id": "pr_low",
            "project_name": "NGKsMediaLab",
            "touched_components": ["stable_component"],
            "touched_files": ["app/python_workers/stable.py"],
        },
    )

    pf = tmp_path / "proof" / "predict_low"
    result = predictive_risk.analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=manifest,
    )

    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    assert str(prediction.get("overall_risk_class", "")) in {"LOW", "MEDIUM"}
    assert (pf / "predictive" / "60_prediction_inputs.json").is_file()
    assert (pf / "predictive" / "61_component_risk_scores.json").is_file()
    assert (pf / "predictive" / "62_metric_risk_predictions.json").is_file()
    assert (pf / "predictive" / "63_recommended_validation_targets.json").is_file()
    assert (pf / "predictive" / "64_prediction_classification.json").is_file()
    assert (pf / "predictive" / "65_prediction_summary.md").is_file()


def test_repeated_regression_component_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_history(project_root)

    manifest = tmp_path / "high_risk_manifest.json"
    _write_json(
        manifest,
        {
            "change_id": "pr_high",
            "project_name": "NGKsMediaLab",
            "touched_components": ["unstable_component"],
            "touched_files": ["app/python_workers/scoring.py"],
        },
    )

    pf = tmp_path / "proof" / "predict_high"
    result = predictive_risk.analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=manifest,
    )

    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    assert str(prediction.get("overall_risk_class", "")) in {"HIGH", "CRITICAL"}
    assert str(prediction.get("highest_risk_component", "")) == "unstable_component"

    classification = _load_json(pf / "predictive" / "64_prediction_classification.json")
    recurrence_rows = classification.get("recurrence_evidence", []) if isinstance(classification.get("recurrence_evidence", []), list) else []
    assert recurrence_rows


def test_mixed_component_fixture_with_cli(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_history(project_root)

    manifest = tmp_path / "mixed_risk_manifest.json"
    _write_json(
        manifest,
        {
            "change_id": "pr_mixed",
            "project_name": "NGKsMediaLab",
            "touched_components": ["stable_component", "unstable_component"],
            "touched_files": ["app/python_workers/scoring.py", "app/python_workers/stable.py"],
        },
    )

    pf_name = "predict_mixed"
    code = fabric_main.main(
        [
            "predict-risk",
            "--project",
            str(project_root),
            "--change-manifest",
            str(manifest),
            "--pf",
            pf_name,
        ]
    )
    assert code == 0

    pf = fabric_main.DEVFABRIC_ROOT.parent.resolve() / "_proof" / "runs" / pf_name
    classification = _load_json(pf / "predictive" / "64_prediction_classification.json")
    prediction = classification.get("prediction", {}) if isinstance(classification.get("prediction", {}), dict) else {}
    scenarios = prediction.get("recommended_validation_scenarios", []) if isinstance(prediction.get("recommended_validation_scenarios", []), list) else []
    assert scenarios
    assert str(prediction.get("highest_risk_component", "")) == "unstable_component"
    assert str(prediction.get("overall_risk_class", "")) in {"MEDIUM", "HIGH", "CRITICAL"}
