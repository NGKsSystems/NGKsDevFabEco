from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent), newline="") as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    last_error: Exception | None = None
    for _ in range(20):
        try:
            tmp_path.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        raise last_error


def write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))


def write_text(path: Path, text: str) -> None:
    _atomic_write_text(path, text)


def read_tail_lines(path: Path, line_count: int) -> str:
    if line_count <= 0 or not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])
