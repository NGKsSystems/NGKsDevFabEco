from pathlib import Path

from ngksgraph.build import configure_project
from ngksgraph.capsule import freeze_capsule, verify_capsule
from ngksgraph.config import Config, TargetConfig, save_config

from tests.qt_test_tools import setup_fake_qt_tools


def _make_qt_project(tmp_path, qt):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg.qt.enabled = True
    cfg.qt.moc_path = qt["moc_path"]
    cfg.qt.uic_path = qt["uic_path"]
    cfg.qt.rcc_path = qt["rcc_path"]
    cfg.qt.include_dirs = ["C:/Qt/include", "C:/Qt/include/QtCore", "C:/Qt/include/QtWidgets"]
    cfg.qt.lib_dirs = ["C:/Qt/lib"]
    cfg.qt.libs = ["Qt6Core.lib", "Qt6Widgets.lib"]

    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src" / "res").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "src" / "widget.hpp").write_text("class Widget { Q_OBJECT };", encoding="utf-8")
    (tmp_path / "src" / "main.ui").write_text("<ui version=\"4.0\"></ui>", encoding="utf-8")
    (tmp_path / "src" / "res" / "icon.txt").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "resources.qrc").write_text(
        "<RCC><qresource><file>res/icon.txt</file></qresource></RCC>",
        encoding="utf-8",
    )

    configure_project(tmp_path, cfg_path)
    return cfg_path


def test_qt_capsule_freeze_verify_pass(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg_path = _make_qt_project(tmp_path, qt)

    frozen = freeze_capsule(repo_root=tmp_path, config_path=cfg_path, target="app", verify=True)
    capsule = Path(frozen["capsule_path"])
    result = verify_capsule(capsule)
    assert result["ok"] is True


def test_qt_tool_binary_change_fails_verify(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg_path = _make_qt_project(tmp_path, qt)

    frozen = freeze_capsule(repo_root=tmp_path, config_path=cfg_path, target="app", verify=True)
    capsule = Path(frozen["capsule_path"])

    moc_cmd = Path(qt["moc_path"])
    moc_cmd.write_text("@echo off\necho modified\n", encoding="utf-8")

    result = verify_capsule(capsule)
    assert result["ok"] is False
    assert any(m["component"] in {"qt_tool.moc.sha256", "qt_tool.moc.version"} for m in result["mismatches"])
