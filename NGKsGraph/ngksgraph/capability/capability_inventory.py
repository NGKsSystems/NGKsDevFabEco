from __future__ import annotations

from ngksgraph.config import Config
from ngksgraph.graph import Target

from .capability_detector import (
    detect_compiler_capabilities,
    detect_debug_symbols_capability,
    detect_qt_capabilities,
    detect_windows_sdk_capability,
)
from .capability_types import CapabilityInventory


def build_capability_inventory(*, config: Config, target: Target) -> CapabilityInventory:
    records = []
    records.extend(detect_compiler_capabilities(target))
    records.append(detect_windows_sdk_capability())
    records.extend(detect_qt_capabilities(config, target))
    records.append(detect_debug_symbols_capability())
    return CapabilityInventory(records=records)
