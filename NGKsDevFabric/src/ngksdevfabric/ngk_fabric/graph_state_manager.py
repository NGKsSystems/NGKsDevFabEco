from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_GRAPH_STATE_VERSION = 1


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _state_file(project_root: Path) -> Path:
    return project_root.resolve() / ".graph_state" / "graph_state.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tracked_files(project_root: Path) -> list[Path]:
    include_suffixes = {
        ".py",
        ".ps1",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".txt",
        ".md",
        ".csproj",
        ".sln",
        ".props",
        ".targets",
        ".vcxproj",
    }
    include_names = {
        "pyproject.toml",
        "requirements.txt",
        "requirements.local.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "global.json",
        "directory.build.props",
        "directory.build.targets",
        "nuget.config",
        "env_capsule.lock.json",
        "ngksgraph.toml",
    }
    blocked_dirs = {
        ".git",
        ".ngks",
        "_proof",
        ".venv",
        "_validation_venv",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        "releases",
        "wheelhouse",
        ".graph_state",
    }

    root = project_root.resolve()
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.lower() in blocked_dirs for part in rel.parts):
            continue
        name_l = path.name.lower()
        if name_l in include_names or path.suffix.lower() in include_suffixes:
            files.append(path)

    files.sort(key=lambda p: p.as_posix().lower())
    return files


def _toolchain_fingerprint() -> dict[str, Any]:
    tools = {
        "python": sys.executable,
        "cl": shutil.which("cl") or "",
        "cmake": shutil.which("cmake") or "",
        "ninja": shutil.which("ninja") or "",
        "msbuild": shutil.which("msbuild") or "",
    }
    digest = hashlib.sha256(json.dumps(tools, sort_keys=True).encode("utf-8")).hexdigest()
    return {"tools": tools, "fingerprint": digest}


