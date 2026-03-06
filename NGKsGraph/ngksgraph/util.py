from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def rel_path(path: Path, base: Path) -> str:
    return normalize_path(path.resolve().relative_to(base.resolve()))


def stable_unique_sorted(values: Iterable[str]) -> list[str]:
    normalized = [normalize_path(v).strip() for v in values if str(v).strip()]
    return sorted(set(normalized))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
