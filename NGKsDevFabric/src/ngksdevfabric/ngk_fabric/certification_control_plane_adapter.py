from __future__ import annotations

from pathlib import Path
from typing import Any

from .control_plane_integration import (
    compute_operational_governance_state,
    gather_operational_surfaces,
    load_control_plane_context,
    write_control_plane_summary,
)


def emit_certification_control_plane_summary(
    *,
    pf: Path,
    execution_summary: dict[str, Any],
    rerun_summary: dict[str, Any],
    chain_summary: dict[str, Any],
) -> dict[str, Any]:
    control_plane_context = load_control_plane_context(pf=pf)
    surfaces = gather_operational_surfaces(pf=pf)
    governance_state = compute_operational_governance_state(
        control_plane_context=control_plane_context,
        surfaces=surfaces,
    )

    payload = {
        "schema": "ngks.control_plane.certification.summary.v1",
        "summary_type": "certification_control_plane_alignment",
        "execution_policy": str(execution_summary.get("execution_policy", "")),
        "executed_scenario_count": int(execution_summary.get("completed_scenario_count", 0) or 0),
        "rerun_decision": str(rerun_summary.get("rerun_decision", "")),
        "rerun_reason": str(rerun_summary.get("rerun_reason", "")),
        "certification_decision": str(rerun_summary.get("certification_decision", "")),
        "compatibility_state": str(rerun_summary.get("compatibility_state", "")),
        "enforced_gate": str(rerun_summary.get("enforced_gate", "")),
        "pipeline_chain_gate": str(chain_summary.get("chain_gate", "")),
        "pipeline_final_state": str(chain_summary.get("final_combined_state", "")),
        "governance_state": governance_state,
        "control_plane_context": control_plane_context,
        "operational_surfaces": {
            "pipeline": surfaces.get("pipeline", {}),
            "workflow": surfaces.get("workflow", {}),
        },
        "evidence_refs": [
            "control_plane/58_decision_envelope_chain.json",
            "control_plane/65_outcome_feedback_chain.json",
            "control_plane/67_confidence_propagation.json",
            "control_plane/68_recurrence_propagation.json",
            "control_plane/69_predictive_calibration_propagation.json",
            "control_plane/70_certification_impact_propagation.json",
            "pipeline/142_certification_rerun_summary.json",
            "pipeline/143_pipeline_chain_decision.json",
        ],
    }

    output_path = write_control_plane_summary(
        pf=pf,
        file_name="72_certification_control_plane_summary.json",
        payload=payload,
    )
    return {
        "summary_path": output_path,
        "governance_state": governance_state,
        "chain_gate": str(chain_summary.get("chain_gate", "")),
        "certification_decision": str(rerun_summary.get("certification_decision", "")),
    }