def _workspace_integrity_input(project_root: Path) -> dict[str, Any]:
    report = project_root.resolve() / "_proof" / "workspace_integrity" / "02_workspace_integrity_report.json"
    if not report.exists() or not report.is_file():
        return {"path": str(report), "exists": False, "sha256": ""}
    data = report.read_bytes()
    return {
        "path": str(report),
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def compute_project_fingerprint(
    *,
    project_root: Path,
    active_profile: str,
    active_target: str,
) -> dict[str, Any]:
    root = project_root.resolve()
    tracked = _tracked_files(root)
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()

    for path in tracked:
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        row = {
            "path": rel,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }
        rows.append(row)
        digest.update(rel.encode("utf-8"))
        digest.update(str(row["size"]).encode("utf-8"))
        digest.update(str(row["mtime_ns"]).encode("utf-8"))

    toolchain = _toolchain_fingerprint()
    integrity = _workspace_integrity_input(root)

    digest.update(active_profile.encode("utf-8"))
    digest.update(active_target.encode("utf-8"))
    digest.update(toolchain["fingerprint"].encode("utf-8"))
    digest.update(integrity["sha256"].encode("utf-8"))

    return {
        "workspace_root": str(root),
        "file_count": len(rows),
        "rows": rows,
        "active_profile": active_profile,
        "active_target": active_target,
        "toolchain_fingerprint": toolchain,
        "workspace_integrity_input": integrity,
        "project_fingerprint": digest.hexdigest(),
    }


def load_graph_state(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    state_path = _state_file(root)
    data = _read_json(state_path)
    if data:
        return data
    return {
        "workspace_root": str(root),
        "graph_state_version": _GRAPH_STATE_VERSION,
        "last_refresh_utc": "",
        "last_refresh_status": "none",
        "dirty": True,
        "dirty_reasons": ["no_successful_prior_graph_refresh"],
        "project_fingerprint": "",
        "graph_artifact_root": "",
        "active_profile": "",
        "active_target": "",
        "toolchain_fingerprint": "",
    }


def _dirty_reasons(*, previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    previous_fp = str(previous.get("project_fingerprint", "")).strip()
    current_fp = str(current.get("project_fingerprint", "")).strip()

    if str(previous.get("last_refresh_status", "none")) != "success":
        reasons.append("no_successful_prior_graph_refresh")
    if not previous_fp:
        reasons.append("no_prior_fingerprint")
    if previous_fp and current_fp and previous_fp != current_fp:
        reasons.append("source_or_config_tree_changed")

    if str(previous.get("active_profile", "")) != str(current.get("active_profile", "")):
        reasons.append("profile_changed")
    if str(previous.get("active_target", "")) != str(current.get("active_target", "")):
        reasons.append("target_changed")

    previous_tool = str(previous.get("toolchain_fingerprint", ""))
    current_tool = str(current.get("toolchain_fingerprint", ""))
    if previous_tool != current_tool:
        reasons.append("toolchain_fingerprint_changed")

    return sorted(set(reasons))


def persist_graph_state(project_root: Path, state_payload: dict[str, Any]) -> Path:
    state_path = _state_file(project_root.resolve())
    _write_json(state_path, state_payload)
    return state_path


def evaluate_graph_state(
    *,
    project_root: Path,
    active_profile: str,
    active_target: str,
    graph_artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    previous = load_graph_state(project_root)
    fingerprint = compute_project_fingerprint(
        project_root=project_root,
        active_profile=active_profile,
        active_target=active_target,
    )

    current_state = {
        "workspace_root": str(project_root.resolve()),
        "graph_state_version": _GRAPH_STATE_VERSION,
        "last_refresh_utc": str(previous.get("last_refresh_utc", "")),
        "last_refresh_status": str(previous.get("last_refresh_status", "none")),
        "dirty": True,
        "dirty_reasons": [],
        "project_fingerprint": str(fingerprint.get("project_fingerprint", "")),
        "graph_artifact_root": str(graph_artifact_root.resolve()),
        "active_profile": active_profile,
        "active_target": active_target,
        "toolchain_fingerprint": str(fingerprint.get("toolchain_fingerprint", {}).get("fingerprint", "")),
    }

    reasons = _dirty_reasons(previous=previous, current=current_state)
    current_state["dirty_reasons"] = reasons
    current_state["dirty"] = len(reasons) > 0
    return previous, fingerprint, current_state


def _write_graph_state_artifacts(
    *,
    pf: Path,
    before_state: dict[str, Any],
    fingerprint: dict[str, Any],
    dirty_reasons: list[str],
    refresh_action: dict[str, Any],
    after_state: dict[str, Any],
) -> list[str]:
    p20 = pf / "20_graph_state_before.json"
    p21 = pf / "21_graph_fingerprint_current.json"
    p22 = pf / "22_graph_dirty_reasons.json"
    p23 = pf / "23_graph_refresh_action.json"
    p24 = pf / "24_graph_state_after.json"
    p25 = pf / "25_graph_state_summary.md"

    _write_json(p20, before_state)
    _write_json(p21, fingerprint)
    _write_json(p22, {"dirty": len(dirty_reasons) > 0, "dirty_reasons": dirty_reasons})
    _write_json(p23, refresh_action)
    _write_json(p24, after_state)

    summary = [
        "# Graph State Summary",
        "",
        f"- dirty_before: {len(dirty_reasons) > 0}",
        f"- dirty_reasons: {', '.join(dirty_reasons) if dirty_reasons else 'none'}",
        f"- refresh_action: {refresh_action.get('action', '')}",
        f"- refresh_status: {refresh_action.get('status', '')}",
        f"- buildcore_allowed: {refresh_action.get('buildcore_allowed', False)}",
        f"- state_dirty_after: {after_state.get('dirty', True)}",
        "",
    ]
    _write_text(p25, "\n".join(summary))

    return [
        p20.name,
        p21.name,
        p22.name,
        p23.name,
        p24.name,
        p25.name,
    ]


def ensure_graph_state_fresh(
    *,
    project_root: Path,
    pf: Path,
    active_profile: str,
    active_target: str,
    graph_artifact_root: Path,
    refresh_callback: Callable[[], tuple[bool, str]],
) -> dict[str, Any]:
    before_state, fingerprint, candidate_state = evaluate_graph_state(
        project_root=project_root,
        active_profile=active_profile,
        active_target=active_target,
        graph_artifact_root=graph_artifact_root,
    )

    dirty_reasons = list(candidate_state.get("dirty_reasons", []))
    refresh_action = {
        "action": "none",
        "status": "skipped_clean",
        "reason": "graph_state_clean",
        "buildcore_allowed": True,
    }

    after_state = dict(candidate_state)
    if bool(candidate_state.get("dirty", True)):
        refresh_action = {
            "action": "auto_refresh",
            "status": "attempted",
            "reason": "dirty_graph_state",
            "buildcore_allowed": False,
        }
        if os.environ.get("NGKS_FORCE_GRAPH_REFRESH_FAILURE", "").strip() == "1":
            ok, message = False, "forced_graph_refresh_failure"
        else:
            ok, message = refresh_callback()

        if ok:
            after_state["last_refresh_utc"] = _iso_now()
            after_state["last_refresh_status"] = "success"
            after_state["dirty"] = False
            after_state["dirty_reasons"] = []
            refresh_action["status"] = "success"
            refresh_action["reason"] = str(message)
            refresh_action["buildcore_allowed"] = True
        else:
            after_state["last_refresh_utc"] = _iso_now()
            after_state["last_refresh_status"] = "failed"
            after_state["dirty"] = True
            after_state["dirty_reasons"] = sorted(set(dirty_reasons + ["refresh_failed"]))
            refresh_action["status"] = "failed"
            refresh_action["reason"] = str(message)
            refresh_action["buildcore_allowed"] = False

    state_path = persist_graph_state(project_root, after_state)
    artifact_names = _write_graph_state_artifacts(
        pf=pf.resolve(),
        before_state=before_state,
        fingerprint=fingerprint,
        dirty_reasons=dirty_reasons,
        refresh_action=refresh_action,
        after_state=after_state,
    )

    return {
        "ok": bool(refresh_action.get("buildcore_allowed", False)),
        "dirty_before": len(dirty_reasons) > 0,
        "dirty_reasons": dirty_reasons,
        "refresh_action": refresh_action,
        "state_path": str(state_path),
        "after_state": after_state,
        "artifact_names": artifact_names,
    }


def mark_graph_state_dirty_if_changed(
    *,
    project_root: Path,
    active_profile: str,
    active_target: str,
    graph_artifact_root: Path,
) -> dict[str, Any]:
    before_state, _fingerprint, candidate_state = evaluate_graph_state(
        project_root=project_root,
        active_profile=active_profile,
        active_target=active_target,
        graph_artifact_root=graph_artifact_root,
    )

    if bool(candidate_state.get("dirty", True)):
        previous_status = str(before_state.get("last_refresh_status", "none"))
        candidate_state["last_refresh_status"] = previous_status if previous_status else "none"
        persist_graph_state(project_root, candidate_state)

    return {
        "dirty": bool(candidate_state.get("dirty", True)),
        "dirty_reasons": list(candidate_state.get("dirty_reasons", [])),
    }
