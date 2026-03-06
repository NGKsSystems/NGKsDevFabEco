from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.forensics import symbol_forensics


def test_symbol_forensics_suggests_missing_link(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=[]),
        ],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src" / "core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "core" / "foo.cpp").write_text("int foo_bar(){return 1;}", encoding="utf-8")
    (tmp_path / "src" / "app" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    configured = configure_project(tmp_path, cfg_path)
    graph = configured["graph_payload"]

    log_text = "error LNK2019: unresolved external symbol foo_bar referenced in function main"
    suggestions = symbol_forensics(log_text, tmp_path, cfg, "app", graph)

    assert suggestions
    assert suggestions[0]["symbol"] == "foo_bar"
    assert suggestions[0]["likely_target"] == "core"
    assert suggestions[0]["suggestion"]["missing_link_edge"] == "app -> core"
