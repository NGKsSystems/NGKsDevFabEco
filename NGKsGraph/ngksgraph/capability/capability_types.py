from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityRecord:
    capability_name: str
    provider: str
    version: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_name": str(self.capability_name),
            "provider": str(self.provider),
            "version": str(self.version),
            "status": str(self.status),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityInventory:
    records: list[CapabilityRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [record.to_dict() for record in self.records],
        }

    def by_name(self, capability_name: str) -> CapabilityRecord | None:
        for record in self.records:
            if record.capability_name == capability_name:
                return record
        return None

    def available_names(self) -> set[str]:
        return {record.capability_name for record in self.records if record.status == "available"}
