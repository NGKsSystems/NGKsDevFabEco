from __future__ import annotations

from .capability_types import CapabilityInventory


def inventory_payload(inventory: CapabilityInventory) -> dict:
    return {
        "records": [record.to_dict() for record in inventory.records],
        "total_records": len(inventory.records),
        "available_count": sum(1 for record in inventory.records if record.status == "available"),
        "missing_count": sum(1 for record in inventory.records if record.status == "missing"),
    }
