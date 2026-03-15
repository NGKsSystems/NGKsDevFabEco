from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.regression_intelligence import analyze_regression_intelligence


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_common_layout(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    history_root = project_root / "devfabeco_history"
    pf = tmp_path / "proof" / "intelligence"

    _write_json(history_root / "runs" / "run_000001.json", {"history_run_id": "run_000001", "regression_count": 1})
    _write_json(history_root / "runs" / "run_000002.json", {"history_run_id": "run_000002", "regression_count": 2})

    _write_json(pf / "history" / "50_component_health_scores.json", {"rows": []})
    _write_json(pf / "history" / "53_recurring_regression_patterns.json", {"rows": []})
    _write_json(pf / "resolution" / "70_regression_lifecycle_states.json", {"rows": []})
    _write_json(pf / "resolution" / "71_component_resolution_metrics.json", {"rows": []})
    _write_json(pf / "hotspots" / "13_remediation_guidance.json", {"entries": []})

    return history_root, pf


def test_minimal_learning_history(tmp_path: Path) -> None:
    history_root, pf = _seed_common_layout(tmp_path)

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_one",
                    "scenario_id": "baseline_pass",
                    "metric": "diagnostic_score",
                    "component": "component_a",
                    "severity_bucket": "LOW",
                    "occurrences": 1,
                }
            ]
        },
    )
    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                "component_a": {
                    "component": "component_a",
                    "total_regression_occurrences": 1,
                    "unique_fingerprints": 1,
                    "last_seen_run": "run_000002",
                }
            }
        },
    )

    result = analyze_regression_intelligence(history_root=history_root, pf=pf)

    watchlist = json.loads((pf / "intelligence" / "110_component_watchlist.json").read_text(encoding="utf-8"))
    rows = watchlist.get("rows", []) if isinstance(watchlist.get("rows", []), list) else []

    assert result.get("summary", {}).get("insufficient_history", False) is True
    assert rows
    assert str((rows[0] if isinstance(rows[0], dict) else {}).get("watch_class", "")) == "NORMAL"
    assert (pf / "intelligence" / "114_intelligence_summary.md").is_file()


def test_chronic_component_fixture(tmp_path: Path) -> None:
    history_root, pf = _seed_common_layout(tmp_path)

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_chronic",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "component": "diagnostic_scoring_pipeline",
                    "severity_bucket": "HIGH",
                    "occurrences": 8,
                },
                {
                    "fingerprint": "fp_chronic_2",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "detection_accuracy",
                    "component": "diagnostic_scoring_pipeline",
                    "severity_bucket": "HIGH",
                    "occurrences": 5,
                },
            ]
        },
    )
    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                "diagnostic_scoring_pipeline": {
                    "component": "diagnostic_scoring_pipeline",
                    "total_regression_occurrences": 13,
                    "unique_fingerprints": 2,
                    "last_seen_run": "run_000002",
                }
            }
        },
    )

    _write_json(
        pf / "history" / "50_component_health_scores.json",
        {
            "rows": [
                {
                    "component": "diagnostic_scoring_pipeline",
                    "health_score": 0.20,
                    "health_class": "CRITICAL",
                    "regression_count": 13,
                    "recent_regressions": 4,
                    "recurrence_rate": 0.8,
                    "severity_distribution": 1.0,
                }
            ]
        },
    )
    _write_json(
        pf / "resolution" / "71_component_resolution_metrics.json",
        {
            "rows": [
                {
                    "component": "diagnostic_scoring_pipeline",
                    "resolution_rate": 0.20,
                    "mean_time_to_resolution": 6.0,
                    "recurrence_rate": 0.80,
                    "resolved_regressions": 2,
                    "unresolved_regressions": 8,
                }
            ]
        },
    )
    _write_json(
        pf / "resolution" / "70_regression_lifecycle_states.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_chronic",
                    "state": "PERSISTING",
                    "component": "diagnostic_scoring_pipeline",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "streak_before_current": 3,
                }
            ]
        },
    )

    analyze_regression_intelligence(history_root=history_root, pf=pf)

    watchlist = json.loads((pf / "intelligence" / "110_component_watchlist.json").read_text(encoding="utf-8"))
    pattern = json.loads((pf / "intelligence" / "111_regression_pattern_memory.json").read_text(encoding="utf-8"))

    rows = watchlist.get("rows", []) if isinstance(watchlist.get("rows", []), list) else []
    top = rows[0] if rows and isinstance(rows[0], dict) else {}
    assert str(top.get("watch_class", "")) in {"HOT", "CRITICAL"}

    repeated = pattern.get("top_repeated_fingerprints", []) if isinstance(pattern.get("top_repeated_fingerprints", []), list) else []
    assert repeated
    assert str((repeated[0] if isinstance(repeated[0], dict) else {}).get("fingerprint", "")).startswith("fp_chronic")


