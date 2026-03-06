import json
import zipfile

from ngksgraph.build import configure_project
from ngksgraph.capsule import freeze_capsule
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.diff import list_snapshots


def test_freeze_from_snapshot_regenerates_missing_compdb(tmp_path):
    cfg = Config(
        out_dir="build",
        targets=[TargetConfig(name="app", type="exe", src_glob=["src/**/*.cpp"])],
        build_default_target="app",
    )
    cfg_path = tmp_path / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    configure_project(tmp_path, cfg_path)

    snaps_root = tmp_path / "build" / ".ngksgraph_snapshots"
    snap = list_snapshots(snaps_root)[-1]
    compdb_path = snap / "compdb.json"
    if compdb_path.exists():
        compdb_path.unlink()

    freeze_capsule(repo_root=tmp_path, config_path=cfg_path, from_snapshot=snap.name, verify=True)
    capsule_path = next((tmp_path / "build" / "ngksgraph_capsules").glob("*.ngkcapsule.zip"))

    with zipfile.ZipFile(capsule_path, mode="r") as zf:
        compdb = json.loads(zf.read("compdb.json").decode("utf-8"))
        assert isinstance(compdb, list)
        assert len(compdb) >= 1

        snap_ref = json.loads(zf.read("snapshot_ref.json").decode("utf-8"))
        assert snap_ref["fallbacks_used"]["compdb"] is True
