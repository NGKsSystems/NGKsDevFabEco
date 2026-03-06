from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from ngk_fabric.main import main as fabric_main

    return int(fabric_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
