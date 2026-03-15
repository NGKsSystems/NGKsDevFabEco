from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.validation_rerun_pipeline import run_validation_and_certify_pipeline


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _scenario_row(scenario_id: str, rank: int, score: float, required: bool) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "priority_rank": rank,
        "priority_score": score,
        "required": required,
        "selection_reason": "fixture",
        "signals": {
            "historical_detection_value": score,
            "watch_pressure": score,
            "predictive_pressure": score,
            "recurrence_pressure": score,
            "unresolved_pressure": score,
            "relevance": 1.0,
        },
    }


def _seed_plan(
    *,
    project_root: Path,
    run_name: str,
    plan_class: str,
    rows: list[dict[str, object]],
    required_ids: list[str],
    optional_ids: list[str],
) -> Path:
    plan_root = project_root / "_proof" / "runs" / run_name
    planning = plan_root / "planning"

    required_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(required_ids)]
    optional_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(optional_ids)]

    _write_json(
        planning / "120_validation_plan_inputs.json",
        {
            "project_root": str(project_root.resolve()),
            "change_manifest": {"change_id": "chg_chain", "touched_components": ["component_a"]},
            "touched_components": ["component_a"],
        },
    )
    _write_json(planning / "121_scenario_plan_ranking.json", {"rows": rows})
    _write_json(planning / "122_required_vs_optional_plan.json", {"required": required_rows, "optional": optional_rows})
    _write_json(
        planning / "123_component_focus_plan.json",
        {
            "rows": [
                {
                    "component": "component_a",
                    "watch_class": "NORMAL",
                    "predictive_risk_score": 0.10,
                    "unresolved_ratio": 0.10,
                    "focus_score": 0.10,
                    "priority_rank": 1,
                }
            ]
        },
    )
    _write_json(
        planning / "124_plan_classification.json",
        {
            "plan_class": plan_class,
            "aggregate_plan_score": 0.20,
            "required_scenario_count": len(required_rows),
            "optional_scenario_count": len(optional_rows),
        },
    )
    return plan_root


def _seed_certification_target(project_root: Path, *, baseline_score: float, current_score: float) -> None:
    cert_root = project_root / "certification" / "baseline_v1"
    _write_json(cert_root / "baseline_manifest.json", {"baseline_version": "v1", "scenario_count": 1})
    _write_json(
        cert_root / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": baseline_score,
            "average_component_ownership_accuracy": baseline_score,
            "average_root_cause_accuracy": baseline_score,
            "average_remediation_quality": baseline_score,
            "average_proof_quality": baseline_score,
            "average_diagnostic_score": baseline_score,
        },
    )
    _write_json(
        cert_root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": baseline_score,
                    "scores": {
                        "detection_accuracy": baseline_score,
                        "component_ownership_accuracy": baseline_score,
                        "root_cause_accuracy": baseline_score,
                        "remediation_quality": baseline_score,
                        "proof_quality": baseline_score,
                    },
                }
            ]
        },
    )

    _write_json(project_root / "certification" / "scenario_index.json", {"scenario_ids": ["baseline_pass"]})

    _write_json(project_root / "baseline_manifest.json", {"baseline_version": "current_run", "scenario_count": 1})
    _write_json(
        project_root / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": current_score,
            "average_component_ownership_accuracy": current_score,
            "average_root_cause_accuracy": current_score,
            "average_remediation_quality": current_score,
            "average_proof_quality": current_score,
            "average_diagnostic_score": current_score,
        },
    )
    _write_json(
        project_root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": current_score,
                    "scores": {
                        "detection_accuracy": current_score,
                        "component_ownership_accuracy": current_score,
                        "root_cause_accuracy": current_score,
                        "remediation_quality": current_score,
                        "proof_quality": current_score,
                    },
                }
            ]
        },
    )

    _write_json(
        project_root / "certification_target.json",
        {
            "project_name": "ChainFixture",
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
        },
    )


def _decision(path: Path) -> dict[str, object]:
    payload = json.loads((path / "pipeline" / "143_pipeline_chain_decision.json").read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _execution_summary(path: Path) -> dict[str, object]:
    payload = json.loads((path / "pipeline" / "141_execution_stage_summary.json").read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rerun_summary(path: Path) -> dict[str, object]:
    payload = json.loads((path / "pipeline" / "142_certification_rerun_summary.json").read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def test_balanced_chain_success(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.90, current_score=0.90)
    _seed_plan(
        project_root=project_root,
        run_name="plan_balanced_success",
        plan_class="STANDARD",
        rows=[
            _scenario_row("required_a", 1, 0.20, True),
            _scenario_row("optional_a", 2, 0.10, False),
        ],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "chain_balanced"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    state = str(result.get("summary", {}).get("final_combined_state", ""))
    assert state in {"EXECUTION_AND_CERTIFIED_STABLE", "EXECUTION_AND_CERTIFIED_IMPROVEMENT"}


def test_fast_policy_early_stop_chain(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.90, current_score=0.60)
    _seed_plan(
        project_root=project_root,
        run_name="plan_fast_early",
        plan_class="CRITICAL",
        rows=[
            _scenario_row("critical_case", 1, 0.95, True),
            _scenario_row("required_b", 2, 0.70, True),
            _scenario_row("optional_b", 3, 0.20, False),
        ],
        required_ids=["critical_case", "required_b"],
        optional_ids=["optional_b"],
    )

    pf = tmp_path / "proof" / "chain_fast"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="FAST",
    )

    exec_summary = _execution_summary(pf)
    rerun = _rerun_summary(pf)
    state = str(result.get("summary", {}).get("final_combined_state", ""))

    assert str(exec_summary.get("early_stop_reason", "")) == "critical_regression_detected"
    assert rerun
    assert state in {"EXECUTION_AND_CERTIFIED_REGRESSION", "EXECUTION_CHAIN_INCONCLUSIVE"}


def test_strict_chain_no_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.90, current_score=0.90)
    _seed_plan(
        project_root=project_root,
        run_name="plan_no_execution",
        plan_class="MINIMAL",
        rows=[],
        required_ids=[],
        optional_ids=[],
    )

    pf = tmp_path / "proof" / "chain_strict_no_exec"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
        strict_chain=True,
        skip_rerun_if_no_execution=True,
    )

    decision = _decision(pf)
    state = str(result.get("summary", {}).get("final_combined_state", ""))
    assert state == "EXECUTION_CHAIN_INCONCLUSIVE"
    assert str(decision.get("rerun_decision", "")).startswith("BLOCKED_STRICT")


def test_execution_then_regression_rerun(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.90, current_score=0.62)
    _seed_plan(
        project_root=project_root,
        run_name="plan_then_regression",
        plan_class="STANDARD",
        rows=[
            _scenario_row("required_c", 1, 0.25, True),
            _scenario_row("optional_c", 2, 0.18, False),
        ],
        required_ids=["required_c"],
        optional_ids=["optional_c"],
    )

    pf = tmp_path / "proof" / "chain_regression"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    state = str(result.get("summary", {}).get("final_combined_state", ""))
    assert state == "EXECUTION_AND_CERTIFIED_REGRESSION"
    assert (pf / "pipeline" / "144_pipeline_chain_summary.md").is_file()
    assert (pf / "workflow" / "150_primary_workflow_recommendation.json").is_file()
