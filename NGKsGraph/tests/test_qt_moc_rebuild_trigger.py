from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config

from tests.qt_test_tools import setup_fake_qt_tools


def test_modify_header_triggers_moc_rebuild(tmp_path):
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
    hdr = tmp_path / "src" / "widget.hpp"
    hdr.write_text("class Widget { Q_OBJECT };", encoding="utf-8")
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    first = configure_project(tmp_path, cfg_path)["qt_result"]
    assert any(n.kind == "moc" and n.status == "generated" for n in first.generator_nodes)

    second = configure_project(tmp_path, cfg_path)["qt_result"]
    assert any(n.kind == "moc" and n.status == "skipped" for n in second.generator_nodes)

    hdr.write_text("class Widget { Q_OBJECT public: int x; };", encoding="utf-8")
    third = configure_project(tmp_path, cfg_path)["qt_result"]
    assert any(n.kind == "moc" and n.status == "generated" for n in third.generator_nodes)
