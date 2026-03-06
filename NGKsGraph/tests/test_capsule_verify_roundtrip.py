from pathlib import Path

from ngksgraph.capsule import freeze_capsule, thaw_capsule, verify_capsule
from ngksgraph.config import Config, TargetConfig, save_config


def test_capsule_verify_roundtrip(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    frozen = freeze_capsule(repo_root=tmp_path, config_path=cfg_path, verify=True)
    capsule_path = Path(frozen["capsule_path"])

    verified = verify_capsule(capsule_path)
    assert verified["ok"] is True

    out_dir = tmp_path / "thawed"
    thawed = thaw_capsule(capsule_path=capsule_path, out_dir=out_dir, verify=True)
    assert thawed["ok"] is True
    assert (out_dir / "compile_commands.json").exists()
    assert (out_dir / "ngksgraph_graph.json").exists()
    assert (out_dir / "config.normalized.json").exists()
