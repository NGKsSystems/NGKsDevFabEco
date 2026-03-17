from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _latest_entry(chain_payload: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in chain_payload.get("entries", []) if isinstance(row, dict)]
    if not rows:
        return {}
    rows = sorted(rows, key=lambda row: _safe_int(row.get("chain_index", 0)))
    return rows[-1]


def load_control_plane_context(*, pf: Path) -> dict[str, Any]:
    cp = (pf / "control_plane").resolve()
    decision_chain = _read_json(cp / "58_decision_envelope_chain.json")
    feedback_chain = _read_json(cp / "65_outcome_feedback_chain.json")
    confidence_payload = _read_json(cp / "67_confidence_propagation.json")
    recurrence_payload = _read_json(cp / "68_recurrence_propagation.json")
    calibration_payload = _read_json(cp / "69_predictive_calibration_propagation.json")
    cert_impact_payload = _read_json(cp / "70_certification_impact_propagation.json")

    decision_latest = _latest_entry(decision_chain)
    feedback_latest = _latest_entry(feedback_chain)

    decision_count = len([row for row in decision_chain.get("entries", []) if isinstance(row, dict)])
    feedback_count = len([row for row in feedback_chain.get("entries", []) if isinstance(row, dict)])

    return {
        "control_plane_dir": str(cp),
        "decision_chain": {
            "path": "control_plane/58_decision_envelope_chain.json",
            "entries": decision_count,
            "latest_stage": str(decision_latest.get("stage_name", "")),
            "latest_gate": str(decision_latest.get("gate_decision", "")),
            "latest_entry_hash": str(decision_latest.get("entry_hash", "")),
        },
        "feedback_chain": {
            "path": "control_plane/65_outcome_feedback_chain.json",
            "entries": feedback_count,
            "latest_action": str(feedback_latest.get("action_type", "")),
            "latest_status": str(feedback_latest.get("outcome_status", "")),
            "latest_entry_hash": str(feedback_latest.get("entry_hash", "")),
        },
        "propagation": {
            "confidence_present": bool(confidence_payload),
            "recurrence_present": bool(recurrence_payload),
            "calibration_present": bool(calibration_payload),
            "certification_impact_present": bool(cert_impact_payload),
            "confidence_chain_status": str(confidence_payload.get("chain_status", "")),
            "predictive_mutation_policy": str(calibration_payload.get("predictive_mutation_policy", "")),
            "certification_mutation_policy": str(cert_impact_payload.get("certification_mutation_policy", "")),
            "max_per_event_delta": _safe_float(confidence_payload.get("max_per_event_delta", 0.0)),
            "max_cumulative_delta": _safe_float(confidence_payload.get("max_cumulative_delta", 0.0)),
        },
    }


def gather_operational_surfaces(*, pf: Path) -> dict[str, Any]:
    execution_summary = _read_json(pf / "execution" / "130_execution_plan.json")
    pipeline_summary = _read_json(pf / "pipeline" / "143_pipeline_chain_decision.json")
    workflow_summary = _read_json(pf / "workflow" / "150_primary_workflow_recommendation.json")
    history_summary = _read_json(pf / "history" / "52_regression_trend_analysis.json")
    predictive_summary = _read_json(pf / "predictive" / "64_prediction_classification.json")
    intelligence_summary = _read_json(pf / "intelligence" / "110_component_watchlist.json")
    hotspot_summary = _read_json(pf / "hotspots" / "09_regression_hotspots.json")
    explain_summary = _read_json(pf / "control_plane" / "74_explain_control_plane_summary.json")

    prediction = predictive_summary.get("prediction", {}) if isinstance(predictive_summary.get("prediction", {}), dict) else {}
    aggregate_impact = hotspot_summary.get("aggregate_impact", {}) if isinstance(hotspot_summary.get("aggregate_impact", {}), dict) else {}

    return {
        "execution": {
            "execution_policy": str(execution_summary.get("execution_policy", "")),
            "effective_touched_components": execution_summary.get("effective_touched_components", []),
        },
        "pipeline": {
            "final_combined_state": str(pipeline_summary.get("final_combined_state", "")),
            "chain_gate": str(pipeline_summary.get("chain_gate", "")),
            "rerun_decision": str(pipeline_summary.get("rerun_decision", "")),
        },
        "workflow": {
            "primary_action": str(workflow_summary.get("primary_action", "")),
            "primary_reason": str(workflow_summary.get("primary_reason", "")),
        },
        "history": {
            "trend_classification": str(history_summary.get("trend_classification", "")),
            "trend_reason": str(history_summary.get("trend_reason", "")),
            "component_count": _safe_int(history_summary.get("component_count", 0)),
        },
        "predictive": {
            "overall_risk_class": str(prediction.get("overall_risk_class", "")),
            "overall_risk_score": _safe_float(prediction.get("overall_risk_score", 0.0)),
            "resolution_adjusted_risk_score": _safe_float(prediction.get("resolution_adjusted_risk_score", 0.0)),
            "highest_risk_component": str(prediction.get("highest_risk_component", "")),
        },
        "intelligence": {
            "insufficient_history": bool(intelligence_summary.get("insufficient_history", False)),
            "watch_rows": len([row for row in intelligence_summary.get("rows", []) if isinstance(row, dict)]),
        },
        "hotspots": {
            "classification": str(aggregate_impact.get("classification", "")),
            "regressed_scenarios": _safe_int(aggregate_impact.get("total_regressed_scenarios", 0)),
            "top_metric": str((aggregate_impact.get("top_metric_regression", {}) if isinstance(aggregate_impact.get("top_metric_regression", {}), dict) else {}).get("metric", "")),
        },
        "explain": {
            "latest_entity": str(explain_summary.get("latest_entity", "")),
            "latest_confidence": str(explain_summary.get("latest_confidence", "")),
            "explain_gate": str(explain_summary.get("explain_gate", "")),
        },
    }


def compute_operational_governance_state(*, control_plane_context: dict[str, Any], surfaces: dict[str, Any]) -> str:
    decision_gate = str((control_plane_context.get("decision_chain", {}) if isinstance(control_plane_context.get("decision_chain", {}), dict) else {}).get("latest_gate", ""))
    pipeline_gate = str((surfaces.get("pipeline", {}) if isinstance(surfaces.get("pipeline", {}), dict) else {}).get("chain_gate", ""))

    if decision_gate in {"FAIL", "BLOCK", "INVALID_CHAIN"}:
        return "ATTENTION_REQUIRED"
    if pipeline_gate == "FAIL":
        return "ATTENTION_REQUIRED"
    if not decision_gate and not pipeline_gate:
        return "UNKNOWN"
    return "ALIGNED"


def write_control_plane_summary(*, pf: Path, file_name: str, payload: dict[str, Any]) -> str:
    cp = (pf / "control_plane").resolve()
    _write_json(cp / file_name, payload)
    return str((cp / file_name).resolve())
