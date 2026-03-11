from __future__ import annotations

from pathlib import Path
import json

from ngksgraph.log import write_json as _write_json
from ngksgraph.log import write_text as _write_text


def write_json(path: Path, payload: dict) -> None:
    _write_json(path, payload)


def write_text(path: Path, content: str) -> None:
    _write_text(path, content)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
