from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .receipts import write_json, write_text


ACTION_EXECUTOR_ENUM = {"system", "operator", "mixed"}
RECURRENCE_CATEGORIES = {"reduced", "unchanged", "increased"}
HASH_EXCLUSION_FIELDS = {"timestamp_utc", "writer_runtime_ms", "local_path_variants"}


@dataclass
class FeedbackContext:
    pf: Path
    run_id: str
    parent_run_id: str | None


class OutcomeFeedbackManager:
    def __init__(self, *, context: FeedbackContext) -> None:
        self._context = context
        self._cp = (context.pf / "control_plane").resolve()
        self._cp.mkdir(parents=True, exist_ok=True)
        self._chain_path = self._cp / "65_outcome_feedback_chain.json"
        self._schema_path = Path(__file__).with_name("outcome_feedback_schema.json")
        self._reason_codes_path = Path(__file__).with_name("outcome_feedback_reason_codes.json")
        self._write_static_contracts()
        self._materialize_views()

    @property
    def control_plane_dir(self) -> Path:
        return self._cp

    def append_feedback(
        self,
        *,
        stage_id: str,
        stage_name: str,
        linked_envelope_hash: str,
        action_id: str,
        action_proposed: bool,
        action_taken: bool,
        action_executor: str,
        observed_result_code: str,
        observed_result_summary: str,
        observed_gate_change: str,
        confidence_adjustment_delta: float,
        confidence_adjustment_reason: str,
        recurrence_impact_category: str,
        recurrence_impact_delta: float,
        predictive_calibration_delta: float,
        predictive_calibration_reason: str,
        certification_impact: str,
        supporting_evidence_refs: list[str] | None = None,
        ruleset_version: str = "phase1b.v1",
        cycle_id: str | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()

        executor = str(action_executor).strip().lower()
        if executor not in ACTION_EXECUTOR_ENUM:
            raise ValueError(f"invalid action_executor: {action_executor}")

        recurrence = str(recurrence_impact_category).strip().lower()
        if recurrence not in RECURRENCE_CATEGORIES:
            raise ValueError(f"invalid recurrence_impact_category: {recurrence_impact_category}")

        delta = float(confidence_adjustment_delta)
        if abs(delta) > 0.05:
            raise ValueError("confidence_adjustment_delta exceeds per-event absolute bound 0.05")

        chain = self._load_chain()
        cycle_key = str(cycle_id or self._context.parent_run_id or self._context.run_id)
        cumulative = abs(delta)
        for row in chain:
            if str(row.get("cycle_id", "")) == cycle_key:
                cumulative += abs(float(row.get("confidence_adjustment_delta", 0.0)))
        if cumulative > 0.10:
            raise ValueError("confidence adjustment cumulative absolute bound 0.10 exceeded for cycle")

        prev_hash = chain[-1].get("feedback_hash", "GENESIS") if chain else "GENESIS"
        seq = len(chain) + 1

        entry: dict[str, Any] = {
            "feedback_version": "1.0.0",
            "run_id": self._context.run_id,
            "parent_run_id": self._context.parent_run_id,
            "stage_id": str(stage_id),
            "stage_name": str(stage_name),
            "linked_envelope_hash": str(linked_envelope_hash),
            "feedback_sequence_index": seq,
            "timestamp_utc": _iso_now(),
            "action_id": str(action_id),
            "action_proposed": bool(action_proposed),
            "action_taken": bool(action_taken),
            "action_executor": executor,
            "action_timestamp_utc": _iso_now(),
            "observed_result_code": str(observed_result_code),
            "observed_result_summary": str(observed_result_summary),
            "observed_gate_change": str(observed_gate_change),
            "confidence_adjustment_delta": delta,
            "confidence_adjustment_reason": str(confidence_adjustment_reason),
            "recurrence_impact_category": recurrence,
            "recurrence_impact_delta": float(recurrence_impact_delta),
            "predictive_calibration_delta": float(predictive_calibration_delta),
            "predictive_calibration_reason": str(predictive_calibration_reason),
            "certification_impact": str(certification_impact),
            "supporting_evidence_refs": list(supporting_evidence_refs or []),
            "previous_feedback_hash": str(prev_hash),
            "ruleset_version": str(ruleset_version),
            "cycle_id": cycle_key,
            "writer_runtime_ms": 0.0,
            "local_path_variants": [],
        }

        entry["feedback_hash"] = _semantic_hash(entry)
        entry["writer_runtime_ms"] = round((perf_counter() - started) * 1000.0, 3)

        chain.append(entry)
        write_json(self._chain_path, {"schema": "ngks.outcome_feedback.chain.v1", "entries": chain})
        self._materialize_views()
        return entry

    def replay_hash_stability_check(self) -> dict[str, Any]:
        chain = self._load_chain()
        parent_expected = "GENESIS"
        rows: list[dict[str, Any]] = []
        ok = True
        for row in chain:
            calc = _semantic_hash(_for_hash_payload(row))
            this_hash_ok = calc == str(row.get("feedback_hash", ""))
            this_parent_ok = str(row.get("previous_feedback_hash", "")) == parent_expected
            rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "hash_ok": this_hash_ok,
                    "parent_ok": this_parent_ok,
                }
            )
            ok = ok and this_hash_ok and this_parent_ok
            parent_expected = str(row.get("feedback_hash", ""))
        return {"status": "PASS" if ok else "FAIL", "rows": rows}

    def _write_static_contracts(self) -> None:
        if self._schema_path.exists():
            payload = _read_json(self._schema_path)
            if payload:
                write_json(self._cp / "outcome_feedback_schema.json", payload)
        if self._reason_codes_path.exists():
            payload = _read_json(self._reason_codes_path)
            if payload:
                write_json(self._cp / "outcome_feedback_reason_codes.json", payload)

    def _load_chain(self) -> list[dict[str, Any]]:
        if not self._chain_path.exists():
            return []
        payload = _read_json(self._chain_path)
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        rows = [row for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
        rows.sort(key=lambda row: int(row.get("feedback_sequence_index", 0)))
        return rows

    def _materialize_views(self) -> None:
        chain = self._load_chain()

        action_rows = []
        observed_rows = []
        confidence_rows = []
        recurrence_rows = []
        predictive_rows = []

        for row in chain:
            action_rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "action_id": row.get("action_id"),
                    "action_proposed": row.get("action_proposed"),
                    "action_taken": row.get("action_taken"),
                    "action_executor": row.get("action_executor"),
                    "linked_envelope_hash": row.get("linked_envelope_hash"),
                    "stage_name": row.get("stage_name"),
                }
            )
            observed_rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "observed_result_code": row.get("observed_result_code"),
                    "observed_result_summary": row.get("observed_result_summary"),
                    "observed_gate_change": row.get("observed_gate_change"),
                    "certification_impact": row.get("certification_impact"),
                    "linked_envelope_hash": row.get("linked_envelope_hash"),
                }
            )
            confidence_rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "confidence_adjustment_delta": row.get("confidence_adjustment_delta"),
                    "confidence_adjustment_reason": row.get("confidence_adjustment_reason"),
                    "cycle_id": row.get("cycle_id"),
                }
            )
            recurrence_rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "recurrence_impact_category": row.get("recurrence_impact_category"),
                    "recurrence_impact_delta": row.get("recurrence_impact_delta"),
                }
            )
            predictive_rows.append(
                {
                    "feedback_sequence_index": row.get("feedback_sequence_index"),
                    "predictive_calibration_delta": row.get("predictive_calibration_delta"),
                    "predictive_calibration_reason": row.get("predictive_calibration_reason"),
                    "model_mutation": "none",
                }
            )

        write_json(self._cp / "60_outcome_feedback_actions.json", {"rows": action_rows})
        write_json(self._cp / "61_outcome_feedback_observed_results.json", {"rows": observed_rows})
        write_json(self._cp / "62_outcome_feedback_confidence_adjustments.json", {"rows": confidence_rows})
        write_json(self._cp / "63_outcome_feedback_recurrence_impact.json", {"rows": recurrence_rows})
        write_json(self._cp / "64_outcome_feedback_predictive_calibration.json", {"rows": predictive_rows, "model_mutation": "none"})

        summary_lines = [
            "# Outcome Feedback Summary",
            "",
            f"- run_id: {self._context.run_id}",
            f"- parent_run_id: {self._context.parent_run_id or 'none'}",
            f"- feedback_entries: {len(chain)}",
            f"- action_taken_count: {sum(1 for row in chain if bool(row.get('action_taken', False)))}",
            f"- operator_action_count: {sum(1 for row in chain if str(row.get('action_executor', '')).lower() == 'operator')}",
            f"- mixed_action_count: {sum(1 for row in chain if str(row.get('action_executor', '')).lower() == 'mixed')}",
            "- authoritative_chain: control_plane/65_outcome_feedback_chain.json",
            "- predictive_model_mutation: none",
        ]
        write_text(self._cp / "66_outcome_feedback_summary.md", "\n".join(summary_lines) + "\n")


def create_feedback_manager(*, pf: Path, run_id: str, parent_run_id: str | None = None) -> OutcomeFeedbackManager:
    return OutcomeFeedbackManager(context=FeedbackContext(pf=pf.resolve(), run_id=run_id, parent_run_id=parent_run_id))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _for_hash_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry)
    payload.pop("feedback_hash", None)
    return payload


def _strip_non_semantic(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in HASH_EXCLUSION_FIELDS:
                continue
            out[key] = _strip_non_semantic(value[key])
        return out
    if isinstance(value, list):
        return [_strip_non_semantic(item) for item in value]
    return value


def _semantic_hash(entry: dict[str, Any]) -> str:
    canonical = _strip_non_semantic(_for_hash_payload(entry))
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
