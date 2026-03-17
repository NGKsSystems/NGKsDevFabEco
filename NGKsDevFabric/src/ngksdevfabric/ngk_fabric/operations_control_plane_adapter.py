from __future__ import annotations

from pathlib import Path
from typing import Any

from .control_plane_integration import (
    compute_operational_governance_state,
    gather_operational_surfaces,
    load_control_plane_context,
    write_control_plane_summary,
)


def emit_operational_control_plane_summary(
    *,
    pf: Path,
    source: str,
    source_summary: dict[str, Any],
) -> dict[str, Any]:
    control_plane_context = load_control_plane_context(pf=pf)
    surfaces = gather_operational_surfaces(pf=pf)
    governance_state = compute_operational_governance_state(
        control_plane_context=control_plane_context,
        surfaces=surfaces,
    )

    payload = {
        "schema": "ngks.control_plane.operational.summary.v1",
        "summary_type": "operational_control_plane_alignment",
        "integration_source": str(source),
        "integration_source_summary": source_summary,
        "governance_state": governance_state,
        "control_plane_context": control_plane_context,
        "operational_surfaces": surfaces,
        "evidence_refs": [
            "control_plane/58_decision_envelope_chain.json",
            "control_plane/65_outcome_feedback_chain.json",
            "control_plane/67_confidence_propagation.json",
            "control_plane/68_recurrence_propagation.json",
            "control_plane/69_predictive_calibration_propagation.json",
            "control_plane/70_certification_impact_propagation.json",
            "pipeline/143_pipeline_chain_decision.json",
            "workflow/150_primary_workflow_recommendation.json",
            "history/52_regression_trend_analysis.json",
            "predictive/64_prediction_classification.json",
            "intelligence/110_component_watchlist.json",
            "hotspots/09_regression_hotspots.json",
        ],
    }

    output_path = write_control_plane_summary(
        pf=pf,
        file_name="73_operational_control_plane_summary.json",
        payload=payload,
    )

    return {
        "summary_path": output_path,
        "governance_state": governance_state,
        "integration_source": str(source),
    }


def emit_explain_control_plane_summary(
    *,
    pf: Path,
    explain_result: dict[str, Any],
    explain_context: dict[str, Any],
) -> dict[str, Any]:
    control_plane_context = load_control_plane_context(pf=pf)
    surfaces = gather_operational_surfaces(pf=pf)
    governance_state = compute_operational_governance_state(
        control_plane_context=control_plane_context,
        surfaces=surfaces,
    )

    graph_edges_used = explain_result.get("graph_edges_used", []) if isinstance(explain_result.get("graph_edges_used", []), list) else []
    explain_gate = "PASS" if graph_edges_used else "PARTIAL"

    payload = {
        "schema": "ngks.control_plane.explain.summary.v1",
        "summary_type": "explain_control_plane_alignment",
        "latest_entity": str(explain_result.get("entity", "")),
        "latest_entity_type": str(explain_result.get("entity_type", "")),
        "latest_confidence": str(explain_result.get("confidence", "")),
        "latest_confidence_reason": str(explain_result.get("confidence_reason", "")),
        "reason_chain": explain_result.get("reason_chain", []) if isinstance(explain_result.get("reason_chain", []), list) else [],
        "graph_edges_used": graph_edges_used,
        "evidence_file_count": len(explain_result.get("evidence_files", []) if isinstance(explain_result.get("evidence_files", []), list) else []),
        "explain_gate": explain_gate,
        "governance_state": governance_state,
        "control_plane_context": control_plane_context,
        "operational_surfaces": {
            "pipeline": surfaces.get("pipeline", {}),
            "workflow": surfaces.get("workflow", {}),
            "explain_context_paths": {
                "component_graph_path": str(explain_context.get("component_graph_path", "")),
                "impact_run": str(explain_context.get("impact_run", "")),
                "rebuild_run": str(explain_context.get("rebuild_run", "")),
            },
        },
        "evidence_refs": [
            "control_plane/58_decision_envelope_chain.json",
            "control_plane/65_outcome_feedback_chain.json",
            "control_plane/67_confidence_propagation.json",
            "control_plane/68_recurrence_propagation.json",
            "control_plane/69_predictive_calibration_propagation.json",
            "control_plane/70_certification_impact_propagation.json",
            "pipeline/143_pipeline_chain_decision.json",
            "workflow/150_primary_workflow_recommendation.json",
        ],
    }

    output_path = write_control_plane_summary(
        pf=pf,
        file_name="74_explain_control_plane_summary.json",
        payload=payload,
    )
    return {
        "summary_path": output_path,
        "governance_state": governance_state,
        "explain_gate": explain_gate,
    }
