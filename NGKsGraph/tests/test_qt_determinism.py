import json

from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.util import sha256_file

from tests.qt_test_tools import setup_fake_qt_tools


def test_qt_determinism_across_two_runs(tmp_path):
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
    (tmp_path / "src" / "widget.hpp").write_text("class Widget { Q_OBJECT };", encoding="utf-8")
    (tmp_path / "src" / "main.ui").write_text("<ui version=\"4.0\"></ui>", encoding="utf-8")
    (tmp_path / "src" / "res" / "icon.txt").write_text("x", encoding="utf-8")
    (tmp_path / "src" / "resources.qrc").write_text(
        "<RCC><qresource><file>res/icon.txt</file></qresource></RCC>",
        encoding="utf-8",
    )

    configure_project(tmp_path, cfg_path)
    compdb_a = (tmp_path / "build" / "compile_commands.json").read_text(encoding="utf-8")
    graph_a = json.loads((tmp_path / "build" / "ngksgraph_graph.json").read_text(encoding="utf-8"))
    moc_hash_a = sha256_file(tmp_path / "build" / "qt" / "moc_widget.cpp")

    configure_project(tmp_path, cfg_path)
    compdb_b = (tmp_path / "build" / "compile_commands.json").read_text(encoding="utf-8")
    graph_b = json.loads((tmp_path / "build" / "ngksgraph_graph.json").read_text(encoding="utf-8"))
    moc_hash_b = sha256_file(tmp_path / "build" / "qt" / "moc_widget.cpp")

    assert compdb_a == compdb_b
    assert graph_a["generator_nodes"] == graph_b["generator_nodes"]
    assert moc_hash_a == moc_hash_b
