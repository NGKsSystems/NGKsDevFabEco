from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from ..core.types import Candidate, Constraint, HostContext, Selection


PROVIDER_KEY = "msvc"


def detect(host: HostContext) -> list[Candidate]:
    if host.os != "windows":
        return []
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        return []
    try:
        proc = subprocess.run(
            [
                str(vswhere),
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return []
        entries = json.loads(proc.stdout)
    except Exception:
        return []

    candidates: list[Candidate] = []
    for entry in entries:
        candidates.append(
            Candidate(
                id=entry.get("productId") or entry.get("instanceId") or "VS",
                version=str(entry.get("catalog", {}).get("productLineVersion", "")),
                meta={"path": entry.get("installationPath", "")},
            )
        )
    return sorted(candidates, key=lambda x: (x.version, x.id), reverse=True)


def select(constraint: Constraint, candidates: list[Candidate]) -> Selection:
    if constraint.strategy == "off":
        return Selection(provider=PROVIDER_KEY, status="not_selected")
    chosen = candidates[0] if candidates else None
    if constraint.strategy == "require" and chosen is None:
        return Selection(provider=PROVIDER_KEY, status="missing_required", reason="Required toolchain missing: MSVC")
    if chosen is None:
        return Selection(provider=PROVIDER_KEY, status="not_selected")
    return Selection(provider=PROVIDER_KEY, status="selected", selected=chosen)


def fingerprint(selection: Selection) -> dict | None:
    if not selection.selected:
        return None
    return {"install_id": selection.selected.id, "toolset": selection.selected.version}


def verify(lock_facts: dict, host: HostContext) -> tuple[bool, str | None]:
    for candidate in detect(host):
        facts = {"install_id": candidate.id, "toolset": candidate.version}
        if facts == lock_facts:
            return True, None
    return False, "msvc mismatch"
