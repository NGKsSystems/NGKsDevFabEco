import json
import zipfile

from ngksgraph.capsule import freeze_capsule
from ngksgraph.config import Config, TargetConfig, save_config


def test_capsule_contains_no_secret_env_dump(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    freeze_capsule(repo_root=tmp_path, config_path=cfg_path, verify=True)
    capsule_path = next((tmp_path / "build" / "ngksgraph_capsules").glob("*.ngkcapsule.zip"))

    with zipfile.ZipFile(capsule_path, mode="r") as zf:
        joined = "\n".join(zf.read(name).decode("utf-8", errors="ignore") for name in zf.namelist())
        upper = joined.upper()
        assert "PATH=" not in upper
        assert "INCLUDE=" not in upper
        assert "LIB=" not in upper

        toolchain = json.loads(zf.read("toolchain.json").decode("utf-8"))
        allowed = {
            "python_version",
            "platform",
            "msvc_auto_used",
            "vswhere_path",
            "vs_install_path",
            "vsdevcmd_path",
            "cl_version",
        }
        assert set(toolchain.keys()).issubset(allowed)
