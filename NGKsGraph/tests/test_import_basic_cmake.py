from __future__ import annotations

from pathlib import Path

import ngksgraph.cli as graph_cli
from ngksgraph.cli import main
from ngksgraph.config import load_config


def test_init_template_multi_target(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rc = main(["init", "--template", "multi-target"])
    assert rc == 0

    cfg_path = tmp_path / "ngksgraph.toml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "[[targets]]" in text
    assert "[profiles.debug]" in text
    assert "[profiles.release]" in text


def test_init_uses_packaged_template_when_repo_template_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(graph_cli, "_repo_root_from_cwd", lambda: tmp_path)

    rc = main(["init", "--template", "qt-app"])
    assert rc == 0

    cfg_path = tmp_path / "ngksgraph.toml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "modules = [\"Core\", \"Gui\", \"Widgets\"]" in text


def test_init_default_emits_repo_aware_multitarget_for_engine_and_multiple_apps(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "engine" / "core" / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine" / "core" / "src" / "core.cpp").write_text("int core(){return 0;}\n", encoding="utf-8")
    (tmp_path / "apps" / "alpha").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "beta").mkdir(parents=True, exist_ok=True)
    (tmp_path / "apps" / "alpha" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "apps" / "beta" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    rc = main(["init"])
    assert rc == 0

    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")
    assert "[[targets]]" in cfg_text
    assert 'name = "engine"' in cfg_text
    assert 'name = "alpha"' in cfg_text
    assert 'name = "beta"' in cfg_text
    assert '[build]' in cfg_text
    assert 'default_target = "alpha"' in cfg_text


def test_import_cmake_basic_mapping(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "src" / "core.cpp").write_text("int core(){return 1;}\n", encoding="utf-8")
    (tmp_path / "include").mkdir()

    (tmp_path / "CMakeLists.txt").write_text(
        "\n".join(
            [
                "cmake_minimum_required(VERSION 3.20)",
                "project(Demo LANGUAGES CXX)",
                "set(CMAKE_CXX_STANDARD 20)",
                "set(APP_SOURCES src/main.cpp)",
                "add_library(core STATIC src/core.cpp)",
                "target_include_directories(core PRIVATE include)",
                "add_executable(app ${APP_SOURCES})",
                "target_compile_definitions(app PRIVATE APP_DEF=1)",
                "target_compile_options(app PRIVATE /W4)",
                "target_link_options(app PRIVATE /INCREMENTAL:NO)",
                "target_link_libraries(app PRIVATE core user32 Qt6::Widgets)",
            ]
        ),
        encoding="utf-8",
    )

    rc = main(["import", "--cmake", "."])
    assert rc == 0

    cfg = load_config(tmp_path / "ngksgraph.toml")
    names = {t.name for t in cfg.targets}
    assert names == {"core", "app"}

    app = cfg.get_target("app")
    core = cfg.get_target("core")

    assert "core" in app.links
    assert "user32" in app.libs
    assert "APP_DEF=1" in app.defines
    assert "/W4" in app.cflags
    assert "/INCREMENTAL:NO" in app.ldflags
    assert "include" in core.include_dirs
    assert cfg.qt.enabled is True
    assert "Widgets" in cfg.qt.modules
    assert cfg.build_default_target == "app"


def test_import_cmake_does_not_overwrite_without_force(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ngksgraph.toml").write_text('name = "existing"\n', encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(Demo)\n", encoding="utf-8")

    rc = main(["import", "--cmake", "CMakeLists.txt"])
    assert rc == 1

    text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")
    assert "existing" in text
