from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProofContext:
    run_id: str
    run_pf: Path
    stage_pf: Path
    backup_root: Path | None = None
    mirror_stage_pf: Path | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "run_id": self.run_id,
            "run_pf": str(self.run_pf),
            "stage_pf": str(self.stage_pf),
            "backup_root": str(self.backup_root) if self.backup_root else None,
            "mirror_stage_pf": str(self.mirror_stage_pf) if self.mirror_stage_pf else None,
        }

    @staticmethod
    def from_paths(run_id: str, run_pf: Path, stage_pf: Path, backup_root: Path | None = None) -> "ProofContext":
        run_pf_abs = run_pf.resolve()
        stage_pf_abs = stage_pf.resolve()
        mirror_stage_pf = None
        if backup_root is not None:
            mirror_stage_pf = backup_root.resolve() / run_pf_abs.name / stage_pf_abs.name
        return ProofContext(
            run_id=run_id,
            run_pf=run_pf_abs,
            stage_pf=stage_pf_abs,
            backup_root=backup_root.resolve() if backup_root else None,
            mirror_stage_pf=mirror_stage_pf,
        )
