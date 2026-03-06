from __future__ import annotations

import json
from pathlib import Path


def dumps_stable(obj: object) -> str:
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_stable_json(path: str | Path, obj: object) -> int:
    payload = dumps_stable(obj).encode("utf-8")
    Path(path).write_bytes(payload)
    return len(payload)
