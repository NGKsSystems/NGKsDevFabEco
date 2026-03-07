from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.cli import main
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
