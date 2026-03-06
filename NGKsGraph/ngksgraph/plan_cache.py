from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
from typing import Any
import shutil as _shutil
import xml.etree.ElementTree as ET

from ngksgraph import __version__
from ngksgraph.config import Config
from ngksgraph.hashutil import stable_json_dumps, sha256_text
from ngksgraph.util import normalize_path, rel_path, sha256_file


CACHE_SCHEMA_VERSION = 1


def cache_paths(repo_root: Path, profile: str) -> dict[str, Path]:
    cache_root = repo_root / ".ngksgraph_cache"
    profile_dir = cache_root / f"profile_{profile}"
    return {
        "root": cache_root,
        "version": cache_root / "cache_version.txt",
        "profile": profile_dir,
        "plan": profile_dir / "plan.json",
        "plan_key": profile_dir / "plan_key.json",
        "plan_key_sha": profile_dir / "plan_key.sha256",
        "fingerprint": profile_dir / "scan_fingerprint.json",
        "fingerprint_sha": profile_dir / "scan_fingerprint.sha256",
        "last_hit": profile_dir / "last_hit.txt",
    }


def ensure_cache_layout(repo_root: Path, profile: str) -> dict[str, Path]:
    paths = cache_paths(repo_root, profile)
    paths["profile"].mkdir(parents=True, exist_ok=True)
    paths["version"].write_text(str(CACHE_SCHEMA_VERSION), encoding="utf-8")
    return paths


def clear_profile_cache(repo_root: Path, profile: str) -> None:
    profile_dir = cache_paths(repo_root, profile)["profile"]
    if profile_dir.exists():
        shutil.rmtree(profile_dir, ignore_errors=True)


def _pattern_root(pattern: str) -> str:
    wildcard_pos = len(pattern)
    for token in ["*", "?", "["]:
        idx = pattern.find(token)
        if idx != -1:
            wildcard_pos = min(wildcard_pos, idx)
    root = pattern[:wildcard_pos].rstrip("/\\")
    return root or "."


def _target_scope_roots(repo_root: Path, src_glob: list[str]) -> list[Path]:
    roots = []
    seen = set()
    for pattern in src_glob:
        root = (repo_root / _pattern_root(pattern)).resolve()
        norm = normalize_path(root)
        if norm in seen:
            continue
        seen.add(norm)
        roots.append(root)
    return sorted(roots, key=lambda p: normalize_path(p))


