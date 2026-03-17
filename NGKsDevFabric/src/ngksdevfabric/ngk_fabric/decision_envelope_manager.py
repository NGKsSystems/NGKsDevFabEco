from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .receipts import write_json, write_text


STAGE_ORDER = [
    "preflight",
    "planning",
    "pre-build",
    "execution",
    "post-build",
    "certification",
    "rerun-remediation",
]

STAGE_OWNER_MAP = {
    "preflight": "DevFabric",
    "planning": "NGKsGraph",
    "pre-build": "DevFabric",
    "execution": "NGKsBuildCore",
    "post-build": "DevFabric",
    "certification": "DevFabric",
    "rerun-remediation": "DevFabric",
}

GATE_ENUM = {
    "PASS",
    "FAIL",
    "BLOCK",
    "WARN",
    "ADVISORY",
    "SKIP",
    "INCOMPLETE",
    "INVALID_CHAIN",
}

_HASH_EXCLUDED_KEYS = {"timestamp_utc", "writer_runtime_ms", "local_path_variants"}


@dataclass
class EnvelopeContext:
    pf: Path
    run_id: str
    parent_run_id: str | None
    trigger: str


class DecisionEnvelopeManager:
    def __init__(self, *, context: EnvelopeContext) -> None:
        self._context = context
        self._cp = (context.pf / "control_plane").resolve()
        self._cp.mkdir(parents=True, exist_ok=True)
        self._chain_path = self._cp / "58_decision_envelope_chain.json"
        self._reason_codes_path = Path(__file__).with_name("decision_reason_codes.json")
        self._schema_path = Path(__file__).with_name("decision_envelope_schema.json")

        self._write_static_contracts()

    @property
    def control_plane_dir(self) -> Path:
        return self._cp

    def write_stage(
        self,
        *,
        stage_name: str,
        gate_decision: str,
        reason_codes: list[str],
        evidence_refs: list[str] | None = None,
        missing_inputs: list[str] | None = None,
        normalized_findings: list[dict[str, Any]] | None = None,
        action_records: list[dict[str, Any]] | None = None,
        owner_component: str | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        stage = str(stage_name).strip()
        gate = str(gate_decision).strip().upper()

        if stage not in STAGE_ORDER:
            raise ValueError(f"invalid stage_name: {stage}")
        if gate not in GATE_ENUM:
            raise ValueError(f"invalid gate_decision: {gate}")

        reasons = [str(code).strip() for code in (reason_codes or []) if str(code).strip()]
        if not reasons:
            raise ValueError("reason_codes must contain at least one code")

        chain = self._load_chain()
        parent_hash = chain[-1].get("entry_hash", "GENESIS") if chain else "GENESIS"
        chain_index = len(chain) + 1

        entry: dict[str, Any] = {
            "schema": "ngks.decision.envelope.entry.v1",
            "schema_version": "1.0.0",
            "run_id": self._context.run_id,
            "parent_run_id": self._context.parent_run_id,
            "chain_index": chain_index,
            "stage_name": stage,
            "owner_component": owner_component or STAGE_OWNER_MAP.get(stage, "DevFabric"),
            "gate_decision": gate,
            "reason_codes": reasons,
            "missing_inputs": list(missing_inputs or []),
            "normalized_findings": list(normalized_findings or []),
            "evidence_refs": list(evidence_refs or []),
            "action_records": list(action_records or []),
            "parent_hash": str(parent_hash),
            "timestamp_utc": _iso_now(),
            "writer_runtime_ms": 0.0,
            "local_path_variants": [],
            "trigger": self._context.trigger,
        }

        entry["entry_hash"] = _semantic_hash(entry)
        entry["writer_runtime_ms"] = round((perf_counter() - started) * 1000.0, 3)

        chain.append(entry)
        write_json(self._chain_path, {"schema": "ngks.decision.envelope.chain.v1", "entries": chain})

        self._materialize_views()
        return entry

    def finalize_missing_stages(self) -> None:
        chain = self._load_chain()
        present = {str(row.get("stage_name", "")) for row in chain if isinstance(row, dict)}
        for stage in STAGE_ORDER:
            if stage in present:
                continue
            if stage == "certification":
                self.write_stage(
                    stage_name=stage,
                    gate_decision="SKIP",
                    reason_codes=["CERTIFICATION_NOT_REQUESTED"],
                    missing_inputs=["certification_inputs"],
                )
            elif stage == "rerun-remediation":
                self.write_stage(
                    stage_name=stage,
                    gate_decision="SKIP",
                    reason_codes=["RERUN_NOT_REQUESTED"],
                    missing_inputs=["rerun_request"],
                )
            else:
                self.write_stage(
                    stage_name=stage,
                    gate_decision="SKIP",
                    reason_codes=["PRIOR_UNCLOSED_STAGE"],
                    missing_inputs=["stage_not_reached"],
                )

    def _write_static_contracts(self) -> None:
        if self._reason_codes_path.exists():
            payload = _read_json(self._reason_codes_path)
            if payload:
                write_json(self._cp / "decision_reason_codes.json", payload)
        if self._schema_path.exists():
            payload = _read_json(self._schema_path)
            if payload:
                write_json(self._cp / "decision_envelope_schema.json", payload)

    def _load_chain(self) -> list[dict[str, Any]]:
        if not self._chain_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            payload = json.loads(self._chain_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return []
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        for item in entries if isinstance(entries, list) else []:
            if isinstance(item, dict):
                rows.append(item)
        rows.sort(key=lambda row: int(row.get("chain_index", 0)))
        return rows

    def _materialize_views(self) -> None:
        chain = self._load_chain()
        latest_by_stage: dict[str, dict[str, Any]] = {}
        invalid_chain = False
        expected_parent = "GENESIS"

        for row in chain:
            stage = str(row.get("stage_name", ""))
            if stage:
                latest_by_stage[stage] = row
            if str(row.get("parent_hash", "")) != expected_parent:
                invalid_chain = True
            expected_parent = str(row.get("entry_hash", ""))

        stage_files = {
            "preflight": "51_decision_envelope_preflight.json",
            "planning": "52_decision_envelope_planning.json",
            "pre-build": "53_decision_envelope_pre_build.json",
            "execution": "54_decision_envelope_execution.json",
            "post-build": "55_decision_envelope_post_build.json",
            "certification": "56_decision_envelope_certification.json",
            "rerun-remediation": "57_decision_envelope_rerun_remediation.json",
        }

        for stage in STAGE_ORDER:
            payload = {
                "schema": "ngks.decision.envelope.stage_view.v1",
                "run_id": self._context.run_id,
                "stage_name": stage,
                "entry": latest_by_stage.get(stage),
            }
            write_json(self._cp / stage_files[stage], payload)

        final_gate = "SKIP"
        if chain:
            final_gate = str(chain[-1].get("gate_decision", "SKIP"))
        if invalid_chain:
            final_gate = "INVALID_CHAIN"

        gate_counts: dict[str, int] = {}
        for row in chain:
            gate = str(row.get("gate_decision", "UNKNOWN"))
            gate_counts[gate] = gate_counts.get(gate, 0) + 1

        summary = {
            "run_id": self._context.run_id,
            "parent_run_id": self._context.parent_run_id,
            "trigger": self._context.trigger,
            "chain_entries": len(chain),
            "stages_present": sorted(latest_by_stage.keys()),
            "gate_counts": gate_counts,
            "chain_integrity": "INVALID_CHAIN" if invalid_chain else "OK",
            "final_gate": final_gate,
            "latest_entry_hash": str(chain[-1].get("entry_hash", "")) if chain else "",
        }

        lines = [
            "# Decision Envelope Summary",
            "",
            f"- run_id: {self._context.run_id}",
            f"- parent_run_id: {self._context.parent_run_id or 'none'}",
            f"- trigger: {self._context.trigger}",
            f"- chain_entries: {len(chain)}",
            f"- chain_integrity: {summary['chain_integrity']}",
            f"- final_gate: {final_gate}",
            "- gate_counts:",
        ]
        for gate, count in sorted(gate_counts.items()):
            lines.append(f"  - {gate}: {count}")
        write_text(self._cp / "59_decision_envelope_summary.md", "\n".join(lines) + "\n")


def create_manager(*, pf: Path, run_id: str, trigger: str, parent_run_id: str | None = None) -> DecisionEnvelopeManager:
    context = EnvelopeContext(pf=pf.resolve(), run_id=run_id, parent_run_id=parent_run_id, trigger=trigger)
    return DecisionEnvelopeManager(context=context)


def make_finding(
    *,
    source_component: str,
    source_artifact: str,
    severity: str,
    reason_code: str,
    confidence_score: float,
    blocking: bool,
    evidence_refs: list[str],
    stage_name: str,
) -> dict[str, Any]:
    score = max(0.0, min(1.0, float(confidence_score)))
    if score >= 0.8:
        band = "HIGH"
    elif score >= 0.5:
        band = "MEDIUM"
    else:
        band = "LOW"
    return {
        "source_component": str(source_component),
        "source_artifact": str(source_artifact),
        "severity": str(severity),
        "reason_code": str(reason_code),
        "confidence": {"score": score, "band": band},
        "blocking": bool(blocking),
        "evidence_refs": list(evidence_refs),
        "timestamp_utc": _iso_now(),
        "stage_name": str(stage_name),
    }


def _strip_non_semantic(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in _HASH_EXCLUDED_KEYS:
                continue
            out[key] = _strip_non_semantic(value[key])
        return out
    if isinstance(value, list):
        return [_strip_non_semantic(item) for item in value]
    return value


def _semantic_hash(entry: dict[str, Any]) -> str:
    canonical = _strip_non_semantic(entry)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
