from __future__ import annotations

import importlib.util
import shutil
import sys


class ComponentResolutionError(RuntimeError):
    def __init__(self, component_name: str, module_name: str) -> None:
        self.component_name = component_name
        self.module_name = module_name
        self.module_main = f"{module_name}.__main__"
        super().__init__(
            "\n".join(
                [
                    "Component resolution failed.",
                    f"component_name={component_name}",
                    f"checked_console_script={component_name}",
                    f"checked_module={module_name}",
                    f"checked_module_main={self.module_main}",
                    "suggestion=pip install -e <repo> OR pip install -e '.[dev]'",
                ]
            )
        )


def resolve_component_cmd(component_name: str, module_name: str) -> dict[str, object]:
    def _safe_find_spec(name: str):
        try:
            return importlib.util.find_spec(name)
        except (ModuleNotFoundError, ValueError):
            return None

    console_path = shutil.which(component_name)
    module_spec = _safe_find_spec(module_name)
    module_main_name = f"{module_name}.__main__"
    module_main_spec = _safe_find_spec(module_main_name)

    if console_path:
        why = "console script found on PATH"
        if module_spec and module_main_spec:
            why = "console script found on PATH; module is also importable"
        return {
            "mode": "console",
            "argv": [component_name],
            "why": why,
        }

    if module_spec and module_main_spec:
        return {
            "mode": "module",
            "argv": [sys.executable, "-m", module_name],
            "why": "console script not found; module and module.__main__ importable",
        }

    raise ComponentResolutionError(component_name=component_name, module_name=module_name)
