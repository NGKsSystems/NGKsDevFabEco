from __future__ import annotations


def capability_map(framework_names: set[str]) -> dict[str, object]:
    if "Qt6" in framework_names:
        return {
            "native_supported": True,
            "unsupported_features": [],
        }
    return {
        "native_supported": True,
        "unsupported_features": [],
    }
