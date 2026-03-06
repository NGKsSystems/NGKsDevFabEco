from pathlib import Path

from ngksgraph.capsule import freeze_capsule
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.forensics import why_target


def test_why_from_capsule_mode(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=["core"]),
        ],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src" / "core").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "core" / "core.cpp").write_text("int core(){return 1;}", encoding="utf-8")
    (tmp_path / "src" / "app" / "main.cpp").write_text("int main(){return core();}", encoding="utf-8")

    frozen = freeze_capsule(repo_root=tmp_path, config_path=cfg_path, target="app", verify=True)
    capsule = Path(frozen["capsule_path"])

    result = why_target(tmp_path, cfg_path, "app", from_capsule=capsule)
    assert result["from_capsule"] == str(capsule).replace("\\", "/")
    assert result["target_overview"]["type"] == "exe"
    assert result["target_overview"]["full_closure"] == ["core"]
