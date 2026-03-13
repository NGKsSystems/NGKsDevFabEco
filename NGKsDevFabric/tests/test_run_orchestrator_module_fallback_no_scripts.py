from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from ngksdevfabric.ngk_fabric import component_exec
from ngksdevfabric.ngk_fabric import main as fabric_main


@dataclass
class _Proc:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _latest_run_dir(project: Path) -> Path:
    roots = sorted((project / "_proof").glob("devfabric_run_run_*"))
    assert roots, "expected at least one run proof folder"
    return roots[-1]


def _write_package_json(project: Path) -> None:
    (project / "package.json").write_text(
        '{"name":"app","scripts":{"smoke":"node app.js","all":"node app.js"}}\n',
        encoding="utf-8",
    )


def test_run_uses_module_fallback_when_console_scripts_missing(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    monkeypatch.setattr(component_exec.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        fabric_main.shutil,
        "which",
        lambda name: f"C:/fake/{name}.cmd" if name in {"node", "npm", "pnpm"} else None,
    )

    def _fake_find_spec(name: str):
        allowed = {
            "ngksenvcapsule",
            "ngksenvcapsule.__main__",
            "ngksgraph",
            "ngksgraph.__main__",
            "ngksbuildcore",
            "ngksbuildcore.__main__",
            "ngkslibrary",
            "ngkslibrary.__main__",
        }
        return object() if name in allowed else None

    monkeypatch.setattr(component_exec.importlib.util, "find_spec", _fake_find_spec)

    calls: list[list[str]] = []

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text
        cmd = [str(part) for part in command]
        calls.append(cmd)

        if cmd[:3] == [sys.executable, "-m", "ngksenvcapsule"] and cmd[3] == "lock":
            (tmp_path / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash_module\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if cmd[:3] == [sys.executable, "-m", "ngksenvcapsule"] and cmd[3] == "resolve":
            return _Proc(returncode=0, stdout="resolve ok\n")

        if cmd[:3] == [sys.executable, "-m", "ngksenvcapsule"] and cmd[3:5] == ["verify", "--lock"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if cmd[:3] == [sys.executable, "-m", "ngksgraph"] and cmd[3] == "plan":
            (tmp_path / "build_plan.json").write_text('{"plan":true}\n', encoding="utf-8")
            (tmp_path / "build_plan.hash.txt").write_text("planhash_module\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="plan ok\n")

        if cmd[:3] == [sys.executable, "-m", "ngksbuildcore"] and cmd[3] == "run":
            return _Proc(returncode=0, stdout="build ok\n")

        if cmd[:3] == [sys.executable, "-m", "ngkslibrary"] and cmd[3] == "assemble":
            return _Proc(returncode=0, stdout="library ok\n")

        return _Proc(returncode=1, stderr="unexpected command")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 0
    assert [cmd[:3] for cmd in calls[:6]] == [
        [sys.executable, "-m", "ngksenvcapsule"],
        [sys.executable, "-m", "ngksenvcapsule"],
        [sys.executable, "-m", "ngksenvcapsule"],
        [sys.executable, "-m", "ngksgraph"],
        [sys.executable, "-m", "ngksbuildcore"],
        [sys.executable, "-m", "ngkslibrary"],
    ]

    run_dir = _latest_run_dir(tmp_path)
    for stage in ["10_envcapsule", "20_graph", "30_buildcore", "40_library"]:
        resolve_file = run_dir / stage / "00_resolve.txt"
        assert resolve_file.exists()
        text = resolve_file.read_text(encoding="utf-8")
        assert "mode=module" in text
        assert f"argv={sys.executable} -m" in text

    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "env_capsule_hash=envhash_module" in summary_text
    assert "env_capsule_hash_reason=ok" in summary_text
    assert "build_plan_hash=" in summary_text
    assert "build_plan_hash=planhash_module" not in summary_text
    assert "build_plan_hash_reason=ok" in summary_text


def test_module_fallback_missing_outputs_maps_to_precondition_failed(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    monkeypatch.setattr(component_exec.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        fabric_main.shutil,
        "which",
        lambda name: f"C:/fake/{name}.cmd" if name in {"node", "npm", "pnpm"} else None,
    )

    def _fake_find_spec(name: str):
        allowed = {
            "ngksenvcapsule",
            "ngksenvcapsule.__main__",
            "ngksgraph",
            "ngksgraph.__main__",
            "ngksbuildcore",
            "ngksbuildcore.__main__",
            "ngkslibrary",
            "ngkslibrary.__main__",
        }
        return object() if name in allowed else None

    monkeypatch.setattr(component_exec.importlib.util, "find_spec", _fake_find_spec)

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text
        cmd = [str(part) for part in command]
        if cmd[:3] == [sys.executable, "-m", "ngksenvcapsule"] and cmd[3] == "lock":
            return _Proc(returncode=0, stdout="lock ok\n")
        if cmd[:3] == [sys.executable, "-m", "ngksenvcapsule"] and cmd[3:5] == ["verify", "--lock"]:
            return _Proc(returncode=0, stdout="verify ok\n")
        return _Proc(returncode=0, stdout="ok\n")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    err_text = (run_dir / "30_errors.txt").read_text(encoding="utf-8")
    assert "class=precondition_failed" in err_text
    assert "stage=10_envcapsule" in err_text
    assert "exit_code=0" in err_text
    assert "missing_outputs=env_capsule.lock.json,env_capsule.hash.txt" in err_text

    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "env_capsule_hash_reason=missing_outputs" in summary_text
    assert "build_plan_hash_reason=skipped_due_to_precondition" in summary_text
