from __future__ import annotations


def capability_map(framework_names: set[str]) -> dict[str, object]:
    unsupported: list[str] = []
    if "Flutter" in framework_names:
        unsupported.append("flutter_toolchain_not_native_in_buildcore")
    if "Qt6" in framework_names and "Flutter" in framework_names:
        unsupported.append("mixed_qt_flutter_workspace_requires_split")

    return {
        "native_supported": len(unsupported) == 0,
        "unsupported_features": unsupported,
    }