def _qrc_referenced_files(repo_root: Path, qrc_rel_paths: set[str]) -> set[str]:
    out: set[str] = set()
    for rel in sorted(qrc_rel_paths):
        qrc_path = (repo_root / rel).resolve()
        if not qrc_path.exists() or not qrc_path.is_file():
            continue
        try:
            tree = ET.fromstring(qrc_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        base = qrc_path.parent
        for elem in tree.iter("file"):
            if not elem.text:
                continue
            candidate = (base / elem.text.strip()).resolve()
            if candidate.exists() and candidate.is_file():
                out.add(rel_path(candidate, repo_root))
    return out


def build_scan_fingerprint(repo_root: Path, config: Config, source_map: dict[str, list[str]]) -> dict[str, Any]:
    out_prefix = normalize_path(config.out_dir).rstrip("/") + "/"
    source_paths = sorted(
        {
            normalize_path(src)
            for values in source_map.values()
            for src in values
            if not normalize_path(src).startswith(out_prefix)
        }
    )

    headers: set[str] = set()
    uis: set[str] = set()
    qrcs: set[str] = set()

    for target in config.targets:
        for root in _target_scope_roots(repo_root, target.src_glob):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = rel_path(path, repo_root)
                suffix = path.suffix.lower()
                if suffix in {".h", ".hpp", ".hh", ".hxx"}:
                    headers.add(rel)
                elif suffix == ".ui":
                    uis.add(rel)
                elif suffix == ".qrc":
                    qrcs.add(rel)

    tracked = sorted(set(source_paths) | headers | uis | qrcs)
    qrc_refs = _qrc_referenced_files(repo_root, qrcs)
    tracked = sorted(set(tracked) | set(qrc_refs))
    files: list[dict[str, Any]] = []
    for rel in tracked:
        abs_path = (repo_root / rel).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            files.append({"path": normalize_path(rel), "missing": True})
            continue
        stat = abs_path.stat()
        files.append(
            {
                "path": normalize_path(rel),
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        )

    return {
        "schema_version": 1,
        "sources": source_paths,
        "headers": sorted(headers),
        "uis": sorted(uis),
        "qrcs": sorted(qrcs),
        "qrc_referenced": sorted(qrc_refs),
        "files": files,
    }


def _danger_env() -> dict[str, str]:
    out = {k: v for k, v in os.environ.items() if k.upper().startswith("NGK_")}
    return {k: out[k] for k in sorted(out.keys())}


def _compiler_fingerprint() -> dict[str, str]:
    resolved = _shutil.which("cl") or ""
    compiler_path = normalize_path(Path(resolved).resolve()) if resolved else ""
    compiler_hash = ""
    if resolved:
        path = Path(resolved)
        if path.exists() and path.is_file():
            try:
                compiler_hash = sha256_file(path)
            except Exception:
                compiler_hash = ""
    return {"compiler_path": compiler_path, "compiler_hash": compiler_hash}


def _qt_tool_fingerprint(config: Config) -> dict[str, Any]:
    if not config.qt.enabled:
        return {
            "qt_enabled": False,
            "moc_path": "",
            "uic_path": "",
            "rcc_path": "",
            "moc_hash": "",
            "uic_hash": "",
            "rcc_hash": "",
        }

    def _norm(value: str) -> str:
        if not value:
            return ""
        try:
            return normalize_path(Path(value).resolve())
        except Exception:
            return normalize_path(value)

    def _hash(value: str) -> str:
        if not value:
            return ""
        try:
            p = Path(value)
            if p.exists() and p.is_file():
                return sha256_file(p)
        except Exception:
            return ""
        return ""

    return {
        "qt_enabled": True,
        "moc_path": _norm(config.qt.moc_path),
        "uic_path": _norm(config.qt.uic_path),
        "rcc_path": _norm(config.qt.rcc_path),
        "moc_hash": _hash(config.qt.moc_path),
        "uic_hash": _hash(config.qt.uic_path),
        "rcc_hash": _hash(config.qt.rcc_path),
    }


def build_plan_key(
    config_path: Path,
    profile: str,
    selected_target: str,
    structural_graph_hash: str,
    config: Config,
) -> dict[str, Any]:
    config_hash = sha256_text(config_path.read_text(encoding="utf-8")) if config_path.exists() else ""
    commit = os.environ.get("NGK_COMMIT", "") or os.environ.get("GITHUB_SHA", "")

    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "ngksgraph_version": __version__,
        "ngksgraph_commit": str(commit),
        "profile": profile,
        "selected_target": selected_target,
        "config_hash": config_hash,
        "structural_graph_hash": structural_graph_hash,
        "toolchain": {
            **_compiler_fingerprint(),
            **_qt_tool_fingerprint(config),
        },
        "danger_env": _danger_env(),
    }


def json_sha(data: dict[str, Any]) -> str:
    return sha256_text(stable_json_dumps(data))


def save_cache_record(
    repo_root: Path,
    profile: str,
    plan: dict[str, Any],
    plan_key: dict[str, Any],
    fingerprint: dict[str, Any],
) -> dict[str, str]:
    paths = ensure_cache_layout(repo_root, profile)
    plan_key_sha = json_sha(plan_key)
    fingerprint_sha = json_sha(fingerprint)

    paths["plan"].write_text(stable_json_dumps(plan), encoding="utf-8")
    paths["plan_key"].write_text(stable_json_dumps(plan_key), encoding="utf-8")
    paths["plan_key_sha"].write_text(plan_key_sha + "\n", encoding="utf-8")
    paths["fingerprint"].write_text(stable_json_dumps(fingerprint), encoding="utf-8")
    paths["fingerprint_sha"].write_text(fingerprint_sha + "\n", encoding="utf-8")

    return {
        "plan_key_sha": plan_key_sha,
        "fingerprint_sha": fingerprint_sha,
    }


def read_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "corrupt"
    if not isinstance(data, dict):
        return None, "corrupt"
    return data, None


def touch_cache_hit(repo_root: Path, profile: str) -> None:
    paths = ensure_cache_layout(repo_root, profile)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    paths["last_hit"].write_text(stamp + "\n", encoding="utf-8")
