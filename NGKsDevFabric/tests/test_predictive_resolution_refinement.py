from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric import predictive_risk


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_inputs(
    *,
    project_root: Path,
    component: str,
    health_score: float,
    recent_regressions: int,
    occurrences: int,
    resolution_rate: float,
    mean_time_to_resolution: float,
    recurrence_rate: float,
    resolved_regressions: int,
    unresolved_regressions: int,
    persisting_count: int,
) -> None:
    history_root = project_root / "devfabeco_history"

    _write_json(history_root / "runs" / "run_000001.json", {"history_run_id": "run_000001", "regression_count": 2})
    _write_json(history_root / "runs" / "run_000002.json", {"history_run_id": "run_000002", "regression_count": 2})
    _write_json(history_root / "runs" / "run_000003.json", {"history_run_id": "run_000003", "regression_count": 2})

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": f"fp_{component}",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "component": component,
                    "severity_bucket": "HIGH",
                    "occurrences": occurrences,
                    "first_seen_run": "run_000001",
                    "last_seen_run": "run_000003",
                }
            ]
        },
    )
    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                component: {
                    "component": component,
                    "total_regression_occurrences": occurrences,
                    "unique_fingerprints": 1,
                    "last_seen_run": "run_000003",
                }
            }
        },
    )

    run_root = project_root / "_proof" / "runs" / "certification_compare_20260313_190000"
    trend_root = run_root / "history"
    _write_json(
        trend_root / "50_component_health_scores.json",
        {
            "rows": [
                {
                    "component": component,
                    "health_score": health_score,
                    "health_class": "CRITICAL" if health_score < 0.4 else "WATCH",
                    "regression_count": occurrences,
                    "recent_regressions": recent_regressions,
                    "recurrence_rate": 0.8,
                    "severity_distribution": 1.0,
                }
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
            "recurring_pattern_count": 1,
            "component_count": 1,
        },
    )
    _write_json(
        trend_root / "53_recurring_regression_patterns.json",
        {
            "rows": [
                {
                    "fingerprint": f"fp_{component}",
                    "component": component,
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "severity_bucket": "HIGH",
                    "occurrences": occurrences,
                    "last_seen_run": "run_000003",
                }
            ]
        },
    )

    resolution_root = run_root / "resolution"
    lifecycle_rows: list[dict[str, object]] = []
    for i in range(persisting_count):
        lifecycle_rows.append(
            {
                "fingerprint": f"fp_persist_{i}",
                "state": "PERSISTING",
                "component": component,
                "scenario_id": "fault_missing_dependency_decl",
                "metric": "diagnostic_score",
                "severity_bucket": "HIGH",
            }
        )
    _write_json(resolution_root / "70_regression_lifecycle_states.json", {"rows": lifecycle_rows})
    _write_json(
        resolution_root / "71_component_resolution_metrics.json",
        {
            "rows": [
                {
                    "component": component,
                    "resolution_rate": resolution_rate,
                    "mean_time_to_resolution": mean_time_to_resolution,
                    "recurrence_rate": recurrence_rate,
                    "resolved_regressions": resolved_regressions,
                    "unresolved_regressions": unresolved_regressions,
                    "known_fingerprints": 1,
                    "recurring_fingerprints": 1,
                }
            ]
        },
    )
    _write_json(
        resolution_root / "72_resolved_regressions.json",
        {"rows": [{"component": component, "fingerprint": f"fp_res_{i}"} for i in range(resolved_regressions)]},
    )
    _write_json(
        resolution_root / "73_unresolved_regressions.json",
        {"rows": [{"component": component, "fingerprint": f"fp_unres_{i}"} for i in range(unresolved_regressions)]},
    )


def _manifest(path: Path, component: str) -> Path:
    payload = {
        "change_id": f"pr_{component}",
        "project_name": "NGKsMediaLab",
        "touched_components": [component],
        "touched_files": [f"src/{component}.py"],
    }
    _write_json(path, payload)
    return path


def test_high_resolution_component_refines_down(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    component = "high_resolution_component"
    _seed_inputs(
        project_root=project_root,
        component=component,
        health_score=0.30,
        recent_regressions=4,
        occurrences=8,
        resolution_rate=0.90,
        mean_time_to_resolution=1.0,
        recurrence_rate=0.80,
        resolved_regressions=9,
        unresolved_regressions=1,
        persisting_count=0,
    )

    pf = tmp_path / "proof" / "high_resolution"
    result = predictive_risk.analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=_manifest(tmp_path / "high_resolution_manifest.json", component),
    )

    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    base = float(prediction.get("overall_risk_score", 0.0))
    refined = float(prediction.get("resolution_adjusted_risk_score", 0.0))

    assert str(prediction.get("overall_risk_class", "")) in {"HIGH", "CRITICAL"}
    assert refined < base
    assert (pf / "predictive" / "66_resolution_adjusted_risk.json").is_file()
    assert (pf / "predictive" / "67_resolution_context.json").is_file()
    assert (pf / "predictive" / "68_resolution_risk_adjustments.json").is_file()
    assert (pf / "predictive" / "69_predictive_refinement_summary.md").is_file()


def test_unresolved_regression_component_refines_up(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    component = "unresolved_regression_component"
    _seed_inputs(
        project_root=project_root,
        component=component,
        health_score=0.28,
        recent_regressions=4,
        occurrences=9,
        resolution_rate=0.10,
        mean_time_to_resolution=6.0,
        recurrence_rate=0.90,
        resolved_regressions=1,
        unresolved_regressions=9,
        persisting_count=2,
    )

    pf = tmp_path / "proof" / "unresolved_component"
    result = predictive_risk.analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=_manifest(tmp_path / "unresolved_manifest.json", component),
    )

    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    base = float(prediction.get("overall_risk_score", 0.0))
    refined = float(prediction.get("resolution_adjusted_risk_score", 0.0))

    assert str(prediction.get("overall_risk_class", "")) in {"HIGH", "CRITICAL"}
    assert refined > base
    assert bool(prediction.get("persistent_regression_warning", False)) is True


def test_stable_component_refinement_is_flat_or_down(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    component = "stable_component"
    _seed_inputs(
        project_root=project_root,
        component=component,
        health_score=0.90,
        recent_regressions=0,
        occurrences=1,
        resolution_rate=0.95,
        mean_time_to_resolution=1.0,
        recurrence_rate=0.10,
        resolved_regressions=6,
        unresolved_regressions=0,
        persisting_count=0,
    )

    pf = tmp_path / "proof" / "stable_component"
    result = predictive_risk.analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=_manifest(tmp_path / "stable_manifest.json", component),
    )

    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    base = float(prediction.get("overall_risk_score", 0.0))
    refined = float(prediction.get("resolution_adjusted_risk_score", 0.0))

    assert str(prediction.get("overall_risk_class", "")) in {"LOW", "MEDIUM"}
    assert refined <= base
    assert float(prediction.get("historical_fix_success_rate", 0.0)) >= 0.80
