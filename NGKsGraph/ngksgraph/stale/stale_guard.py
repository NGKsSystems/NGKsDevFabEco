from __future__ import annotations

import json
import re
from pathlib import Path
from pathlib import PurePosixPath

from ngksgraph.probe.file_walker import relative
from ngksgraph.probe.path_classifier import is_stale_risk_path
from ngksgraph.stale.stale_rules import STALE_RULES


def _iter_stale_candidates(repo_root: Path):
    direct_names = ["build.ninja", "compile_commands.json", "cmake_install.cmake", "CMakeCache.txt"]
    for name in direct_names:
        candidate = repo_root / name
        if candidate.exists() and candidate.is_file():
            yield candidate

    for build_root in [repo_root / "build", repo_root / "out"]:
        if not build_root.exists() or not build_root.is_dir():
            continue
        for path in build_root.rglob("*"):
            if path.is_file():
                yield path


def _append_dead_path_items(repo_root: Path, stale_items: list[dict[str, object]]) -> None:
    cmake_cache_candidates = [repo_root / "CMakeCache.txt", repo_root / "build" / "CMakeCache.txt", repo_root / "out" / "CMakeCache.txt"]
    dead_path_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:PATH=(.+)$")
    for cache in cmake_cache_candidates:
        if not cache.exists():
            continue
        try:
            lines = cache.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = dead_path_pattern.match(line.strip())
            if not match:
                continue
            path_value = match.group(1).strip()
            if not path_value or path_value.startswith("$"):
                continue
            resolved = Path(path_value)
            if not resolved.exists():
                stale_items.append(
                    {
                        "path": relative(cache, repo_root),
                        "risk_level": "medium",
                        "classification": "blocked_stale_risk",
                        "reason": f"dead absolute path in CMake cache: {path_value}",
                        "action": "ignore",
                    }
                )
                break

    compdb_candidates = [repo_root / "compile_commands.json", repo_root / "build" / "compile_commands.json", repo_root / "out" / "compile_commands.json"]
    for compdb in compdb_candidates:
        if not compdb.exists():
            continue
        try:
            payload = json.loads(compdb.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            directory = str(entry.get("directory", ""))
            if directory and not Path(directory).exists():
                stale_items.append(
                    {
                        "path": relative(compdb, repo_root),
                        "risk_level": "medium",
                        "classification": "blocked_stale_risk",
                        "reason": f"compile database references missing directory: {directory}",
                        "action": "ignore",
                    }
                )
                break


def evaluate_stale_risk(repo_root: Path) -> dict[str, object]:
    stale_items: list[dict[str, object]] = []

    def _match_rule(rel: str) -> dict[str, str] | None:
        rel_path = PurePosixPath(rel)
        for rule in STALE_RULES:
            path_glob = str(rule.get("path_glob", "")).strip()
            if not path_glob:
                continue
            if rel_path.match(path_glob):
                return rule
        return None

    for path in _iter_stale_candidates(repo_root):
        rel = relative(path, repo_root)
        matched_rule = _match_rule(rel)
        if not matched_rule and is_stale_risk_path(rel):
            if path.name in {"build.ninja", "CMakeCache.txt", "compile_commands.json"}:
                matched_rule = {"risk_level": "high", "action": "ignore"}

        if matched_rule:
            stale_items.append(
                {
                    "path": rel,
                    "risk_level": str(matched_rule.get("risk_level", "high")),
                    "classification": "blocked_stale_risk",
                    "reason": "generated build artifact can poison inference",
                    "action": str(matched_rule.get("action", "ignore")),
                }
            )

    _append_dead_path_items(repo_root, stale_items)

    unique: dict[tuple[str, str], dict[str, object]] = {}
    for item in stale_items:
        key = (str(item.get("path", "")), str(item.get("reason", "")))
        unique[key] = item
    stale_items = sorted(unique.values(), key=lambda item: (str(item.get("path", "")), str(item.get("risk_level", ""))))

    summary = {
        "high": sum(1 for item in stale_items if item["risk_level"] == "high"),
        "medium": sum(1 for item in stale_items if item["risk_level"] == "medium"),
        "low": sum(1 for item in stale_items if item["risk_level"] == "low"),
    }
    return {
        "repo_root": str(repo_root),
        "stale_items": stale_items,
        "summary": summary,
    }
