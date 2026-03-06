from __future__ import annotations

import os
import sys

from ..core.types import Candidate, Constraint, HostContext, Selection


PROVIDER_KEY = "python"


def detect(host: HostContext) -> list[Candidate]:
    mock = os.environ.get("NGKSENV_MOCK_PYTHON")
    if mock:
        return [Candidate(id="python", version=mock, meta={"exe": "mock-python.exe"})]
    return [Candidate(id="python", version=sys.version.split()[0], meta={"exe": sys.executable})]


def select(constraint: Constraint, candidates: list[Candidate]) -> Selection:
    if constraint.strategy == "off":
        return Selection(provider=PROVIDER_KEY, status="not_selected")

    chosen = None
    if constraint.version:
        chosen = next((c for c in candidates if c.version == constraint.version), None)
    elif candidates:
        chosen = candidates[0]

    if constraint.strategy == "require" and chosen is None:
        required = constraint.version or "(no exact required configured)"
        return Selection(provider=PROVIDER_KEY, status="missing_required", reason=f"Required runtime missing: Python {required}")
    if chosen is None:
        return Selection(provider=PROVIDER_KEY, status="not_selected")
    return Selection(provider=PROVIDER_KEY, status="selected", selected=chosen)


def fingerprint(selection: Selection) -> dict | None:
    if not selection.selected:
        return None
    return {"version": selection.selected.version, "exe": selection.selected.meta.get("exe", "")}


def verify(lock_facts: dict, host: HostContext) -> tuple[bool, str | None]:
    current_candidates = detect(host)
    expected = lock_facts.get("version", "")
    for candidate in current_candidates:
        if candidate.version == expected:
            return True, None
    return False, f"python version mismatch: expected {expected}"


def provision(constraint: Constraint, host: HostContext, proof_dir: str) -> Selection:
    return Selection(
        provider=PROVIDER_KEY,
        status="missing_required",
        reason=(
            f"Auto-install requested for Python {constraint.version or ''}, but deterministic pinned installer flow "
            "is not implemented in Phase 1."
        ),
    )
