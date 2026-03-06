from __future__ import annotations

import argparse
import json
from pathlib import Path

from ngksgraph.cli import main
from ngksgraph.mode import Mode, get_mode


CONFIG_TEXT = "\n".join(
    [
        'name = "app"',
        'out_dir = "build"',
        '',
        '[profiles.debug]',
        'cflags = ["/Od"]',
        'defines = ["DEBUG"]',
        'ldflags = []',
        '',
        '[[targets]]',
        'name = "app"',
        'type = "exe"',
        'src_glob = ["src/**/*.cpp"]',
        'include_dirs = ["include"]',
        'defines = []',
        'cflags = []',
        'libs = []',
        'lib_dirs = []',
        'ldflags = []',
        'cxx_std = 20',
        'links = []',
    ]
)


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "include").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(CONFIG_TEXT, encoding="utf-8")
    return tmp_path


def test_mode_default_is_standalone(monkeypatch) -> None:
    monkeypatch.delenv("NGKS_MODE", raising=False)
    args = argparse.Namespace(mode=None)
    assert get_mode(args) == Mode.STANDALONE


def test_mode_env_fallback_ecosystem(monkeypatch) -> None:
    monkeypatch.setenv("NGKS_MODE", "ecosystem")
    args = argparse.Namespace(mode=None)
    assert get_mode(args) == Mode.ECOSYSTEM


def test_ecosystem_build_requires_capsule_binding(tmp_path: Path, capsys) -> None:
    project = _make_project(tmp_path)

    rc = main(
        [
            "build",
            "--project",
            str(project),
            "--mode",
            "ecosystem",
            "--profile",
            "debug",
            "--target",
            "app",
        ]
    )

    err = capsys.readouterr().err
    assert rc == 2
    assert "ECOSYSTEM_MODE_REQUIRES_ENV_CAPSULE_BINDING" in err


def test_ecosystem_build_emits_build_plan_and_hash(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    hash_value = "0" * 64
    hash_path = project / "env_capsule.hash.txt"
    hash_path.write_text(hash_value + "\n", encoding="utf-8")

    rc = main(
        [
            "build",
            "--project",
            str(project),
            "--mode",
            "ecosystem",
            "--env-capsule-hash",
            str(hash_path),
            "--profile",
            "debug",
            "--target",
            "app",
        ]
    )

    assert rc == 0

    plan_path = project / "build_plan.json"
    plan_hash_path = project / "build_plan.hash.txt"
    assert plan_path.exists()
    assert plan_hash_path.exists()
    assert not (project / "build" / "debug" / "bin" / "app.exe").exists()

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["env_capsule_hash"] == hash_value
    assert isinstance(payload.get("actions"), list) and payload["actions"]
