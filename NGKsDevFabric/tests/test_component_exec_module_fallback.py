from __future__ import annotations

import sys

from ngksdevfabric.ngk_fabric import component_exec


def test_component_exec_module_fallback_uses_sys_executable(monkeypatch):
    monkeypatch.setattr(component_exec.shutil, "which", lambda name: None)

    def _fake_find_spec(name: str):
        if name in {"ngksdevfabric", "ngksdevfabric.__main__"}:
            return object()
        return None

    monkeypatch.setattr(component_exec.importlib.util, "find_spec", _fake_find_spec)

    resolved = component_exec.resolve_component_cmd(component_name="ngksdevfabric", module_name="ngksdevfabric")

    assert resolved["mode"] == "module"
    assert resolved["argv"] == [sys.executable, "-m", "ngksdevfabric"]
    assert "module" in str(resolved["why"])
