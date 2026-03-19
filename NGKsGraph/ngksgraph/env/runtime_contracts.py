from __future__ import annotations

import os
from pathlib import Path


def has_qt_runtime() -> bool:
    return bool(os.environ.get("QTDIR") or os.environ.get("QT_ROOT") or Path("C:/Qt").exists())
