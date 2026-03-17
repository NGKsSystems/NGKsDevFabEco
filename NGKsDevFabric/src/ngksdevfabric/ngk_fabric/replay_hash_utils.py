from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


HASH_EXCLUSION_FIELDS = {"timestamp_utc", "writer_runtime_ms", "local_path_variants"}


def strip_non_semantic(value: Any, *, excluded: set[str] | None = None) -> Any:
    excluded_keys = excluded or HASH_EXCLUSION_FIELDS
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in excluded_keys:
                continue
            out[key] = strip_non_semantic(value[key], excluded=excluded_keys)
        return out
    if isinstance(value, list):
        return [strip_non_semantic(item, excluded=excluded_keys) for item in value]
    return value


def semantic_sha256(entry: dict[str, Any], *, hash_field: str) -> str:
    payload = dict(entry)
    payload.pop(hash_field, None)
    canonical = strip_non_semantic(payload)
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_chain_rows(chain_path: Path, *, index_field: str) -> tuple[list[dict[str, Any]], bool]:
    payload = read_json(chain_path)
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    rows = [row for row in entries if isinstance(row, dict)] if isinstance(entries, list) else []
    original_indexes = [int(row.get(index_field, 0)) for row in rows]
    rows.sort(key=lambda row: int(row.get(index_field, 0)))
    sorted_indexes = [int(row.get(index_field, 0)) for row in rows]
    return rows, original_indexes == sorted_indexes


def resolve_proof_ref_strict(proof_root: Path, ref: str) -> tuple[Path | None, str | None]:
    normalized = str(ref or "").strip().replace("\\", "/")
    if not normalized:
        return None, "missing_input_ref_empty"
    if normalized.startswith("/"):
        return None, "missing_input_out_of_boundary"
    candidate = (proof_root / normalized).resolve()
    try:
        candidate.relative_to(proof_root.resolve())
    except Exception:
        return None, "missing_input_out_of_boundary"
    return candidate, None


def missing_refs_for_row(proof_root: Path, refs: list[str]) -> list[str]:
    reasons: list[str] = []
    for ref in refs:
        candidate, boundary_reason = resolve_proof_ref_strict(proof_root, str(ref))
        if boundary_reason:
            reasons.append(boundary_reason)
            continue
        if candidate is None or not candidate.exists():
            reasons.append("missing_input_evidence_ref")
    return sorted(set(reasons))


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
