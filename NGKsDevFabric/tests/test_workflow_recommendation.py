from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.workflow_recommendation import recommend_post_rerun_workflow


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_workflow_inputs(
    *,
    pf: Path,
    final_state: str,
    cert_decision: str,
    assignment_policy: str,
    ownership_level: str,
    closure_state: str,
    plan_class: str,
    resolution_states: list[str] | None = None,
    watch_class: str = "NORMAL",
    trend_classification: str = "STABLE",
    skipped_count: int = 0,
) -> None:
    _write_json(
        pf / "pipeline" / "141_execution_stage_summary.json",
        {
            "execution_summary": {"skipped_scenario_count": skipped_count},
            "executed_scenario_count": 2,
            "execution_failure_count": 0,
            "early_stop_reason": "",
        },
    )
    _write_json(
        pf / "pipeline" / "142_certification_rerun_summary.json",
        {
            "certification_decision": cert_decision,
            "enforced_gate": "PASS" if cert_decision != "CERTIFIED_REGRESSION" else "FAIL",
        },
    )
    _write_json(
        pf / "pipeline" / "143_pipeline_chain_decision.json",
        {
            "final_combined_state": final_state,
            "chain_gate": "PASS" if final_state != "EXECUTION_CHAIN_INCONCLUSIVE" else "FAIL",
            "rerun_allowed": True,
            "rerun_decision": "RERUN_COMPLETED",
        },
    )

    _write_json(
        pf / "hotspots" / "19_assignment_policy.json",
        {
            "entries": [
                {
                    "component": "component_a",
                    "action_policy": assignment_policy,
                    "assignee": "owner_a",
                }
            ]
        },
    )
    _write_json(
        pf / "hotspots" / "16_ownership_confidence.json",
        {
            "entries": [
                {
                    "component": "component_a",
                    "confidence_level": ownership_level,
                    "confidence_score": 0.90,
                }
            ]
        },
    )
    _write_json(
        pf / "transport" / "100_closure_reconciliation.json",
        {
            "rows": [
                {
                    "component": "component_a",
                    "closure_reconciliation_state": closure_state,
                }
            ]
        },
    )
    _write_json(
        pf / "planning" / "124_plan_classification.json",
        {
            "plan_class": plan_class,
            "aggregate_plan_score": 0.40,
            "required_scenario_count": 1,
            "optional_scenario_count": 1,
        },
    )
    _write_json(
        pf / "resolution" / "70_regression_lifecycle_states.json",
        {
            "rows": [
                {"component": "component_a", "state": state}
                for state in (resolution_states or ["NEW"])
            ]
        },
    )
    _write_json(
        pf / "intelligence" / "110_component_watchlist.json",
        {
            "rows": [
                {
                    "component": "component_a",
                    "watch_class": watch_class,
                }
            ]
        },
    )
    _write_json(
        pf / "history" / "52_regression_trend_analysis.json",
        {
            "trend_classification": trend_classification,
        },
    )


def _workflow_primary(pf: Path) -> str:
    payload = json.loads((pf / "workflow" / "150_primary_workflow_recommendation.json").read_text(encoding="utf-8"))
    return str(payload.get("primary_action", ""))


def _workflow_secondary(pf: Path) -> list[str]:
    payload = json.loads((pf / "workflow" / "151_secondary_recommendations.json").read_text(encoding="utf-8"))
    rows = payload.get("secondary_actions", [])
    return [str(row) for row in rows] if isinstance(rows, list) else []


def test_recommend_no_action_when_stable_and_clean(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_stable"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_STABLE",
        cert_decision="CERTIFIED_STABLE",
        assignment_policy="AUTO_ASSIGN_SAFE",
        ownership_level="HIGH_CONFIDENCE",
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        plan_class="STANDARD",
    )

    result = recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert _workflow_primary(pf) == "NO_ACTION"
    assert result.get("summary", {}).get("primary_action", "") == "NO_ACTION"


def test_recommend_assign_immediately_for_confident_regression(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_assign"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_REGRESSION",
        cert_decision="CERTIFIED_REGRESSION",
        assignment_policy="AUTO_ASSIGN_SAFE",
        ownership_level="HIGH_CONFIDENCE",
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        plan_class="CRITICAL",
    )

    recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert _workflow_primary(pf) == "ASSIGN_IMMEDIATELY"


def test_recommend_reopen_external_issue_for_recurring_closed_mismatch(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_reopen"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_REGRESSION",
        cert_decision="CERTIFIED_REGRESSION",
        assignment_policy="AUTO_ASSIGN_SAFE",
        ownership_level="HIGH_CONFIDENCE",
        closure_state="EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH",
        plan_class="CRITICAL",
        resolution_states=["RECURRING"],
    )

    recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert _workflow_primary(pf) == "REOPEN_EXTERNAL_ISSUE"


def test_recommend_create_new_external_issue_when_no_match_exists(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_create"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_REGRESSION",
        cert_decision="CERTIFIED_REGRESSION",
        assignment_policy="AUTO_ASSIGN_SAFE",
        ownership_level="HIGH_CONFIDENCE",
        closure_state="NO_EXTERNAL_MATCH",
        plan_class="CRITICAL",
    )

    recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert _workflow_primary(pf) == "CREATE_NEW_EXTERNAL_ISSUE"


def test_recommend_stricter_plan_as_secondary_after_regression(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_stricter_plan"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_REGRESSION",
        cert_decision="CERTIFIED_REGRESSION",
        assignment_policy="AUTO_ASSIGN_SAFE",
        ownership_level="HIGH_CONFIDENCE",
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        plan_class="STANDARD",
        skipped_count=1,
    )

    recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert "RECOMMEND_STRICTER_VALIDATION_PLAN" in _workflow_secondary(pf)


def test_recommend_manual_triage_when_human_review_required(tmp_path: Path) -> None:
    pf = tmp_path / "proof" / "workflow_manual"
    _seed_workflow_inputs(
        pf=pf,
        final_state="EXECUTION_AND_CERTIFIED_REGRESSION",
        cert_decision="CERTIFIED_REGRESSION",
        assignment_policy="HUMAN_REVIEW_REQUIRED",
        ownership_level="MEDIUM_CONFIDENCE",
        closure_state="EXTERNAL_OPEN_INTERNAL_ACTIVE",
        plan_class="CRITICAL",
    )

    recommend_post_rerun_workflow(project_root=tmp_path, pf=pf)
    assert _workflow_primary(pf) == "MANUAL_TRIAGE_REQUIRED"
    assert (pf / "workflow" / "154_workflow_summary.md").is_file()
