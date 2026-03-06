from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config

from tests.qt_test_tools import setup_fake_qt_tools


def test_ui_file_generates_uic_header(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg.qt.enabled = True
    cfg.qt.moc_path = qt["moc_path"]
    cfg.qt.uic_path = qt["uic_path"]
    cfg.qt.rcc_path = qt["rcc_path"]
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "src" / "main.ui").write_text("<ui version=\"4.0\"></ui>", encoding="utf-8")

    configured = configure_project(tmp_path, cfg_path)
    nodes = configured["qt_result"].generator_nodes
    assert any(n.kind == "uic" for n in nodes)
    assert (tmp_path / "build" / "qt" / "ui_main.h").exists()


def test_qrc_file_generates_rcc_cpp(tmp_path):
    qt = setup_fake_qt_tools(tmp_path)
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg.qt.enabled = True
    cfg.qt.moc_path = qt["moc_path"]
    cfg.qt.uic_path = qt["uic_path"]
    cfg.qt.rcc_path = qt["rcc_path"]
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src" / "res").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "src" / "res" / "icon.txt").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "resources.qrc").write_text(
        "<RCC><qresource><file>res/icon.txt</file></qresource></RCC>",
        encoding="utf-8",
    )

    configured = configure_project(tmp_path, cfg_path)
    nodes = configured["qt_result"].generator_nodes
    assert any(n.kind == "rcc" for n in nodes)
    assert (tmp_path / "build" / "qt" / "qrc_resources.cpp").exists()
