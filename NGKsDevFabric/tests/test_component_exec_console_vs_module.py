from __future__ import annotations

from ngksdevfabric.ngk_fabric import component_exec


def test_component_exec_prefers_console_when_available(monkeypatch):
    monkeypatch.setattr(component_exec.shutil, "which", lambda name: "C:/fake/ngksenvcapsule.exe" if name == "ngksenvcapsule" else None)
    monkeypatch.setattr(component_exec.importlib.util, "find_spec", lambda name: object())

    resolved = component_exec.resolve_component_cmd(component_name="ngksenvcapsule", module_name="ngksenvcapsule")

    assert resolved["mode"] == "console"
    assert resolved["argv"] == ["ngksenvcapsule"]
    assert "PATH" in str(resolved["why"])
