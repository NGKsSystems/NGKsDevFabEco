from __future__ import annotations

from . import node_runtime, python_runtime, win_msvc, win_windows_sdk


def get_provider_registry() -> dict[str, object]:
    return {
        python_runtime.PROVIDER_KEY: python_runtime,
        node_runtime.PROVIDER_KEY: node_runtime,
        win_msvc.PROVIDER_KEY: win_msvc,
        win_windows_sdk.PROVIDER_KEY: win_windows_sdk,
    }
