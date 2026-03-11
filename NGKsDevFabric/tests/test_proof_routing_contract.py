from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ngksdevfabric.ngk_fabric import main as fabric_main


@dataclass
class _Proc:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _latest_run_dir(project: Path) -> Path:
    roots = sorted((project / "_proof").glob("devfabric_run_run_*"))
    assert roots
    return roots[-1]


def test_proof_routing_avoids_root_level_legacy_spill(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"x","scripts":{"build":"echo ok"}}\n', encoding="utf-8")

    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test",
        },
    )

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text
        if command[:2] == ["ngksenvcapsule", "resolve"]:
            (tmp_path / "env_capsule.resolved.json").write_text('{"resolved":true}\n', encoding="utf-8")
            return _Proc(returncode=0, stdout="ok\n")
        if command[:2] == ["ngksenvcapsule", "lock"]:
            (tmp_path / "env_capsule.lock.json").write_text('{"ok":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="ok\n")
        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="ok\n")
        if command[:2] == ["ngksgraph", "plan"]:
            (tmp_path / "build_plan.json").write_text('{"ok":true}\n', encoding="utf-8")
            (tmp_path / "build_plan.hash.txt").write_text("planhash\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="ok\n")
        if command[:2] == ["ngksbuildcore", "run"]:
            return _Proc(returncode=0, stdout="build ok\n")
        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="report ok\n")
        return _Proc(returncode=1, stderr="unexpected")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])
    assert code == 0

    run_dir = _latest_run_dir(tmp_path)
    assert (run_dir / "20_graph").exists()
    assert (run_dir / "30_buildcore").exists()
    assert (run_dir / "40_library").exists()

    proof_root = tmp_path / "_proof"
    assert not list(proof_root.glob("build_*"))
    assert not list(proof_root.glob("doctor_*"))
    assert not list(proof_root.glob("lock_*"))
