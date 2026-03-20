from __future__ import annotations

from pathlib import Path

import pytest

from ngksgraph.build import resolve_plan_context


def _write_project(tmp_path: Path, with_profiles: bool) -> tuple[Path, Path]:
    repo = Path(tmp_path)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    lines = [
        'name = "app"',
        'out_dir = "build"',
        'target_type = "exe"',
        'src_glob = ["src/**/*.cpp"]',
    ]
    if with_profiles:
        lines.extend(
            [
                "",
                "[profiles.debug]",
                'cflags = []',
                'defines = []',
                'ldflags = []',
                "",
                "[profiles.release]",
                'cflags = []',
                'defines = []',
                'ldflags = []',
            ]
        )

    config_path = repo / "ngksgraph.toml"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo, config_path


def test_no_profiles_allows_configure_without_profile(tmp_path: Path):
    repo, config_path = _write_project(tmp_path, with_profiles=False)
    configured = resolve_plan_context(repo, config_path, profile=None)
    assert configured["profile"] == "default"


def test_profiles_require_explicit_profile_and_list_available_profiles(tmp_path: Path):
    repo, config_path = _write_project(tmp_path, with_profiles=True)
    with pytest.raises(ValueError, match=r"--profile is required\. Available profiles: debug, release"):
        resolve_plan_context(repo, config_path, profile=None)


def test_unknown_profile_lists_available_profiles(tmp_path: Path):
    repo, config_path = _write_project(tmp_path, with_profiles=True)
    with pytest.raises(ValueError, match=r"Unknown profile 'dev'\. Available profiles: debug, release"):
        resolve_plan_context(repo, config_path, profile="dev")


def test_valid_profile_configure_proceeds(tmp_path: Path):
    repo, config_path = _write_project(tmp_path, with_profiles=True)
    configured = resolve_plan_context(repo, config_path, profile="debug")
    assert configured["profile"] == "debug"