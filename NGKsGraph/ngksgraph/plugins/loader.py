from __future__ import annotations

import importlib
from typing import Any

from ngksgraph.config import AIConfig
from ngksgraph.plugins.stub_ai import Plugin as StubPlugin


def _resolve_plugin_obj(module: Any, class_name: str | None) -> Any:
    if class_name:
        cls = getattr(module, class_name)
        return cls()
    if hasattr(module, "Plugin"):
        return getattr(module, "Plugin")()
    if hasattr(module, "suggest"):
        return module
    raise AttributeError("Plugin module must define Plugin class or suggest(context).")


def load_plugin(ai_cfg: AIConfig):
    if not ai_cfg.enabled or not ai_cfg.plugin.strip():
        return StubPlugin()

    plugin_path = ai_cfg.plugin.strip()
    module_name, class_name = (plugin_path.split(":", 1) + [None])[:2] if ":" in plugin_path else (plugin_path, None)

    try:
        module = importlib.import_module(module_name)
        plugin = _resolve_plugin_obj(module, class_name)
        if not hasattr(plugin, "suggest"):
            return StubPlugin()
        return plugin
    except Exception:
        return StubPlugin()
