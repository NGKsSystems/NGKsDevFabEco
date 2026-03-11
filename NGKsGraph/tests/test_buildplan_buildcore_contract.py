from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.cli import main
from ngksgraph.config import Config, QtConfig, TargetConfig
from ngksgraph.graph import build_graph_from_project
from ngksgraph.plan import create_buildcore_plan
from ngksgraph.torture_project import gen_project
from ngksbuildcore.plan import load_plan
import pytest


def test_buildplan_default_output_emits_buildcore_nodes(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9301, with_profiles=True, qobject_headers=2, ui_files=1, qrc_files=1)
    monkeypatch.chdir(project.repo_root)

    assert main(["configure", "--profile", "debug"]) == 0
    assert main(["buildplan", "--profile", "debug"]) == 0

    out_path = project.repo_root / "build_graph" / "debug" / "ngksbuildcore_plan.json"
    assert out_path.exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(payload.get("nodes"), list)
    assert payload["nodes"]
    node_ids = [str(n.get("id", "")) for n in payload["nodes"] if isinstance(n, dict)]
    assert any(node_id.startswith("cl:") for node_id in node_ids)
    assert any(node_id.startswith("link:") for node_id in node_ids)

    plan = load_plan(out_path)
    assert len(plan.nodes) > 0


def test_buildplan_explicit_output_path_still_supported(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9302, with_profiles=True, qobject_headers=2, ui_files=1, qrc_files=1)
    monkeypatch.chdir(project.repo_root)

    explicit = project.repo_root / "build_graph" / "debug" / "custom_buildcore_plan.json"

    assert main(["configure", "--profile", "debug"]) == 0
    assert main(["buildplan", "--profile", "debug", "--out", str(explicit)]) == 0

    assert explicit.exists()
    plan = load_plan(explicit)
    assert len(plan.nodes) > 0


def test_buildplan_includes_qt_generated_compile_nodes(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9303, with_profiles=True, qobject_headers=3, ui_files=1, qrc_files=1)
    monkeypatch.chdir(project.repo_root)

    assert main(["buildplan", "--profile", "debug"]) == 0

    plan_path = project.repo_root / "build_graph" / "debug" / "ngksbuildcore_plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])

    compile_inputs: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        if not node_id.startswith("cl:"):
            continue
        compile_inputs.extend(str(v) for v in (node.get("inputs", []) or []))

    assert any("/qt/moc_" in value.replace("\\", "/") for value in compile_inputs), "expected moc compile input in buildplan"


