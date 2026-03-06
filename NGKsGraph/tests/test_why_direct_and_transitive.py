from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.forensics import why_target


def test_why_reports_direct_and_transitive_closure(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"]),
            TargetConfig(name="util", type="staticlib", src_glob=["src/util/**/*.cpp"], links=["core"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=["util"]),
        ],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src" / "core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "util").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "core" / "core.cpp").write_text("int core(){return 1;}", encoding="utf-8")
    (tmp_path / "src" / "util" / "util.cpp").write_text("int util(){return core();}", encoding="utf-8")
    (tmp_path / "src" / "app" / "main.cpp").write_text("int main(){return util();}", encoding="utf-8")

    result = why_target(tmp_path, cfg_path, "app")

    overview = result["target_overview"]
    assert overview["direct_links"] == ["util"]
    assert overview["full_closure"] == ["core", "util"]
    assert overview["closure_hash"]

    edge_attr = result["edge_attribution"]
    assert edge_attr[0]["link"] == "util"
    assert edge_attr[0]["origin"]["type"] == "config_field"
    assert edge_attr[0]["origin"]["field"] == "links"

    closure_attr = {item["dependency"]: item for item in result["closure_attribution"]}
    assert closure_attr["util"]["direct_link"] is True
    assert closure_attr["core"]["indirect_link"] is True
    assert any("app -> util -> core" == p for p in closure_attr["core"]["paths"])
