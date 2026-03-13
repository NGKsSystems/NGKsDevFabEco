from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_repo_local_package_json(project_root: Path, package_json_path: Path | None) -> Path:
    root = project_root.resolve()
    if package_json_path is not None:
        candidate = package_json_path.resolve()
        try:
            candidate.relative_to(root)
        except Exception:
            candidate = root / "package.json"
        if candidate.is_file() and candidate.name == "package.json":
            return candidate
    return root / "package.json"


def _load_repo_node_policy(project_root: Path) -> tuple[list[str], str | None]:
    default_policy = ["pnpm", "npm"]
    valid = {"pnpm", "npm", "yarn"}
    policy = default_policy
    explicit_manager: str | None = None

    profile = _load_json_file(project_root / ".ngk" / "profile.json") or {}
    local_policy = _load_json_file(project_root / ".ngk" / "node_toolchain.json") or {}
    merged = {**profile, **local_policy}

    node_cfg = merged.get("node") if isinstance(merged.get("node"), dict) else {}
    if isinstance(node_cfg, dict):
        candidate = node_cfg.get("policy_preference")
        if isinstance(candidate, list):
            cleaned = [str(item).strip().lower() for item in candidate if str(item).strip().lower() in valid]
            if cleaned:
                policy = cleaned

        explicit = str(node_cfg.get("package_manager", "")).strip().lower()
        if explicit in valid:
            explicit_manager = explicit

    return policy, explicit_manager


def detect_node_toolchain(project_root: Path, package_json_path: Path | None) -> dict[str, Any]:
    root = project_root.resolve()
    package_json = _resolve_repo_local_package_json(root, package_json_path)
    node_root = package_json.parent

    evidence_found = {
        "package_json": package_json.is_file(),
        "pnpm_lock": (node_root / "pnpm-lock.yaml").is_file(),
        "npm_lock": (node_root / "package-lock.json").is_file(),
        "yarn_lock": (node_root / "yarn.lock").is_file(),
        "npmrc": (node_root / ".npmrc").is_file(),
        "pnpmfile": (node_root / ".pnpmfile.cjs").is_file(),
        "ngk_profile": (root / ".ngk" / "profile.json").is_file(),
    }

    policy_preference, explicit_manager = _load_repo_node_policy(root)

    selected = ""
    reason = ""
    if evidence_found["pnpm_lock"]:
        selected = "pnpm"
        reason = "lockfile_detected"
    elif evidence_found["npm_lock"]:
        selected = "npm"
        reason = "lockfile_detected"
    elif evidence_found["yarn_lock"]:
        selected = "yarn"
        reason = "lockfile_detected"
    elif explicit_manager:
        selected = explicit_manager
        reason = "repo_configured"
    else:
        selected = policy_preference[0] if policy_preference else "pnpm"
        reason = "policy_default_no_lockfile"

    selected_available = bool(shutil.which(selected)) if selected else False
    fallback_used = False
    if selected and not selected_available:
        for candidate in policy_preference:
            if candidate == selected:
                continue
            if shutil.which(candidate):
                selected = candidate
                selected_available = True
                fallback_used = True
                break
        if fallback_used:
            reason = "fallback_tool_unavailable"

    node_runtime_available = bool(shutil.which("node"))

    return {
        "repo_root": str(root),
        "package_json_path": str(package_json),
        "node_project_root": str(node_root),
        "evidence_found": evidence_found,
        "policy_preference": policy_preference,
        "selected_manager": selected,
        "selected_manager_available": selected_available,
        "node_runtime_available": node_runtime_available,
        "reason": reason,
        "repo_boundary_enforced": True,
        "scan_scope": "repo_root_only",
    }