def test_configure_fails_when_repo_has_sources_but_glob_matches_none(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "apps").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(
        "\n".join(
            [
                'name = "app"',
                'out_dir = "build"',
                'target_type = "exe"',
                'cxx_std = 20',
                'src_glob = ["src/**/*.cpp"]',
                'include_dirs = ["include"]',
                '',
                '[profiles.debug]',
                'cflags = []',
                'defines = []',
                'ldflags = []',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="NO_SOURCES_MATCHED"):
        main(["configure", "--profile", "debug"])


def test_default_template_covers_engine_ui_header_include_resolution(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "apps" / "widget_sandbox").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine" / "ui").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "widget_sandbox" / "main.cpp").write_text(
        "#include \"button.hpp\"\nint main(){return 0;}\n",
        encoding="utf-8",
    )
    (tmp_path / "engine" / "ui" / "button.hpp").write_text("#pragma once\n", encoding="utf-8")
    (tmp_path / "engine" / "ui" / "button.cpp").write_text(
        "#include \"button.hpp\"\n",
        encoding="utf-8",
    )

    assert main(["init"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")
    assert '"engine/ui"' in cfg_text

    assert main(["configure", "--profile", "debug"]) == 0
    assert main(["buildplan", "--profile", "debug"]) == 0

    plan_path = tmp_path / "build_graph" / "debug" / "ngksbuildcore_plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    widget_compile = [
        str(node.get("cmd", ""))
        for node in nodes
        if "apps/widget_sandbox/main.cpp" in str(node.get("cmd", ""))
    ]
    assert widget_compile, "expected compile node for apps/widget_sandbox/main.cpp"
    assert any("/Iengine/ui" in cmd for cmd in widget_compile)


def test_repo_aware_default_topology_avoids_multi_main_linking(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "engine" / "core" / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine" / "ui").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine" / "core" / "src" / "core.cpp").write_text("int core(){return 0;}\n", encoding="utf-8")
    (tmp_path / "engine" / "ui" / "button.hpp").write_text("#pragma once\n", encoding="utf-8")
    (tmp_path / "apps" / "alpha").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "beta").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "alpha" / "main.cpp").write_text("#include \"button.hpp\"\nint main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "apps" / "beta" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    assert main(["init"]) == 0
    assert main(["configure", "--profile", "debug"]) == 0
    assert main(["buildplan", "--profile", "debug"]) == 0

    plan_path = tmp_path / "build_graph" / "debug" / "ngksbuildcore_plan.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    link_nodes = [node for node in nodes if str(node.get("id", "")).startswith("link:")]
    assert len(link_nodes) == 1

    link_cmd = str(link_nodes[0].get("cmd", ""))
    assert "apps/alpha/main.obj" in link_cmd
    assert "apps/beta/main.obj" not in link_cmd
    assert "user32.lib" in link_cmd
    assert "d3d11.lib" in link_cmd


def test_buildcore_plan_emits_windeployqt_for_qt_executable(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    qt_bin = tmp_path / "fake_qt" / "bin"
    qt_bin.mkdir(parents=True, exist_ok=True)
    (qt_bin / "windeployqt.exe").write_text("", encoding="utf-8")

    cfg = Config(
        name="app",
        out_dir="build/debug",
        targets=[
            TargetConfig(
                name="app",
                type="exe",
                src_glob=["src/**/*.cpp"],
                libs=["Qt6Core", "user32"],
            )
        ],
        qt=QtConfig(enabled=True, qt_root=str((tmp_path / "fake_qt").resolve())),
    )

    graph = build_graph_from_project(cfg, source_map={"app": ["src/main.cpp"]}, msvc_auto=False)
    payload, warnings = create_buildcore_plan(tmp_path, selected_target="app", graph=graph)

    assert not [warning for warning in warnings if warning.startswith("QT_WINDEPLOYQT_MISSING")]

    nodes = payload["nodes"]
    deploy_nodes = [node for node in nodes if str(node.get("id", "")).startswith("windeployqt:")]
    assert len(deploy_nodes) == 1

    link_nodes = [node for node in nodes if str(node.get("id", "")).startswith("link:")]
    assert len(link_nodes) == 1

    deploy = deploy_nodes[0]
    assert deploy.get("deps") == [link_nodes[0]["id"]]
    assert "windeployqt.exe" in str(deploy.get("cmd", ""))
    assert "build/debug/bin/app.exe" in str(deploy.get("cmd", "")).replace("\\", "/")


def test_buildcore_plan_discovers_windeployqt_from_lib_dirs_when_qt_disabled(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    qt_root = tmp_path / "Qt" / "6.10.2" / "msvc2022_64"
    qt_lib = qt_root / "lib"
    qt_bin = qt_root / "bin"
    qt_lib.mkdir(parents=True, exist_ok=True)
    qt_bin.mkdir(parents=True, exist_ok=True)
    (qt_bin / "windeployqt.exe").write_text("", encoding="utf-8")

    cfg = Config(
        name="app",
        out_dir="build/debug",
        targets=[
            TargetConfig(
                name="app",
                type="exe",
                src_glob=["src/**/*.cpp"],
                libs=["Qt6Core", "Qt6Widgets"],
                lib_dirs=[str(qt_lib.resolve())],
            )
        ],
        qt=QtConfig(enabled=False),
    )

    graph = build_graph_from_project(cfg, source_map={"app": ["src/main.cpp"]}, msvc_auto=False)
    payload, warnings = create_buildcore_plan(tmp_path, selected_target="app", graph=graph)

    assert not [warning for warning in warnings if warning.startswith("QT_WINDEPLOYQT_MISSING")]
    deploy_nodes = [node for node in payload["nodes"] if str(node.get("id", "")).startswith("windeployqt:")]
    assert len(deploy_nodes) == 1
    assert "windeployqt.exe" in str(deploy_nodes[0].get("cmd", ""))
