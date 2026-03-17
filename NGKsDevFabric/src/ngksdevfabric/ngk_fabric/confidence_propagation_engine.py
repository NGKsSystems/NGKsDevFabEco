from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .calibration_propagation_engine import run_calibration_propagation
from .receipts import write_json, write_text


def run_confidence_propagation(*, pf: Path, ruleset_version: str = "phase1d.v1") -> dict[str, Any]:
    cp = (pf / "control_plane").resolve()
    cp.mkdir(parents=True, exist_ok=True)

    feedback_chain = _read_json(cp / "65_outcome_feedback_chain.json")
    rows = feedback_chain.get("entries", []) if isinstance(feedback_chain, dict) else []
    feedback_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    feedback_rows.sort(key=lambda row: int(row.get("feedback_sequence_index", 0)))

    run_id = str(feedback_rows[-1].get("run_id", "")) if feedback_rows else ""
    parent_run_id = str(feedback_rows[-1].get("parent_run_id", "")) if feedback_rows else ""
    parent_run_id = parent_run_id if parent_run_id else None

    input_confidence = _initial_confidence_from_history(pf)
    recurrence_prior = _initial_recurrence_from_history_trends(pf)
    cert_prior = _initial_certification_impact(pf)

    confidence_rows: list[dict[str, Any]] = []
    recurrence_rows: list[dict[str, Any]] = []
    cert_rows: list[dict[str, Any]] = []
    bound_violations: list[dict[str, Any]] = []
    cycle_abs_deltas: dict[str, float] = {}

    for fb in feedback_rows:
        feedback_hash = str(fb.get("feedback_hash", ""))
        action_id = str(fb.get("action_id", ""))
        stage = str(fb.get("stage_name", ""))
        cycle_id = str(fb.get("cycle_id", run_id or "default"))
        delta = _safe_float(fb.get("confidence_adjustment_delta", 0.0))

        event_ok = abs(delta) <= 0.05
        cycle_abs_deltas[cycle_id] = cycle_abs_deltas.get(cycle_id, 0.0) + abs(delta)
        cumulative_ok = cycle_abs_deltas[cycle_id] <= 0.10
        if not event_ok or not cumulative_ok:
            bound_violations.append(
                {
                    "source_feedback_hash": feedback_hash,
                    "cycle_id": cycle_id,
                    "event_abs_delta": abs(delta),
                    "cycle_abs_delta": round(cycle_abs_deltas[cycle_id], 6),
                    "reason_code": "CONFIDENCE_BOUND_VIOLATION",
                }
            )

        out_confidence = _clamp(input_confidence + delta, 0.0, 1.0)

        recurrence_delta = _safe_float(fb.get("recurrence_impact_delta", 0.0))
        recurrence_new = recurrence_prior + recurrence_delta

        cert_delta = _certification_delta_from_feedback(str(fb.get("certification_impact", "none")))
        cert_new = cert_prior + cert_delta

        refs = [
            "control_plane/65_outcome_feedback_chain.json",
            "history/50_component_health_scores.json",
            "history/52_regression_trend_analysis.json",
            "predictive/64_prediction_classification.json",
            "predictive/66_resolution_adjusted_risk.json",
            "rollup/04_rollup_decision.json",
            "certification/09_gate_result.json",
        ]
        refs.extend(_string_list(fb.get("supporting_evidence_refs", [])))
        refs = sorted({str(item) for item in refs if str(item).strip()})

        base_row = {
            "propagation_version": "1.0.0",
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "source_feedback_hash": feedback_hash,
            "source_feedback_action_id": action_id,
            "propagation_stage": stage,
            "input_confidence": round(input_confidence, 4),
            "delta_applied": round(delta, 4),
            "output_confidence": round(out_confidence, 4),
            "recurrence_prior": round(recurrence_prior, 4),
            "recurrence_delta": round(recurrence_delta, 4),
            "recurrence_new": round(recurrence_new, 4),
            "predictive_metric_prior": 0.0,
            "predictive_metric_delta": 0.0,
            "predictive_metric_new": 0.0,
            "certification_impact_prior": round(cert_prior, 4),
            "certification_impact_delta": round(cert_delta, 4),
            "certification_impact_new": round(cert_new, 4),
            "supporting_evidence_refs": refs,
            "ruleset_version": ruleset_version,
            "timestamp_utc": str(fb.get("timestamp_utc", "")),
        }

        confidence_rows.append(
            {
                **base_row,
                "reason_code": "CONFIDENCE_DELTA_PROPAGATED" if event_ok and cumulative_ok else "CONFIDENCE_BOUND_VIOLATION",
                "bound_checks": {
                    "per_event_abs_delta_ok": event_ok,
                    "cumulative_abs_cycle_ok": cumulative_ok,
                    "cycle_id": cycle_id,
                    "cycle_abs_delta": round(cycle_abs_deltas[cycle_id], 6),
                },
            }
        )

        recurrence_rows.append(
            {
                **base_row,
                "reason_code": "RECURRENCE_PROPAGATED",
            }
        )

        cert_rows.append(
            {
                **base_row,
                "reason_code": "CERTIFICATION_IMPACT_PROPAGATED",
            }
        )

        input_confidence = out_confidence
        recurrence_prior = recurrence_new
        cert_prior = cert_new

    confidence_payload = {
        "propagation_version": "1.0.0",
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "ruleset_version": ruleset_version,
        "bounds": {
            "per_event_abs_limit": 0.05,
            "cumulative_abs_limit_per_cycle": 0.10,
            "violations": bound_violations,
        },
        "rows": confidence_rows,
    }
    recurrence_payload = {
        "propagation_version": "1.0.0",
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "ruleset_version": ruleset_version,
        "rows": recurrence_rows,
    }
    cert_payload = {
        "propagation_version": "1.0.0",
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "ruleset_version": ruleset_version,
        "rows": cert_rows,
    }

    write_json(cp / "67_confidence_propagation.json", confidence_payload)
    write_json(cp / "68_recurrence_propagation.json", recurrence_payload)
    write_json(cp / "70_certification_impact_propagation.json", cert_payload)

    calibration_payload = run_calibration_propagation(
        pf=pf,
        feedback_rows=feedback_rows,
        run_id=run_id,
        parent_run_id=parent_run_id,
        ruleset_version=ruleset_version,
    )

    summary_lines = [
        "# Propagation Summary",
        "",
        f"- run_id: {run_id or 'none'}",
        f"- parent_run_id: {parent_run_id or 'none'}",
        f"- confidence_rows: {len(confidence_rows)}",
        f"- recurrence_rows: {len(recurrence_rows)}",
        f"- predictive_calibration_rows: {len(calibration_payload.get('rows', []))}",
        f"- certification_rows: {len(cert_rows)}",
        f"- bound_violations: {len(bound_violations)}",
        "- predictive_model_mutation: none",
        "- policy_threshold_mutation: none",
    ]
    write_text(cp / "71_propagation_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "confidence": confidence_payload,
        "recurrence": recurrence_payload,
        "predictive": calibration_payload,
        "certification": cert_payload,
        "bound_violations": bound_violations,
        "artifacts": [
            "control_plane/67_confidence_propagation.json",
            "control_plane/68_recurrence_propagation.json",
            "control_plane/69_predictive_calibration_propagation.json",
            "control_plane/70_certification_impact_propagation.json",
            "control_plane/71_propagation_summary.md",
        ],
    }


