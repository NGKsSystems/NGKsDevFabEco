from __future__ import annotations

import os
from pathlib import Path

from ..core.types import Candidate, Constraint, HostContext, Selection


PROVIDER_KEY = "windows_sdk"


def _ver_tuple(v: str) -> tuple[int, ...]:
    out = []
    for part in v.split("."):
        if part.isdigit():
            out.append(int(part))
        else:
            out.append(0)
    return tuple(out)


def detect(host: HostContext) -> list[Candidate]:
    if host.os != "windows":
        return []
    roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "Include",
        Path(r"C:\Program Files (x86)\Windows Kits\10\Include"),
    ]
    versions = set()
    for root in roots:
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and child.name and child.name[0].isdigit():
                    versions.add(child.name)
    candidates = [Candidate(id="windows_sdk", version=v, meta={}) for v in sorted(versions, key=_ver_tuple, reverse=True)]
    return candidates


def select(constraint: Constraint, candidates: list[Candidate]) -> Selection:
    if constraint.strategy == "off":
        return Selection(provider=PROVIDER_KEY, status="not_selected")

    chosen = None
    if constraint.min_version:
        min_t = _ver_tuple(constraint.min_version)
        chosen = next((c for c in candidates if _ver_tuple(c.version or "0") >= min_t), None)
    elif candidates:
        chosen = candidates[0]

    if constraint.strategy == "require" and chosen is None:
        need = constraint.min_version or "(required windows sdk)"
        return Selection(provider=PROVIDER_KEY, status="missing_required", reason=f"Required toolchain missing: Windows SDK >= {need}")
    if chosen is None:
        return Selection(provider=PROVIDER_KEY, status="not_selected")
    return Selection(provider=PROVIDER_KEY, status="selected", selected=chosen)


def fingerprint(selection: Selection) -> dict | None:
    if not selection.selected:
        return None
    return {"version": selection.selected.version}


def verify(lock_facts: dict, host: HostContext) -> tuple[bool, str | None]:
    current_candidates = detect(host)
    expected = lock_facts.get("version", "")
    for candidate in current_candidates:
        if candidate.version == expected:
            return True, None
    return False, f"windows_sdk mismatch: expected {expected}"
