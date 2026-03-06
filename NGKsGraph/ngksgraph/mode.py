from __future__ import annotations

import os
from enum import Enum


class Mode(str, Enum):
    STANDALONE = "standalone"
    ECOSYSTEM = "ecosystem"


def get_mode(args: object) -> Mode:
    raw = getattr(args, "mode", None)
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get("NGKS_MODE", "standalone")
    text = str(raw).strip().lower()
    if text == Mode.ECOSYSTEM.value:
        return Mode.ECOSYSTEM
    return Mode.STANDALONE


def is_ecosystem(mode: Mode) -> bool:
    return mode == Mode.ECOSYSTEM