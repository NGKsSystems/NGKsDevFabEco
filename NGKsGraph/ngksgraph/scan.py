from __future__ import annotations

from pathlib import Path

from ngksgraph.config import Config, TargetConfig
from ngksgraph.util import rel_path


_SOURCE_SUFFIXES = {".cpp", ".c"}
_IGNORED_ROOTS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "_proof",
    "_artifacts",
    "third_party",
    "node_modules",
}


def scan_target_sources(repo_root: Path, target: TargetConfig) -> list[str]:
    files: set[str] = set()
    for pattern in target.src_glob:
        for path in repo_root.glob(pattern):
            if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES:
                files.add(rel_path(path, repo_root))
    return sorted(files)


def discover_repo_source_candidates(repo_root: Path, limit: int = 20) -> list[str]:
    candidates: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        try:
            rel = path.resolve().relative_to(repo_root.resolve())
        except Exception:
            continue
        parts = rel.parts
        if parts and parts[0] in _IGNORED_ROOTS:
            continue
        candidates.append(rel_path(path, repo_root))
    candidates = sorted(set(candidates))
    if limit > 0:
        return candidates[:limit]
    return candidates


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
