from __future__ import annotations

from pathlib import Path
from typing import Any

from .replay_hash_utils import HASH_EXCLUSION_FIELDS, load_chain_rows, missing_refs_for_row, semantic_sha256


def validate_decision_chain_from_proof(
    *,
    proof_root: Path,
    chain_relative_path: str = "control_plane/58_decision_envelope_chain.json",
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
            "error": "missing_decision_chain",
            "rows": [],
            "invalid_chain_detected": True,
            "invalid_chain_reason_codes": ["INVALID_CHAIN"],
            "replay_reason_codes": ["missing_input_decision_chain"],
        }

    rows, order_stable = load_chain_rows(chain_path, index_field="chain_index")
    expected_parent = "GENESIS"
    invalid = not order_stable
    invalid_reasons: set[str] = {"INVALID_CHAIN"} if invalid else set()
    replay_reason_codes: set[str] = set()
    per_row: list[dict[str, Any]] = []

    for row in rows:
        computed = semantic_sha256(row, hash_field="entry_hash")
        stored_hash = str(row.get("entry_hash", ""))
        parent_hash = str(row.get("parent_hash", ""))
        hash_ok = computed == stored_hash
        parent_ok = parent_hash == expected_parent
        if not hash_ok or not parent_ok:
            invalid = True
            invalid_reasons.add("INVALID_CHAIN")

        row_reasons: set[str] = set()
        missing_inputs = row.get("missing_inputs", [])
        if isinstance(missing_inputs, list) and missing_inputs:
            row_reasons.add("missing_input_declared")

        refs = row.get("evidence_refs", [])
        if isinstance(refs, list):
            for reason in missing_refs_for_row(root, [str(r) for r in refs]):
                row_reasons.add(reason)

        replay_reason_codes.update(row_reasons)
        per_row.append(
            {
                "chain_index": int(row.get("chain_index", 0)),
                "stage_name": str(row.get("stage_name", "")),
                "hash_ok": hash_ok,
                "previous_hash_ok": parent_ok,
                "replay_reason_codes": sorted(row_reasons),
            }
        )
        expected_parent = stored_hash

    return {
        "status": "PASS" if not invalid else "FAIL",
        "strict_mode": strict_mode,
        "strict_replay_input_boundary": "proof_artifacts_only",
        "chain_path": chain_relative_path,
        "rows": per_row,
        "chain_order_stable": order_stable,
        "invalid_chain_detected": invalid,
        "invalid_chain_reason_codes": sorted(invalid_reasons),
        "replay_reason_codes": sorted(replay_reason_codes),
        "hash_exclusion_fields": sorted(HASH_EXCLUSION_FIELDS),
    }
