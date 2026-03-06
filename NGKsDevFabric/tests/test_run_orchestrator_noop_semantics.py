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


def _assert_stage_sentinels(run_dir: Path) -> None:
    stages = {
        "10_envcapsule": "envcapsule",
        "20_graph": "graph",
        "30_buildcore": "buildcore",
        "40_library": "library",
    }
    for folder, stage_name in stages.items():
        sentinel = run_dir / folder / "00_stage.txt"
        assert sentinel.exists()
        text = sentinel.read_text(encoding="utf-8")
        assert f"stage={stage_name}" in text
        assert "status=" in text
        assert "reason=" in text
        assert "timestamp=" in text


def test_blank_repo_is_noop_exit_zero(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )

    def _fake_subprocess(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text
        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")
        raise AssertionError(f"unexpected subprocess invocation for noop: {command}")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_subprocess)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--profile", "debug", "--target", "smoke", "--mode", "ecosystem"])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    _assert_stage_sentinels(run_dir)
    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_detected=false" in summary_text
    assert "build_system=none" in summary_text
    assert "build_detect_reason=no_build_inputs" in summary_text
    assert "build_action=skipped" in summary_text
    assert "build_reason=no_build_inputs" in summary_text
    assert "build_success=true" in summary_text
    assert "exit_code=0" in summary_text

    for folder in ["20_graph", "30_buildcore"]:
        sentinel_text = (run_dir / folder / "00_stage.txt").read_text(encoding="utf-8")
        assert "status=skipped" in sentinel_text
        assert "reason=no_build_inputs" in sentinel_text

    lib_sentinel = (run_dir / "40_library" / "00_stage.txt").read_text(encoding="utf-8")
    assert "status=ran" in lib_sentinel

    ngks_dir = tmp_path / ".ngks"
    assert (ngks_dir / "project.json").exists()
    assert (ngks_dir / "profile.default.json").exists()
    assert (ngks_dir / "README.txt").exists()


def test_node_detected_missing_target_is_precondition_failed(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"app","scripts":{"build":"node app.js"}}\n', encoding="utf-8")

    def _unexpected_subprocess(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not be called when target precheck fails: {args}, {kwargs}")

    monkeypatch.setattr(fabric_main.subprocess, "run", _unexpected_subprocess)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--profile", "debug", "--target", "smoke", "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    err_text = (run_dir / "30_errors.txt").read_text(encoding="utf-8")
    assert "class=precondition_failed" in err_text
    assert "stage=30_buildcore" in err_text

    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_detected=true" in summary_text
    assert "build_system=node" in summary_text
    assert "build_detect_reason=package.json" in summary_text
    assert "build_action=skipped" in summary_text
    assert "build_reason=missing_required_target" in summary_text
    assert "failure_class=precondition_failed" in summary_text
    assert "exit_code=2" in summary_text


def test_detect_precedence_sln_over_package_json(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"app","scripts":{"smoke":"node app.js"}}\n', encoding="utf-8")
    (tmp_path / "dummy.sln").write_text("Microsoft Visual Studio Solution File\n", encoding="utf-8")

    def _unexpected_subprocess(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not execute on missing envcapsule resolver: {args}, {kwargs}")

    def _raise_missing(component_name: str, module_name: str):
        del component_name, module_name
        raise fabric_main.ComponentResolutionError("ngksenvcapsule", "ngksenvcapsule")

    monkeypatch.setattr(fabric_main, "resolve_component_cmd", _raise_missing)
    monkeypatch.setattr(fabric_main.subprocess, "run", _unexpected_subprocess)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    _assert_stage_sentinels(run_dir)
    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_detected=true" in summary_text
    assert "build_system=dotnet" in summary_text
    assert "build_detect_reason=dummy.sln" in summary_text


def test_detect_dotnet_with_csproj(monkeypatch, tmp_path: Path):
    (tmp_path / "dummy.csproj").write_text("<Project></Project>\n", encoding="utf-8")

    def _unexpected_subprocess(*args, **kwargs):
        raise AssertionError(f"subprocess.run should not execute on missing envcapsule resolver: {args}, {kwargs}")

    def _raise_missing(component_name: str, module_name: str):
        del component_name, module_name
        raise fabric_main.ComponentResolutionError("ngksenvcapsule", "ngksenvcapsule")

    monkeypatch.setattr(fabric_main, "resolve_component_cmd", _raise_missing)
    monkeypatch.setattr(fabric_main.subprocess, "run", _unexpected_subprocess)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    _assert_stage_sentinels(run_dir)
    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_detected=true" in summary_text
    assert "build_system=dotnet" in summary_text
    assert "build_detect_reason=dummy.csproj" in summary_text


def test_build_attempt_failure_maps_to_exit_one(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"app","scripts":{"smoke":"node app.js"}}\n', encoding="utf-8")

    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True):
        del cwd, check, capture_output, text

        if command[:2] == ["ngksenvcapsule", "lock"]:
            (tmp_path / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if command[:2] == ["ngksgraph", "plan"]:
            (tmp_path / "build_plan.json").write_text('{"plan":true}\n', encoding="utf-8")
            (tmp_path / "build_plan.hash.txt").write_text("planhash\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="plan ok\n")

        if command[:2] == ["ngksbuildcore", "run"]:
            return _Proc(returncode=9, stderr="build failed\n")

        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")

        return _Proc(returncode=1, stderr="unexpected command")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--profile", "debug", "--target", "smoke", "--mode", "ecosystem"])

    assert code == 1
    run_dir = _latest_run_dir(tmp_path)
    _assert_stage_sentinels(run_dir)
    err_text = (run_dir / "30_errors.txt").read_text(encoding="utf-8")
    assert "class=build_failed" in err_text
    assert "stage=30_buildcore" in err_text

    summary_text = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_detected=true" in summary_text
    assert "build_action=attempted" in summary_text
    assert "build_reason=build_failed" in summary_text
    assert "failure_class=build_failed" in summary_text
    assert "failed_stage=30_buildcore" in summary_text
    assert "exit_code=1" in summary_text
