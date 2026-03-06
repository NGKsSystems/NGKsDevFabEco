from __future__ import annotations

import os
import subprocess

from ..core.types import Candidate, Constraint, HostContext, Selection


PROVIDER_KEY = "node"


def _safe_run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()
    except OSError:
        return ""


def detect(host: HostContext) -> list[Candidate]:
    mock = os.environ.get("NGKSENV_MOCK_NODE")
    if mock:
        return [Candidate(id="node", version=mock.lstrip("v"), meta={"exe": "mock-node.exe"})]
    v = _safe_run(["node", "--version"])
    if not v:
        return []
    where = _safe_run(["where", "node"]).splitlines()
    exe = where[0].strip() if where else "node"
    return [Candidate(id="node", version=v.lstrip("v"), meta={"exe": exe})]


def select(constraint: Constraint, candidates: list[Candidate]) -> Selection:
    if constraint.strategy == "off":
        return Selection(provider=PROVIDER_KEY, status="not_selected")
    chosen = None
    if constraint.version:
        chosen = next((c for c in candidates if c.version == constraint.version), None)
    elif candidates:
        chosen = candidates[0]
    if constraint.strategy == "require" and chosen is None:
        required = constraint.version or "(required node runtime)"
        return Selection(provider=PROVIDER_KEY, status="missing_required", reason=f"Required runtime missing: Node {required}")
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
    return False, f"node version mismatch: expected {expected}"
