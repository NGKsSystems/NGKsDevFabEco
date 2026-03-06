from __future__ import annotations

from pathlib import Path

from ngksgraph.config import Config, TargetConfig
from ngksgraph.util import rel_path


def scan_target_sources(repo_root: Path, target: TargetConfig) -> list[str]:
    files: set[str] = set()
    for pattern in target.src_glob:
        for path in repo_root.glob(pattern):
            if path.is_file() and path.suffix.lower() == ".cpp":
                files.add(rel_path(path, repo_root))
    return sorted(files)


def scan_sources_by_target(repo_root: Path, config: Config) -> dict[str, list[str]]:
    config.normalize()
    out: dict[str, list[str]] = {}
    for target in config.targets:
        out[target.name] = scan_target_sources(repo_root, target)
    return out


def scan_sources(repo_root: Path, config: Config) -> list[str]:
    source_map = scan_sources_by_target(repo_root, config)
    default_target = config.default_target_name()
    return source_map.get(default_target, [])
