from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import shutil
import traceback


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ProofSession:
    command: str
    argv: list[str]
    cwd: Path
    root: Path = Path("_proof")
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    outputs: list[str] = field(default_factory=list)
    path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.path = self.root / f"{self.command}_{self.timestamp}"
        self.path.mkdir(parents=True, exist_ok=True)
        cmdline = [
            f"timestamp={utc_now_iso()}",
            f"cwd={self.cwd}",
            "argv=" + " ".join(self.argv),
        ]
        (self.path / "00_cmdline.txt").write_text("\n".join(cmdline) + "\n", encoding="utf-8", newline="\n")

    def write_inputs(self, lines: list[str]) -> None:
        (self.path / "10_inputs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def add_output(self, file_path: Path | str) -> None:
        self.outputs.append(str(file_path))

    def copy_artifact(self, file_path: Path | str) -> None:
        src = Path(file_path)
        if src.exists():
            dst = self.path / src.name
            shutil.copy2(src, dst)
            self.outputs.append(str(dst))

    def finalize(self) -> None:
        (self.path / "20_outputs.txt").write_text("\n".join(self.outputs) + ("\n" if self.outputs else ""), encoding="utf-8", newline="\n")

    def write_error(self, reason: str, exc: Exception | None = None) -> None:
        content = [f"reason={reason}"]
        if exc is not None:
            content.append(f"exception={exc}")
            content.append(traceback.format_exc())
        (self.path / "30_errors.txt").write_text("\n".join(content) + "\n", encoding="utf-8", newline="\n")