def _initial_confidence_from_history(pf: Path) -> float:
    data = _read_json(pf / "history" / "50_component_health_scores.json")
    rows = data.get("rows", []) if isinstance(data, dict) else []
    if not isinstance(rows, list) or not rows:
        return 0.5
    vals = [_safe_float(row.get("health_score", 0.5)) for row in rows if isinstance(row, dict)]
    if not vals:
        return 0.5
    return _clamp(sum(vals) / len(vals), 0.0, 1.0)


def _initial_recurrence_from_history_trends(pf: Path) -> float:
    data = _read_json(pf / "history" / "52_regression_trend_analysis.json")
    cls = str(data.get("trend_classification", "STABLE")).upper()
    if cls == "RISING":
        return 1.0
    if cls == "IMPROVING":
        return -1.0
    return 0.0


def _initial_certification_impact(pf: Path) -> float:
    rollup = _read_json(pf / "rollup" / "04_rollup_decision.json")
    decision = str(rollup.get("certification_decision", "")).upper()
    if decision == "CERTIFIED_IMPROVEMENT":
        return 1.0
    if decision == "CERTIFIED_REGRESSION":
        return -1.0

    gate = _read_json(pf / "certification" / "09_gate_result.json")
    enforced = str(gate.get("enforced_gate", "")).upper()
    if enforced == "PASS":
        return 0.5
    if enforced == "FAIL":
        return -0.5
    return 0.0


def _certification_delta_from_feedback(value: str) -> float:
    impact = str(value).strip().lower()
    mapping = {
        "positive": 0.5,
        "negative": -0.5,
        "blocked": -0.25,
        "stable": 0.0,
        "none": 0.0,
    }
    return mapping.get(impact, 0.0)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
