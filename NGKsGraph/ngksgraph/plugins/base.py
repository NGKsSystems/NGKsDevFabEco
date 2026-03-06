from __future__ import annotations

from typing import Protocol


class AIRepairPlugin(Protocol):
    def suggest(self, context: dict) -> dict:
        ...
