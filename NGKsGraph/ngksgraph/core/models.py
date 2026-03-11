from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanRunResult:
    out_dir: Path
    status: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class Subproject:
    subproject_id: str
    root_path: str
