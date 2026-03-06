import json

from ngksgraph.build import build_project
from ngksgraph.config import Config, TargetConfig, save_config


def test_build_selects_default_target(monkeypatch, tmp_path):
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
    (tmp_path / "src" / "core" / "core.cpp").write_text("int x(){return 1;}", encoding="utf-8")
    (tmp_path / "src" / "app" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    monkeypatch.setattr("ngksgraph.build.has_cl_link", lambda env: True)

    rc = build_project(tmp_path, cfg_path, max_attempts=1)
    assert rc == 0

    report = json.loads((tmp_path / "build" / "ngksgraph_last_report.json").read_text(encoding="utf-8"))
    assert report["target"] == "app"


def test_build_selects_explicit_target(monkeypatch, tmp_path):
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
    (tmp_path / "src" / "core" / "core.cpp").write_text("int x(){return 1;}", encoding="utf-8")
    (tmp_path / "src" / "app" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")

    monkeypatch.setattr("ngksgraph.build.has_cl_link", lambda env: True)

    rc = build_project(tmp_path, cfg_path, max_attempts=1, target="core")
    assert rc == 0

    report = json.loads((tmp_path / "build" / "ngksgraph_last_report.json").read_text(encoding="utf-8"))
    assert report["target"] == "core"
