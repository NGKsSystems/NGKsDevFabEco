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
    assert roots, "expected at least one run proof folder"
    return roots[-1]


def _write_package_json(project: Path) -> None:
    (project / "package.json").write_text(
        '{"name":"app","scripts":{"smoke":"node app.js","all":"node app.js"}}\n',
        encoding="utf-8",
    )


def _fake_run_factory(project: Path, calls: list[list[str]]):
    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text
        calls.append(list(command))

        if command[:2] == ["ngksenvcapsule", "lock"]:
            (project / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (project / "env_capsule.hash.txt").write_text("envhash123\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if command[:2] == ["ngksgraph", "plan"]:
            (project / "build_plan.json").write_text('{"plan":true}\n', encoding="utf-8")
            (project / "build_plan.hash.txt").write_text("planhash456\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="plan ok\n")

        if command[:2] == ["ngksbuildcore", "run"]:
            return _Proc(returncode=0, stdout="build ok\n")

        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")

        return _Proc(returncode=1, stderr="unexpected command")

    return _fake_run


def test_run_directory_creation(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path)])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    assert run_dir.exists()
    assert (run_dir / "00_run_header.txt").exists()
    assert (run_dir / "10_envcapsule").exists()
    assert (run_dir / "20_graph").exists()
    assert (run_dir / "30_buildcore").exists()
    assert (run_dir / "40_library").exists()


def test_component_invocation_order(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 0
    expected_prefixes = [
        ["ngksenvcapsule", "lock"],
        ["ngksenvcapsule", "verify"],
        ["ngksgraph", "plan"],
        ["ngksbuildcore", "run"],
        ["ngkslibrary", "assemble"],
    ]
    assert [cmd[:2] for cmd in calls] == expected_prefixes
    assert "--pf" in calls[0]
    assert "--pf" in calls[1]
    assert "--pf" in calls[2]
    assert "--pf" in calls[3]
    assert "--pf" in calls[4]


def test_summary_generation(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path), "--profile", "dev", "--target", "all"])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    summary = run_dir / "99_summary.txt"
    assert summary.exists()
    text = summary.read_text(encoding="utf-8")
    assert "components_executed=envcapsule,graph,buildcore,library" in text
    assert "env_capsule_hash=envhash123" in text
    assert "build_plan_hash=planhash456" in text
    assert "build_success=true" in text
