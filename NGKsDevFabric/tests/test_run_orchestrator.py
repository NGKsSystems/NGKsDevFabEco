from __future__ import annotations

from dataclasses import dataclass
import json
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
    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True, env=None):
        del cwd, check, capture_output, text, env
        calls.append(list(command))

        if command[:2] == ["ngksenvcapsule", "resolve"]:
            (project / "env_capsule.resolved.json").write_text('{"resolved":true}\n', encoding="utf-8")
            return _Proc(returncode=0, stdout="resolve ok\n")

        if command[:2] == ["ngksenvcapsule", "lock"]:
            (project / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (project / "env_capsule.hash.txt").write_text("envhash123\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if command[:2] == ["ngksgraph", "plan"]:
            (project / "build_plan.json").write_text(
                '{"requirements":{"language":"node","package_manager":"npm"},"actions":[{"argv":["npm","run","build"]}]}\n',
                encoding="utf-8",
            )
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
        ["ngksenvcapsule", "resolve"],
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
    assert "--pf" in calls[5]


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
    assert "build_plan_hash=" in text
    assert "build_plan_hash=planhash456" not in text
    assert "build_success=true" in text
    graph_cmd = calls[3]
    assert "--profile" in graph_cmd
    assert "dev" in graph_cmd
    assert "--target" in graph_cmd
    assert "all" in graph_cmd

    buildcore_cmd = calls[4]
    assert "--profile" not in buildcore_cmd
    assert "--target" not in buildcore_cmd


def test_node_toolchain_decision_prefers_pnpm_without_lockfile(monkeypatch, tmp_path: Path):
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

    monkeypatch.setattr(
        fabric_main.shutil,
        "which",
        lambda name: f"C:/fake/{name}.cmd" if name in {"node", "pnpm", "npm"} else None,
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem", "--target", "all"])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    decision = json.loads((run_dir / "node_toolchain_decision.json").read_text(encoding="utf-8"))
    assert decision["selected_manager"] == "pnpm"
    assert decision["reason"] == "policy_default_no_lockfile"
    assert decision["scan_scope"] == "repo_root_only"

    plan = json.loads((tmp_path / "build_plan.json").read_text(encoding="utf-8"))
    assert plan["requirements"]["package_manager"] == "pnpm"
    assert plan["actions"][0]["argv"][0] == "pnpm"


def test_node_toolchain_fallback_to_npm_when_pnpm_unavailable(monkeypatch, tmp_path: Path):
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

    monkeypatch.setattr(
        fabric_main.shutil,
        "which",
        lambda name: f"C:/fake/{name}.cmd" if name in {"node", "npm"} else None,
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem", "--target", "all"])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    decision = json.loads((run_dir / "node_toolchain_decision.json").read_text(encoding="utf-8"))
    assert decision["selected_manager"] == "npm"
    assert decision["reason"] == "fallback_tool_unavailable"


def test_conflict_outcome_promoted_to_summary(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"app","scripts":{"all":"node app.js"}}\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

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
    monkeypatch.setattr(
        fabric_main.shutil,
        "which",
        lambda name: f"C:/fake/{name}.cmd" if name in {"node", "pnpm", "npm"} else None,
    )
    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run_factory(tmp_path, calls))

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem", "--target", "all"])

    assert code == 0
    run_dir = _latest_run_dir(tmp_path)
    summary = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "conflict_detected=true" in summary
    assert "conflict_type=node_package_manager_lockfile_conflict" in summary
    assert "conflict_resolution=pnpm" in summary

    conflict = json.loads((run_dir / "conflict_outcome.json").read_text(encoding="utf-8"))
    assert conflict["conflict_detected"] is True
    assert conflict["selected_resolution"] == "pnpm"


def test_graph_stage_does_not_reuse_stale_plan_outputs(monkeypatch, tmp_path: Path):
    _write_package_json(tmp_path)
    # Seed stale artifacts that should be removed before graph stage runs.
    (tmp_path / "build_plan.json").write_text('{"stale":true}\n', encoding="utf-8")
    (tmp_path / "build_plan.hash.txt").write_text("stalehash\n", encoding="utf-8")

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
        if command[:2] == ["ngksenvcapsule", "resolve"]:
            (tmp_path / "env_capsule.resolved.json").write_text('{"resolved":true}\n', encoding="utf-8")
            return _Proc(returncode=0, stdout="resolve ok\n")
        if command[:2] == ["ngksenvcapsule", "lock"]:
            (tmp_path / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash123\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")
        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")
        if command[:2] == ["ngksgraph", "plan"]:
            return _Proc(returncode=2, stderr="graph failed\n")
        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")
        return _Proc(returncode=1, stderr="unexpected command")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    summary = (run_dir / "99_summary.txt").read_text(encoding="utf-8")
    assert "build_plan_hash_reason=missing_outputs" in summary
    assert "build_reason=missing_required_outputs" in summary
    # Stale artifacts should not survive as valid outputs.
    assert not (tmp_path / "build_plan.json").exists()
    assert not (tmp_path / "build_plan.hash.txt").exists()


def test_graph_uses_detected_nested_build_root(monkeypatch, tmp_path: Path):
    desktop = tmp_path / "desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    (desktop / "package.json").write_text(
        '{"name":"app","scripts":{"build":"node app.js"}}\n',
        encoding="utf-8",
    )

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

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True, env=None):
        del cwd, check, capture_output, text, env
        calls.append(list(command))

        if command[:2] == ["ngksenvcapsule", "resolve"]:
            (tmp_path / "env_capsule.resolved.json").write_text('{"resolved":true}\n', encoding="utf-8")
            return _Proc(returncode=0, stdout="resolve ok\n")

        if command[:2] == ["ngksenvcapsule", "lock"]:
            (tmp_path / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash123\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if command[:2] == ["ngksgraph", "plan"]:
            (desktop / "build_plan.json").write_text('{"plan":true}\n', encoding="utf-8")
            (desktop / "build_plan.hash.txt").write_text("planhash456\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="plan ok\n")

        if command[:2] == ["ngksbuildcore", "run"]:
            return _Proc(returncode=0, stdout="build ok\n")

        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")

        return _Proc(returncode=1, stderr="unexpected command")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem", "--target", "build"])

    assert code == 0
    graph_cmd = next(cmd for cmd in calls if cmd[:2] == ["ngksgraph", "plan"])
    assert "--project" in graph_cmd
    assert str(desktop) in graph_cmd

    buildcore_cmd = next(cmd for cmd in calls if cmd[:2] == ["ngksbuildcore", "run"])
    plan_arg = buildcore_cmd[buildcore_cmd.index("--plan") + 1]
    assert Path(plan_arg) == desktop / "build_plan.json"


def test_ngksgraph_mode_omits_generic_build_target(monkeypatch, tmp_path: Path):
    (tmp_path / "ngksgraph.toml").write_text(
        '\n'.join(
            [
                'name = "app"',
                '[[targets]]',
                'name = "app_main"',
                'type = "exe"',
                'src_glob = ["src/main.cpp"]',
                '[[targets]]',
                'name = "tests"',
                'type = "exe"',
                'src_glob = ["tests/main.cpp"]',
                '',
            ]
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    monkeypatch.setattr(
        fabric_main,
        "_detect_build_inputs",
        lambda project_root: (True, "ngksgraph", "ngksgraph.toml"),
    )

    monkeypatch.setattr(
        fabric_main,
        "resolve_component_cmd",
        lambda component_name, module_name: {
            "mode": "console",
            "argv": [component_name],
            "why": "test console resolver",
        },
    )

    def _fake_run(command, cwd=None, check=False, capture_output=True, text=True, env=None):
        del cwd, check, capture_output, text, env
        calls.append(list(command))

        if command[:2] == ["ngksenvcapsule", "resolve"]:
            (tmp_path / "env_capsule.resolved.json").write_text('{"resolved":true}\n', encoding="utf-8")
            return _Proc(returncode=0, stdout="resolve ok\n")

        if command[:2] == ["ngksenvcapsule", "lock"]:
            (tmp_path / "env_capsule.lock.json").write_text('{"lock":true}\n', encoding="utf-8")
            (tmp_path / "env_capsule.hash.txt").write_text("envhash123\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="lock ok\n")

        if command[:2] == ["ngksenvcapsule", "verify"]:
            return _Proc(returncode=0, stdout="verify ok\n")

        if command[:2] == ["ngksgraph", "plan"]:
            if "--target" in command and "build" in command:
                return _Proc(returncode=2, stderr="TARGET_NOT_FOUND: build\n")
            (tmp_path / "build_plan.json").write_text('{"plan":true}\n', encoding="utf-8")
            (tmp_path / "build_plan.hash.txt").write_text("planhash456\n", encoding="utf-8")
            return _Proc(returncode=0, stdout="plan ok\n")

        if command[:2] == ["ngksbuildcore", "run"]:
            return _Proc(returncode=0, stdout="build ok\n")

        if command[:2] == ["ngkslibrary", "assemble"]:
            return _Proc(returncode=0, stdout="library ok\n")

        return _Proc(returncode=1, stderr="unexpected command")

    monkeypatch.setattr(fabric_main.subprocess, "run", _fake_run)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem", "--target", "build"])

    assert code == 0
    graph_cmd = next(cmd for cmd in calls if cmd[:2] == ["ngksgraph", "plan"])
    assert "--target" in graph_cmd
    target_arg = graph_cmd[graph_cmd.index("--target") + 1]
    assert target_arg == "app_main"
    assert (tmp_path / "build_plan.json").exists()
    assert (tmp_path / "build_plan.hash.txt").exists()
