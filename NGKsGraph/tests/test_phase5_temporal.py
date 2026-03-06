import json

from ngksgraph.build import configure_project, trace_source
from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.diff import list_snapshots, structural_diff, summarize_diff


def _write_sources(root):
    (root / "src" / "core").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app").mkdir(parents=True, exist_ok=True)
    (root / "src" / "core" / "core.cpp").write_text("int core(){return 1;}", encoding="utf-8")
    (root / "src" / "app" / "main.cpp").write_text("int main(){return core();}", encoding="utf-8")


def test_configure_writes_snapshot_hashes_and_meta(tmp_path):
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
    _write_sources(tmp_path)

    configured = configure_project(tmp_path, cfg_path)
    info = configured["snapshot_info"]

    assert info["snapshot_path"] is not None
    assert "graph_hash" in info["hashes"]
    assert "compdb_hash" in info["hashes"]
    assert "closure_hashes" in info["hashes"]

    snap_dir = configured["paths"]["out_dir"] / ".ngksgraph_snapshots"
    snaps = list_snapshots(snap_dir)
    assert len(snaps) == 1

    meta = json.loads((snaps[0] / "meta.json").read_text(encoding="utf-8"))
    assert meta["sizes"]["targets"] == 2
    assert meta["sizes"]["compile_commands"] >= 2


def test_structural_diff_detects_target_changes(tmp_path):
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
    _write_sources(tmp_path)

    configure_project(tmp_path, cfg_path)

    cfg.targets[1].defines.append("USE_TRACE")
    save_config(cfg_path, cfg)
    configure_project(tmp_path, cfg_path)

    snap_dir = tmp_path / "build" / ".ngksgraph_snapshots"
    snaps = list_snapshots(snap_dir)
    assert len(snaps) >= 2

    diff_obj = structural_diff(snaps[-2], snaps[-1])
    summary = summarize_diff(diff_obj)

    assert "app" in summary["changed_targets"]
    assert diff_obj["hash_changes"]


def test_trace_source_reports_impacted_executables(tmp_path):
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
    _write_sources(tmp_path)

    result = trace_source(tmp_path, cfg_path, "src/core/core.cpp")
    assert result["status"] == "OK"
    assert "core" in result["owners"]
    assert "app" in result["impacted_targets"]
    assert result["impacted_executables"] == ["app"]
