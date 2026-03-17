from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .receipts import write_json


def run_calibration_propagation(
    *,
    pf: Path,
    feedback_rows: list[dict[str, Any]],
    run_id: str,
    parent_run_id: str | None,
    ruleset_version: str,
) -> dict[str, Any]:
    cp = (pf / "control_plane").resolve()
    cp.mkdir(parents=True, exist_ok=True)

    prior_metric = _initial_predictive_metric(pf)
    rows: list[dict[str, Any]] = []

    for fb in feedback_rows:
        delta = float(fb.get("predictive_calibration_delta", 0.0))
        new_metric = _clamp(prior_metric + delta, 0.0, 1.0)
        refs = [
            "control_plane/65_outcome_feedback_chain.json",
            "predictive/64_prediction_classification.json",
            "predictive/66_resolution_adjusted_risk.json",
        ]
        refs.extend(_string_list(fb.get("supporting_evidence_refs", [])))

        rows.append(
            {
                "propagation_version": "1.0.0",
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "source_feedback_hash": str(fb.get("feedback_hash", "")),
                "source_feedback_action_id": str(fb.get("action_id", "")),
                "propagation_stage": str(fb.get("stage_name", "")),
                "reason_code": "PREDICTIVE_CALIBRATION_FROM_REPORTING_ONLY",
                "input_confidence": _safe_float(fb.get("confidence_adjustment_delta", 0.0)),
                "delta_applied": _safe_float(fb.get("confidence_adjustment_delta", 0.0)),
                "output_confidence": _safe_float(fb.get("confidence_adjustment_delta", 0.0)),
                "recurrence_prior": _safe_float(fb.get("recurrence_impact_delta", 0.0)),
                "recurrence_delta": _safe_float(fb.get("recurrence_impact_delta", 0.0)),
                "recurrence_new": _safe_float(fb.get("recurrence_impact_delta", 0.0)),
                "predictive_metric_prior": round(prior_metric, 4),
                "predictive_metric_delta": round(delta, 4),
                "predictive_metric_new": round(new_metric, 4),
                "certification_impact_prior": 0.0,
                "certification_impact_delta": 0.0,
                "certification_impact_new": 0.0,
                "supporting_evidence_refs": sorted({str(r) for r in refs if str(r).strip()}),
                "ruleset_version": ruleset_version,
                "timestamp_utc": str(fb.get("timestamp_utc", "")),
                "predictive_model_mutation": "none",
                "policy_threshold_mutation": "none",
            }
        )
        prior_metric = new_metric

    payload = {
        "propagation_version": "1.0.0",
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "ruleset_version": ruleset_version,
        "model_mutation": "none",
        "policy_threshold_mutation": "none",
        "rows": rows,
    }
    write_json(cp / "69_predictive_calibration_propagation.json", payload)
    return payload


def _initial_predictive_metric(pf: Path) -> float:
    p64 = _read_json(pf / "predictive" / "64_prediction_classification.json")
    prediction = p64.get("prediction", {}) if isinstance(p64.get("prediction", {}), dict) else {}
    score = prediction.get("overall_risk_score", None)
    if score is not None:
        return _clamp(_safe_float(score), 0.0, 1.0)

    p66 = _read_json(pf / "predictive" / "66_resolution_adjusted_risk.json")
    score = p66.get("resolution_adjusted_risk_score", None)
    if score is not None:
        return _clamp(_safe_float(score), 0.0, 1.0)
    return 0.5


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