def test_effective_detection_scenario_fixture(tmp_path: Path) -> None:
    history_root, pf = _seed_common_layout(tmp_path)

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_scenario_top_1",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "component": "component_a",
                    "severity_bucket": "HIGH",
                    "occurrences": 5,
                },
                {
                    "fingerprint": "fp_scenario_top_2",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "root_cause_accuracy",
                    "component": "component_b",
                    "severity_bucket": "HIGH",
                    "occurrences": 4,
                },
                {
                    "fingerprint": "fp_lower",
                    "scenario_id": "baseline_pass",
                    "metric": "proof_quality",
                    "component": "component_c",
                    "severity_bucket": "LOW",
                    "occurrences": 1,
                },
            ]
        },
    )
    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                "component_a": {"component": "component_a", "total_regression_occurrences": 5, "unique_fingerprints": 1},
                "component_b": {"component": "component_b", "total_regression_occurrences": 4, "unique_fingerprints": 1},
                "component_c": {"component": "component_c", "total_regression_occurrences": 1, "unique_fingerprints": 1},
            }
        },
    )

    analyze_regression_intelligence(history_root=history_root, pf=pf)

    scenario_value = json.loads((pf / "intelligence" / "112_scenario_detection_value.json").read_text(encoding="utf-8"))
    rows = scenario_value.get("rows", []) if isinstance(scenario_value.get("rows", []), list) else []
    assert rows
    assert str((rows[0] if isinstance(rows[0], dict) else {}).get("scenario_id", "")) == "fault_missing_dependency_decl"


def test_remediation_effectiveness_fixture(tmp_path: Path) -> None:
    history_root, pf = _seed_common_layout(tmp_path)

    _write_json(
        history_root / "regressions" / "regression_fingerprints.json",
        {
            "rows": [
                {
                    "fingerprint": "fp_remediation",
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "component": "dependency_graph_resolver",
                    "severity_bucket": "MEDIUM",
                    "occurrences": 3,
                }
            ]
        },
    )
    _write_json(
        history_root / "components" / "component_regression_stats.json",
        {
            "components": {
                "dependency_graph_resolver": {
                    "component": "dependency_graph_resolver",
                    "total_regression_occurrences": 3,
                    "unique_fingerprints": 1,
                }
            }
        },
    )
    _write_json(
        pf / "resolution" / "71_component_resolution_metrics.json",
        {
            "rows": [
                {
                    "component": "dependency_graph_resolver",
                    "resolution_rate": 0.90,
                    "mean_time_to_resolution": 1.2,
                    "recurrence_rate": 0.20,
                    "resolved_regressions": 9,
                    "unresolved_regressions": 1,
                }
            ]
        },
    )
    _write_json(
        pf / "hotspots" / "13_remediation_guidance.json",
        {
            "entries": [
                {
                    "scenario_id": "fault_missing_dependency_decl",
                    "metric": "diagnostic_score",
                    "likely_component": "dependency_graph_resolver",
                    "suggested_investigation": "inspect dependency contract resolution logic",
                }
            ]
        },
    )

    analyze_regression_intelligence(history_root=history_root, pf=pf)

    remediation = json.loads((pf / "intelligence" / "113_remediation_effectiveness.json").read_text(encoding="utf-8"))
    rows = remediation.get("rows", []) if isinstance(remediation.get("rows", []), list) else []
    assert rows
    top = rows[0] if isinstance(rows[0], dict) else {}
    assert str(top.get("component", "")) == "dependency_graph_resolver"
    assert str(top.get("effectiveness_class", "")) == "STRONG"
