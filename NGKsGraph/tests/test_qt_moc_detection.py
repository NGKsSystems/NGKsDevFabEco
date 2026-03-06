from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config

from tests.qt_test_tools import setup_fake_qt_tools


def _base_config(tmp_path, qt_paths):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.{cpp,h,hpp,ui,qrc}", "src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg.qt.enabled = True
    cfg.qt.moc_path = qt_paths["moc_path"]
    cfg.qt.uic_path = qt_paths["uic_path"]
    cfg.qt.rcc_path = qt_paths["rcc_path"]
    cfg.qt.include_dirs = ["C:/Qt/include", "C:/Qt/include/QtCore"]
    cfg.qt.lib_dirs = ["C:/Qt/lib"]
    cfg.qt.libs = ["Qt6Core.lib", "Qt6Widgets.lib"]
    return cfg


def test_header_without_qobject_has_no_moc_node(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg = _base_config(tmp_path, qt)
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "src" / "widget.hpp").write_text("class Widget{};", encoding="utf-8")

    configured = configure_project(tmp_path, cfg_path)
    nodes = configured["qt_result"].generator_nodes
    assert not any(node.kind == "moc" for node in nodes)


def test_header_with_qobject_has_moc_node(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg = _base_config(tmp_path, qt)
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "src" / "widget.hpp").write_text("class Widget { Q_OBJECT };", encoding="utf-8")

    configured = configure_project(tmp_path, cfg_path)
    nodes = configured["qt_result"].generator_nodes
    assert any(node.kind == "moc" for node in nodes)
