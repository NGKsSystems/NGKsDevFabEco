from __future__ import annotations

from ngksdevfabric.ngk_fabric.main import main as fabric_main


def main(argv: list[str] | None = None) -> int:
    return int(fabric_main(argv))
