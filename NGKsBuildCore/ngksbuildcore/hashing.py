from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_path(path: str | Path, base_dir: Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    else:
        p = p.resolve()
    return p


def file_fingerprint(path: Path) -> str:
    stat = path.stat()
    raw = f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def input_signature(paths: list[Path]) -> str:
    joined = "|".join(file_fingerprint(p) for p in sorted(paths))
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()
