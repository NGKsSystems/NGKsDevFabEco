from ngksgraph.build import configure_project
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.forensics import rebuild_cause_target


def test_rebuild_cause_identifies_define_change(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"], defines=["UNICODE"])],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    configure_project(tmp_path, cfg_path)

    cfg.targets[0].defines.append("DEBUG")
    save_config(cfg_path, cfg)
    configure_project(tmp_path, cfg_path)

    result = rebuild_cause_target(tmp_path, cfg_path, "app")
    structural = result["structural_change"]

    assert result["message"] == "ok"
    assert structural["field_root_cause"]["defines_added"] == ["DEBUG"]
    assert result["command_change"]["compdb_hash_changed"] is True
    assert "defines" in result["command_change"]["command_delta_fields"]
