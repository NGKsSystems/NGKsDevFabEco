from __future__ import annotations

from ..providers import node_runtime, python_runtime, win_msvc, win_windows_sdk


PROVIDER_ORDER = ["python", "node", "msvc", "windows_sdk"]
PROVIDER_GROUP = {
    "python": "runtimes",
    "node": "runtimes",
    "msvc": "toolchains",
    "windows_sdk": "toolchains",
}


def get_default_registry() -> dict[str, object]:
    registry = {
        python_runtime.PROVIDER_KEY: python_runtime,
        node_runtime.PROVIDER_KEY: node_runtime,
        win_msvc.PROVIDER_KEY: win_msvc,
        win_windows_sdk.PROVIDER_KEY: win_windows_sdk,
    }
    return registry
