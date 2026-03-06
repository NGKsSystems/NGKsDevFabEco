from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_hash_file(path: str | Path, digest_hex: str) -> None:
    Path(path).write_text(f"{digest_hex}\n", encoding="utf-8", newline="\n")
