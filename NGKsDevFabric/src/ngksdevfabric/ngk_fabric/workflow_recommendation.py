from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .operations_control_plane_adapter import emit_operational_control_plane_summary

_PRIMARY_ACTIONS = {
    "NO_ACTION",
    "ASSIGN_IMMEDIATELY",
    "REOPEN_EXTERNAL_ISSUE",
    "CREATE_NEW_EXTERNAL_ISSUE",
    "ESCALATE_COMPONENT_WATCH",
    "RECOMMEND_STRICTER_VALIDATION_PLAN",
    "MANUAL_TRIAGE_REQUIRED",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _watch_rank(name: str) -> int:
    return {"CRITICAL": 4, "HOT": 3, "WATCH": 2, "NORMAL": 1}.get(name.upper(), 0)


def recommend_post_rerun_workflow(*, project_root: Path, pf: Path) -> dict[str, Any]:
    workflow_dir = pf / "workflow"

    pipeline_decision = _read_json(pf / "pipeline" / "143_pipeline_chain_decision.json")
    pipeline_rerun = _read_json(pf / "pipeline" / "142_certification_rerun_summary.json")
    execution_stage = _read_json(pf / "pipeline" / "141_execution_stage_summary.json")

    assignment_payload = _read_json(pf / "hotspots" / "19_assignment_policy.json")
    ownership_payload = _read_json(pf / "hotspots" / "16_ownership_confidence.json")
    closure_payload = _read_json(pf / "transport" / "100_closure_reconciliation.json")
    intelligence_payload = _read_json(pf / "intelligence" / "110_component_watchlist.json")
    planning_payload = _read_json(pf / "planning" / "124_plan_classification.json")
    resolution_payload = _read_json(pf / "resolution" / "70_regression_lifecycle_states.json")
    trend_payload = _read_json(pf / "history" / "52_regression_trend_analysis.json")

    assignment_rows = [row for row in assignment_payload.get("entries", []) if isinstance(row, dict)]
    ownership_rows = [row for row in ownership_payload.get("entries", []) if isinstance(row, dict)]
    closure_rows = [row for row in closure_payload.get("rows", []) if isinstance(row, dict)]
    watch_rows = [row for row in intelligence_payload.get("rows", []) if isinstance(row, dict)]
    resolution_rows = [row for row in resolution_payload.get("rows", []) if isinstance(row, dict)]

    top_assignment = assignment_rows[0] if assignment_rows else {}
    top_ownership = ownership_rows[0] if ownership_rows else {}

    combined_state = str(pipeline_decision.get("final_combined_state", "EXECUTION_CHAIN_INCONCLUSIVE"))
    rerun_decision = str(pipeline_rerun.get("certification_decision", ""))
    plan_class = str(planning_payload.get("plan_class", "STANDARD")).upper()
    trend_class = str(trend_payload.get("trend_classification", "INSUFFICIENT_HISTORY")).upper()
    skipped_count = _safe_int((execution_stage.get("execution_summary", {}) if isinstance(execution_stage.get("execution_summary", {}), dict) else {}).get("skipped_scenario_count", 0))

    assignment_policy = str(top_assignment.get("action_policy", "HUMAN_REVIEW_REQUIRED"))
    ownership_level = str(top_ownership.get("confidence_level", "LOW_CONFIDENCE"))

    closure_states = {str(row.get("closure_reconciliation_state", "")) for row in closure_rows}
    unresolved_mismatch = any(
        state in {
            "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH",
            "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH",
            "UNKNOWN_EXTERNAL_STATUS",
        }
        for state in closure_states
    )
    conflicting_mismatch = any(state in {"EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH", "UNKNOWN_EXTERNAL_STATUS"} for state in closure_states)

    has_closed_external_with_active = "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH" in closure_states
    has_no_viable_prior_issue = "NO_EXTERNAL_MATCH" in closure_states or not closure_rows

    recurrence_or_persistence = any(str(row.get("state", "")).upper() in {"RECURRING", "PERSISTING"} for row in resolution_rows)

    highest_watch = "NORMAL"
    for row in watch_rows:
        candidate = str(row.get("watch_class", "NORMAL")).upper()
        if _watch_rank(candidate) > _watch_rank(highest_watch):
            highest_watch = candidate

    regression_confirmed = combined_state == "EXECUTION_AND_CERTIFIED_REGRESSION"
    stable_or_improvement = combined_state in {
        "EXECUTION_AND_CERTIFIED_STABLE",
        "EXECUTION_AND_CERTIFIED_IMPROVEMENT",
    }

    high_confidence_assign = assignment_policy == "AUTO_ASSIGN_SAFE" and ownership_level == "HIGH_CONFIDENCE"
    manual_required = (
        assignment_policy == "HUMAN_REVIEW_REQUIRED"
        or ownership_level in {"LOW_CONFIDENCE", "MEDIUM_CONFIDENCE"}
        or conflicting_mismatch
        or combined_state == "EXECUTION_CHAIN_INCONCLUSIVE"
    )

    decision_matrix = {
        "NO_ACTION": {
            "eligible": stable_or_improvement and not unresolved_mismatch,
            "reason": "stable_or_improvement_with_no_unresolved_mismatch",
        },
        "MANUAL_TRIAGE_REQUIRED": {
            "eligible": regression_confirmed and manual_required,
            "reason": "human_review_or_low_confidence_or_conflicting_signals",
        },
        "REOPEN_EXTERNAL_ISSUE": {
            "eligible": regression_confirmed and has_closed_external_with_active and recurrence_or_persistence,
            "reason": "closed_external_issue_with_active_recurrence",
        },
        "CREATE_NEW_EXTERNAL_ISSUE": {
            "eligible": regression_confirmed and has_no_viable_prior_issue,
            "reason": "no_viable_prior_external_issue",
        },
        "ASSIGN_IMMEDIATELY": {
            "eligible": regression_confirmed and high_confidence_assign and not has_closed_external_with_active,
            "reason": "regression_with_high_confidence_auto_assign",
        },
        "ESCALATE_COMPONENT_WATCH": {
            "eligible": regression_confirmed and (highest_watch in {"HOT", "CRITICAL"} or trend_class == "RISING"),
            "reason": "hot_or_critical_watch_or_rising_trend",
        },
        "RECOMMEND_STRICTER_VALIDATION_PLAN": {
            "eligible": regression_confirmed and (plan_class in {"MINIMAL", "STANDARD", "HEIGHTENED"} or skipped_count > 0),
            "reason": "regression_after_non_strict_or_narrow_plan",
        },
    }

    primary_action = "MANUAL_TRIAGE_REQUIRED"
    primary_reason = "fallback_manual_triage"
    ordered_primary = [
        "NO_ACTION",
        "MANUAL_TRIAGE_REQUIRED",
        "REOPEN_EXTERNAL_ISSUE",
        "CREATE_NEW_EXTERNAL_ISSUE",
        "ASSIGN_IMMEDIATELY",
    ]
    for action in ordered_primary:
        entry = decision_matrix.get(action, {}) if isinstance(decision_matrix.get(action, {}), dict) else {}
        if bool(entry.get("eligible", False)):
            primary_action = action
            primary_reason = str(entry.get("reason", ""))
            break

    secondary_actions: list[str] = []
    for action in ["ESCALATE_COMPONENT_WATCH", "RECOMMEND_STRICTER_VALIDATION_PLAN"]:
        entry = decision_matrix.get(action, {}) if isinstance(decision_matrix.get(action, {}), dict) else {}
        if bool(entry.get("eligible", False)):
            secondary_actions.append(action)

    # Ensure deterministic order and uniqueness for secondaries.
    secondary_actions = [action for action in ["ESCALATE_COMPONENT_WATCH", "RECOMMEND_STRICTER_VALIDATION_PLAN"] if action in secondary_actions]

    if primary_action not in _PRIMARY_ACTIONS:
        primary_action = "MANUAL_TRIAGE_REQUIRED"
        primary_reason = "invalid_primary_action_fallback"

    evidence = {
        "combined_state": combined_state,
        "certification_decision": rerun_decision,
        "assignment_policy": assignment_policy,
        "ownership_confidence_level": ownership_level,
        "closure_reconciliation_states": sorted(closure_states),
        "recurrence_or_persistence_detected": recurrence_or_persistence,
        "highest_watch_class": highest_watch,
        "trend_classification": trend_class,
        "plan_class": plan_class,
        "skipped_scenario_count": skipped_count,
    }

    artifact_links = [
        "pipeline/141_execution_stage_summary.json",
        "pipeline/142_certification_rerun_summary.json",
        "pipeline/143_pipeline_chain_decision.json",
        "resolution/70_regression_lifecycle_states.json",
        "transport/100_closure_reconciliation.json",
        "intelligence/110_component_watchlist.json",
        "planning/124_plan_classification.json",
        "history/52_regression_trend_analysis.json",
        "hotspots/16_ownership_confidence.json",
        "hotspots/19_assignment_policy.json",
    ]

    _write_json(
        workflow_dir / "150_primary_workflow_recommendation.json",
        {
            "primary_action": primary_action,
            "primary_reason": primary_reason,
            "operator_follow_up": (
                "no_action_required"
                if primary_action == "NO_ACTION"
                else "execute_recommended_workflow_action"
            ),
        },
    )
    _write_json(
        workflow_dir / "151_secondary_recommendations.json",
        {
            "secondary_actions": secondary_actions,
        },
    )
    _write_json(
        workflow_dir / "152_workflow_decision_evidence.json",
        {
            "evidence": evidence,
            "artifact_references": artifact_links,
        },
    )
    _write_json(
        workflow_dir / "153_workflow_action_matrix.json",
        {
            "decision_matrix": decision_matrix,
            "primary_action": primary_action,
            "secondary_actions": secondary_actions,
        },
    )

    lines = [
        "# Autonomous Workflow Recommendation Summary",
        "",
        f"- combined_state: {combined_state}",
        f"- certification_decision: {rerun_decision}",
        f"- primary_action: {primary_action}",
        f"- primary_reason: {primary_reason}",
        f"- secondary_actions: {', '.join(secondary_actions) if secondary_actions else 'none'}",
        f"- assignment_policy: {assignment_policy}",
        f"- ownership_confidence_level: {ownership_level}",
        f"- highest_watch_class: {highest_watch}",
        f"- trend_classification: {trend_class}",
        f"- plan_class: {plan_class}",
        "",
        "## Suggested Operator Follow-up",
        "- apply primary action first",
        "- apply secondary actions if listed",
        "- retain upstream certification/gate semantics unchanged",
    ]
    _write_text(workflow_dir / "154_workflow_summary.md", "\n".join(lines) + "\n")

    emit_operational_control_plane_summary(
        pf=pf,
        source="workflow_recommendation",
        source_summary={
            "primary_action": primary_action,
            "primary_reason": primary_reason,
            "secondary_actions": secondary_actions,
            "combined_state": combined_state,
            "certification_decision": rerun_decision,
        },
    )

    return {
        "summary": {
            "primary_action": primary_action,
            "primary_reason": primary_reason,
            "secondary_actions": secondary_actions,
        },
        "artifacts": [
            "workflow/150_primary_workflow_recommendation.json",
            "workflow/151_secondary_recommendations.json",
            "workflow/152_workflow_decision_evidence.json",
            "workflow/153_workflow_action_matrix.json",
            "workflow/154_workflow_summary.md",
        ],
    }
