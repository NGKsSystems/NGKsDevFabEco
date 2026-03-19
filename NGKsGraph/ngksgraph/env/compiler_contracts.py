from __future__ import annotations

import os


def compiler_family() -> str:
    return "msvc" if os.name == "nt" else "unknown"
