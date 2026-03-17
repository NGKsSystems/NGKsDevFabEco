from __future__ import annotations

from pathlib import Path
from typing import Any

from .replay_hash_utils import HASH_EXCLUSION_FIELDS, load_chain_rows, missing_refs_for_row, read_json, semantic_sha256


def validate_feedback_chain_from_proof(
    *,
    proof_root: Path,
    chain_relative_path: str = "control_plane/65_outcome_feedback_chain.json",
    strict_mode: bool = True,
) -> dict[str, Any]:
    root = proof_root.resolve()
    chain_path = (root / chain_relative_path).resolve()
    if not chain_path.exists():
        return {
            "status": "FAIL",
            "strict_mode": strict_mode,
            "strict_replay_input_boundary": "proof_artifacts_only",
            "chain_path": chain_relative_path,
            "error": "missing_feedback_chain",
            "rows": [],
            "linked_envelope_hashes": [],
        }

    rows, order_stable = load_chain_rows(chain_path, index_field="feedback_sequence_index")
    expected_parent = "GENESIS"
    ok = order_stable
    linked_hashes: set[str] = set()
    replay_reason_codes: set[str] = set()
    per_row: list[dict[str, Any]] = []

    for row in rows:
        computed = semantic_sha256(row, hash_field="feedback_hash")
        stored_hash = str(row.get("feedback_hash", ""))
        parent_hash = str(row.get("previous_feedback_hash", ""))
        linked_hash = str(row.get("linked_envelope_hash", "")).strip()
        linked_ok = bool(linked_hash)
        hash_ok = computed == stored_hash
        parent_ok = parent_hash == expected_parent
        this_ok = hash_ok and parent_ok and linked_ok
        ok = ok and this_ok

        row_reasons: set[str] = set()
        if not linked_ok:
            row_reasons.add("missing_linked_envelope_hash")

        refs = row.get("supporting_evidence_refs", [])
        if isinstance(refs, list):
            for reason in missing_refs_for_row(root, [str(r) for r in refs]):
                row_reasons.add(reason)

        replay_reason_codes.update(row_reasons)
        if linked_ok:
            linked_hashes.add(linked_hash)

        per_row.append(
            {
                "feedback_sequence_index": int(row.get("feedback_sequence_index", 0)),
                "hash_ok": hash_ok,
                "previous_hash_ok": parent_ok,
                "linked_envelope_hash_present": linked_ok,
                "replay_reason_codes": sorted(row_reasons),
            }
        )
        expected_parent = stored_hash

    return {
        "status": "PASS" if ok else "FAIL",
        "strict_mode": strict_mode,
        "strict_replay_input_boundary": "proof_artifacts_only",
        "chain_path": chain_relative_path,
        "rows": per_row,
        "chain_order_stable": order_stable,
        "linked_envelope_hashes": sorted(linked_hashes),
        "replay_reason_codes": sorted(replay_reason_codes),
        "hash_exclusion_fields": sorted(HASH_EXCLUSION_FIELDS),
    }


def validate_cross_chain_links(
    *,
    proof_root: Path,
    decision_chain_relative_path: str = "control_plane/58_decision_envelope_chain.json",
    feedback_chain_relative_path: str = "control_plane/65_outcome_feedback_chain.json",
) -> dict[str, Any]:
    root = proof_root.resolve()
    decision = read_json(root / decision_chain_relative_path)
    feedback = read_json(root / feedback_chain_relative_path)

    decision_rows = decision.get("entries", []) if isinstance(decision, dict) else []
    feedback_rows = feedback.get("entries", []) if isinstance(feedback, dict) else []
    valid_decision_hashes = {
        str(row.get("entry_hash", "")).strip()
        for row in decision_rows
        if isinstance(row, dict) and str(row.get("entry_hash", "")).strip()
    }

    missing: list[dict[str, Any]] = []
    for row in feedback_rows if isinstance(feedback_rows, list) else []:
        if not isinstance(row, dict):
            continue
        linked = str(row.get("linked_envelope_hash", "")).strip()
        if not linked or linked not in valid_decision_hashes:
            missing.append(
                {
                    "feedback_sequence_index": int(row.get("feedback_sequence_index", 0)),
                    "linked_envelope_hash": linked,
                    "reason": "missing_or_unknown_envelope_hash",
                }
            )

    return {
        "status": "PASS" if not missing else "FAIL",
        "decision_chain_path": decision_chain_relative_path,
        "feedback_chain_path": feedback_chain_relative_path,
        "decision_hash_count": len(valid_decision_hashes),
        "invalid_link_rows": missing,
    }
