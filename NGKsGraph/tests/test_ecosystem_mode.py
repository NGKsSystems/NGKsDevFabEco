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


def test_ecosystem_build_prefers_node_plan_when_package_json_present(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    (project / "package.json").write_text(
        json.dumps({"name": "app", "scripts": {"build": "vite build", "dev": "vite"}}),
        encoding="utf-8",
    )
    (project / "package-lock.json").write_text("{}\n", encoding="utf-8")

    hash_value = "1" * 64
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
    payload = json.loads((project / "build_plan.json").read_text(encoding="utf-8"))
    assert payload["requirements"]["language"] == "node"
    assert payload["target"] == "build"
    assert payload["actions"][0]["id"] == "node:script:build"
    assert payload["actions"][0]["argv"][:3] == ["npm", "run", "build"]


def test_ecosystem_plan_works_without_ngksgraph_toml_for_node(tmp_path: Path) -> None:
    project = tmp_path
    (project / "package.json").write_text(
        json.dumps({"name": "app", "scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )
    (project / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")

    hash_value = "2" * 64
    hash_path = project / "env_capsule.hash.txt"
    hash_path.write_text(hash_value + "\n", encoding="utf-8")

    rc = main(
        [
            "plan",
            "--project",
            str(project),
            "--mode",
            "ecosystem",
            "--env-capsule-hash",
            str(hash_path),
            "--target",
            "build",
        ]
    )

    assert rc == 0
    payload = json.loads((project / "build_plan.json").read_text(encoding="utf-8"))
    assert payload["requirements"]["language"] == "node"
    assert payload["actions"][0]["argv"][:3] == ["pnpm", "run", "build"]


def test_ecosystem_plan_works_without_ngksgraph_toml_for_flutter(tmp_path: Path) -> None:
    project = tmp_path
    (project / "pubspec.yaml").write_text(
        "name: demo_flutter\n"
        "description: demo\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
        encoding="utf-8",
    )
    (project / "windows").mkdir(parents=True, exist_ok=True)

    hash_value = "3" * 64
    hash_path = project / "env_capsule.hash.txt"
    hash_path.write_text(hash_value + "\n", encoding="utf-8")

    rc = main(
        [
            "plan",
            "--project",
            str(project),
            "--mode",
            "ecosystem",
            "--env-capsule-hash",
            str(hash_path),
            "--target",
            "build",
        ]
    )

    assert rc == 0
    payload = json.loads((project / "build_plan.json").read_text(encoding="utf-8"))
    assert payload["requirements"]["language"] == "flutter"
    assert payload["requirements"]["package_manager"] == "pub"
    assert payload["actions"][0]["argv"] == ["flutter", "build", "windows"]
