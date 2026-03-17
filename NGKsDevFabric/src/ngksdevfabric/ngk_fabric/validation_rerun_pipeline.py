from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .certification_policy_surface import evaluate_structural_certification_state, evaluate_target_capability_state
from .certification_status import inspect_certification_status
from .certification_target import run_target_validation_precheck
from .certification_control_plane_adapter import emit_certification_control_plane_summary
from .certify_compare import ComparisonPolicy
from .certify_gate import GateEnforcementPolicy, run_certification_gate
from .operations_control_plane_adapter import emit_operational_control_plane_summary
from .validation_plugin_registry import execute_validation_plugins
from .validation_orchestrator import run_validation_orchestrator
from .workflow_recommendation import recommend_post_rerun_workflow

_COMBINED_STATE_MAP = {
    "CERTIFIED_STABLE": "EXECUTION_AND_CERTIFIED_STABLE",
    "CERTIFIED_IMPROVEMENT": "EXECUTION_AND_CERTIFIED_IMPROVEMENT",
    "CERTIFIED_REGRESSION": "EXECUTION_AND_CERTIFIED_REGRESSION",
    "CERTIFICATION_INCONCLUSIVE": "EXECUTION_CHAIN_INCONCLUSIVE",
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


def _is_execution_failure(reason: str) -> bool:
    lowered = reason.strip().lower()
    if not lowered:
        return False
    if lowered in {"confidence_threshold_satisfied"}:
        return False
    return True


def _combined_state_from_rerun(decision: str) -> str:
    return _COMBINED_STATE_MAP.get(decision, "EXECUTION_CHAIN_INCONCLUSIVE")


def _chain_gate(final_state: str) -> str:
    if final_state in {
        "EXECUTION_ONLY",
        "EXECUTION_AND_CERTIFIED_STABLE",
        "EXECUTION_AND_CERTIFIED_IMPROVEMENT",
    }:
        return "PASS"
    return "FAIL"


def run_validation_and_certify_pipeline(
    *,
    project_root: Path,
    repo_root: Path,
    pf: Path,
    execution_policy: str = "BALANCED",
    change_manifest_path: Path | None = None,
    touched_components: list[str] | None = None,
    skip_rerun_if_no_execution: bool = False,
    strict_chain: bool = False,
) -> dict[str, Any]:
    pipeline_dir = pf / "pipeline"

    orchestrator_result = run_validation_orchestrator(
        project_root=project_root,
        pf=pf,
        execution_policy=execution_policy,
        change_manifest_path=change_manifest_path,
        touched_components=touched_components,
    )
    execution_summary = orchestrator_result.get("summary", {}) if isinstance(orchestrator_result.get("summary", {}), dict) else {}

    execution_failures_payload = _read_json(pf / "execution" / "133_execution_failures.json")
    execution_failure_rows = [row for row in execution_failures_payload.get("rows", []) if isinstance(row, dict)]
    execution_failure_count = sum(1 for row in execution_failure_rows if _is_execution_failure(str(row.get("failure_reason", ""))))

    executed_count = _safe_int(execution_summary.get("completed_scenario_count", 0))
    early_stop_reason = str(execution_summary.get("early_stop_reason", "")).strip()

    rerun_allowed = True
    rerun_decision = "RUN_CERTIFICATION_RERUN"
    rerun_reason = "default_chain"

    if executed_count == 0:
        if strict_chain:
            rerun_allowed = False
            rerun_decision = "BLOCKED_STRICT_NO_EXECUTION"
            rerun_reason = "strict_chain_requires_executed_scenarios"
        elif skip_rerun_if_no_execution:
            rerun_allowed = False
            rerun_decision = "SKIPPED_NO_EXECUTION"
            rerun_reason = "skip_rerun_if_no_execution_enabled"
        else:
            rerun_allowed = False
            rerun_decision = "SKIPPED_NO_EXECUTION"
            rerun_reason = "no_executed_scenarios"

    if execution_failure_count > 0 and strict_chain:
        rerun_allowed = False
        rerun_decision = "BLOCKED_STRICT_EXECUTION_FAILURES"
        rerun_reason = "strict_chain_blocks_rerun_on_execution_failures"

    rerun_pf = (pf / "rerun_certification").resolve()
    rerun_summary: dict[str, Any] = {
        "rerun_allowed": rerun_allowed,
        "rerun_decision": rerun_decision,
        "rerun_reason": rerun_reason,
        "target_capability_state": "",
        "certification_decision": "",
        "compatibility_state": "",
        "enforced_gate": "",
        "exit_code": 1,
    }

    final_state = "EXECUTION_ONLY"
    if rerun_allowed:
        target_result = run_target_validation_precheck(project_root=project_root, pf=pf)
        rerun_summary["target_capability_state"] = target_result.state

        target_policy = evaluate_target_capability_state(target_result.state)
        if not target_policy.allow:
            final_state = "EXECUTION_CHAIN_INCONCLUSIVE"
            rerun_summary.update(
                {
                    "rerun_decision": "BLOCKED_POLICY",
                    "rerun_reason": target_policy.reason_code,
                    "target_policy_rule_id": target_policy.rule_id,
                    "certification_decision": "CERTIFICATION_INCONCLUSIVE",
                    "compatibility_state": "INCOMPATIBLE",
                    "enforced_gate": "FAIL",
                    "exit_code": 1,
                }
            )
        else:
            structural_status = inspect_certification_status(project_root)
            structural_policy = evaluate_structural_certification_state(structural_status.state)
            if not structural_policy.allow:
                final_state = "EXECUTION_CHAIN_INCONCLUSIVE"
                rerun_summary.update(
                    {
                        "rerun_decision": "BLOCKED_POLICY",
                        "rerun_reason": structural_policy.reason_code,
                        "structural_policy_rule_id": structural_policy.rule_id,
                        "certification_decision": "CERTIFICATION_INCONCLUSIVE",
                        "compatibility_state": "UNKNOWN",
                        "enforced_gate": "FAIL",
                        "exit_code": 1,
                    }
                )
            else:
                baseline_path = target_result.baseline_root.resolve()
                gate_result = run_certification_gate(
                    repo_root=repo_root,
                    baseline_path=baseline_path,
                    current_path=project_root.resolve(),
                    pf=rerun_pf,
                    comparison_policy=ComparisonPolicy(),
                    enforcement_policy=GateEnforcementPolicy(strict_mode=True),
                    supported_baseline_versions=target_result.supported_baseline_versions,
                    profile_project_root=project_root.resolve(),
                )

                decision = str(gate_result.get("decision", "CERTIFICATION_INCONCLUSIVE"))
                final_state = _combined_state_from_rerun(decision)
                rerun_summary.update(
                    {
                        "rerun_decision": "RERUN_COMPLETED",
                        "rerun_reason": "certification_gate_completed",
                        "certification_decision": decision,
                        "compatibility_state": str(gate_result.get("compatibility_state", "")),
                        "enforced_gate": str(gate_result.get("enforced_gate", "FAIL")),
                        "exit_code": _safe_int(gate_result.get("exit_code", 1)),
                        "rerun_pf": str(gate_result.get("pf", "")),
                        "rerun_zip": str(gate_result.get("zip", "")),
                    }
                )
    else:
        if rerun_decision.startswith("BLOCKED_STRICT"):
            final_state = "EXECUTION_CHAIN_INCONCLUSIVE"
            rerun_summary.update(
                {
                    "certification_decision": "CERTIFICATION_INCONCLUSIVE",
                    "compatibility_state": "UNKNOWN",
                    "enforced_gate": "FAIL",
                    "exit_code": 1,
                }
            )
        else:
            final_state = "EXECUTION_ONLY"
            rerun_summary.update(
                {
                    "certification_decision": "",
                    "compatibility_state": "",
                    "enforced_gate": "",
                    "exit_code": 0,
                }
            )

    chain_gate = _chain_gate(final_state)

    _write_json(
        pipeline_dir / "140_orchestrator_to_rerun_inputs.json",
        {
            "project_root": str(project_root.resolve()),
            "repo_root": str(repo_root.resolve()),
            "execution_policy": str(execution_summary.get("execution_policy", execution_policy)),
            "change_manifest": _read_json(change_manifest_path) if change_manifest_path is not None else {},
            "touched_components": [str(component).strip() for component in (touched_components or []) if str(component).strip()],
            "strict_chain": bool(strict_chain),
            "skip_rerun_if_no_execution": bool(skip_rerun_if_no_execution),
            "orchestrator_artifacts": orchestrator_result.get("artifacts", []),
        },
    )
    _write_json(
        pipeline_dir / "141_execution_stage_summary.json",
        {
            "execution_summary": execution_summary,
            "execution_failure_count": execution_failure_count,
            "execution_failures": execution_failure_rows,
            "early_stop_reason": early_stop_reason,
            "executed_scenario_count": executed_count,
        },
    )
    _write_json(pipeline_dir / "142_certification_rerun_summary.json", rerun_summary)
    _write_json(
        pipeline_dir / "143_pipeline_chain_decision.json",
        {
            "final_combined_state": final_state,
            "chain_gate": chain_gate,
            "rerun_allowed": rerun_allowed,
            "rerun_decision": rerun_decision,
            "strict_chain": bool(strict_chain),
            "skip_rerun_if_no_execution": bool(skip_rerun_if_no_execution),
        },
    )

    workflow_result = recommend_post_rerun_workflow(project_root=project_root, pf=pf)
    workflow_summary = workflow_result.get("summary", {}) if isinstance(workflow_result.get("summary", {}), dict) else {}
    workflow_artifacts = workflow_result.get("artifacts", []) if isinstance(workflow_result.get("artifacts", []), list) else []

    plugin_result = execute_validation_plugins(
        project_root=project_root,
        pf=pf,
        view_name="runtime_update_loop_scheduler",
    )
    plugin_summary = plugin_result.get("summary", {}) if isinstance(plugin_result.get("summary", {}), dict) else {}
    plugin_artifacts = plugin_result.get("artifacts", []) if isinstance(plugin_result.get("artifacts", []), list) else []

    lines = [
        "# Validation to Certification Chain Summary",
        "",
        f"- execution_policy: {execution_summary.get('execution_policy', execution_policy)}",
        f"- executed_scenario_count: {executed_count}",
        f"- early_stop_reason: {early_stop_reason or 'none'}",
        f"- execution_failure_count: {execution_failure_count}",
        f"- rerun_decision: {rerun_decision}",
        f"- rerun_reason: {rerun_reason}",
        f"- certification_decision: {rerun_summary.get('certification_decision', '')}",
        f"- enforced_gate: {rerun_summary.get('enforced_gate', '')}",
        f"- final_combined_state: {final_state}",
        f"- chain_gate: {chain_gate}",
        f"- primary_workflow_action: {workflow_summary.get('primary_action', '')}",
        f"- secondary_workflow_actions: {', '.join(workflow_summary.get('secondary_actions', [])) if workflow_summary.get('secondary_actions') else 'none'}",
        f"- validation_plugin_status: {plugin_summary.get('overall_status', 'PASS')}",
        f"- validation_plugin_fail_count: {plugin_summary.get('fail_count', 0)}",
        "",
        "## Stage Boundaries",
        "- stage_1: orchestrated_execution (execution/130..134)",
        "- stage_2: certification_rerun (rerun_certification/* when rerun is allowed)",
        "- stage_3: chain_decision (pipeline/140..144)",
        "- stage_4: workflow_recommendation (workflow/150..154)",
        "- stage_5: post_certification_validation_plugins (validation_plugins/220..222)",
    ]
    _write_text(pipeline_dir / "144_pipeline_chain_summary.md", "\n".join(lines) + "\n")

    certification_cp = emit_certification_control_plane_summary(
        pf=pf,
        execution_summary=execution_summary,
        rerun_summary=rerun_summary,
        chain_summary={
            "final_combined_state": final_state,
            "chain_gate": chain_gate,
        },
    )
    operational_cp = emit_operational_control_plane_summary(
        pf=pf,
        source="validation_and_certify_pipeline",
        source_summary={
            "execution_policy": str(execution_summary.get("execution_policy", execution_policy)),
            "executed_scenario_count": executed_count,
            "final_combined_state": final_state,
            "chain_gate": chain_gate,
            "primary_workflow_action": str(workflow_summary.get("primary_action", "")),
            "validation_plugin_status": str(plugin_summary.get("overall_status", "PASS")),
        },
    )

    return {
        "summary": {
            "final_combined_state": final_state,
            "chain_gate": chain_gate,
            "execution_policy": str(execution_summary.get("execution_policy", execution_policy)),
            "executed_scenario_count": executed_count,
            "early_stop_reason": early_stop_reason,
            "rerun_decision": rerun_decision,
            "certification_decision": str(rerun_summary.get("certification_decision", "")),
            "enforced_gate": str(rerun_summary.get("enforced_gate", "")),
            "primary_workflow_action": str(workflow_summary.get("primary_action", "")),
            "secondary_workflow_actions": [
                str(action) for action in workflow_summary.get("secondary_actions", []) if str(action)
            ],
            "validation_plugin_status": str(plugin_summary.get("overall_status", "PASS")),
            "validation_plugin_fail_count": _safe_int(plugin_summary.get("fail_count", 0)),
            "certification_control_plane_governance_state": str(certification_cp.get("governance_state", "")),
            "operational_control_plane_governance_state": str(operational_cp.get("governance_state", "")),
        },
        "artifacts": [
            "pipeline/140_orchestrator_to_rerun_inputs.json",
            "pipeline/141_execution_stage_summary.json",
            "pipeline/142_certification_rerun_summary.json",
            "pipeline/143_pipeline_chain_decision.json",
            "pipeline/144_pipeline_chain_summary.md",
            "control_plane/72_certification_control_plane_summary.json",
            "control_plane/73_operational_control_plane_summary.json",
            *[str(item) for item in workflow_artifacts if str(item)],
            *[str(item) for item in plugin_artifacts if str(item)],
        ],
    }
