from __future__ import annotations

from pathlib import Path
from typing import Any

from .node_toolchain import detect_node_toolchain
from .probe import probe_project
from .receipts import file_sha256, is_writable_directory, write_json


def init_profile(project_path: Path, pf: Path, write_project: bool = False) -> dict[str, Any]:
    """
    Profile init contract:

    DEFAULT:
      - Write profile.json into PF (pf/profile.json)
      - Do NOT write into target project directory.

        OPT-IN:
            - If write_project=True, attempt to also write:
          <project_path>/.ngk/profile.json
        Only if the project directory is writable.

    Rationale:
      - Prevents side-effects in user target trees (especially backups)
      - Keeps profile as an execution artifact unless user explicitly opts in
    """
    project_path = project_path.resolve()
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)

    probe = probe_project(project_path, pf, run_dynamic_checks=False)
    sln_candidates = probe.get("fingerprint_map", {}).get("sln", [])

    bootstrap_candidates = probe.get("bootstrap_ritual_candidates", [])
    bootstrap_command = bootstrap_candidates[0] if bootstrap_candidates else ""

    npm_entries = probe.get("fingerprint_map", {}).get("npm", [])
    package_json_path = project_path / "package.json"
    if npm_entries:
        package_json_path = (project_path / str(npm_entries[0])).resolve()
    node_toolchain = detect_node_toolchain(project_path, package_json_path)

    node_component = "root"
    if package_json_path.parent != project_path:
        node_component = package_json_path.parent.name

    node_language = "javascript"
    if (package_json_path.parent / "tsconfig.json").is_file():
        node_language = "typescript"

    payload = {
        "version": 1,
        "detected": {
            "primary_path": probe.get("primary_path", "unknown"),
            "confidence": probe.get("confidence", {}),
        },
        "bootstrap": {
            "kind": "script" if bootstrap_command else "none",
            "command": bootstrap_command,
            "notes": "Detected from probe fingerprints",
        },
        "dialect": {
            "debug": "",
            "release": "",
            "build": "",
            "test": "",
            "package": "",
        },
        "solution": {
            "solution_candidates": sln_candidates,
        },
        "runner": {
            "default_path": probe.get("primary_path", "unknown"),
            "overrides": {},
        },
        "node_toolchain": node_toolchain,
        "contracts": {
            "node_toolchain": [
                {
                    "component": node_component,
                    "language": node_language,
                    "build_system": "node",
                    "package_manager": node_toolchain.get("selected_manager", ""),
                    "reason": node_toolchain.get("reason", ""),
                }
            ]
        },
    }

    # Always write to PF (no side-effects in target by default)
    pf_profile_path = pf / "profile.json"
    write_json(pf_profile_path, payload)

    write_mode = "pf_only"
    project_profile_path = project_path / ".ngk" / "profile.json"

    # Optional opt-in write into the project tree
    if write_project:
        if is_writable_directory(project_path):
            project_profile_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(project_profile_path, payload)
            write_mode = "pf_and_project"
        else:
            write_mode = "pf_only_project_not_writable"

    receipt = {
        "profile_path": str(pf_profile_path),
        "write_mode": write_mode,
        "sha256": file_sha256(pf_profile_path),
        "project_profile_path": str(project_profile_path),
        "write_project_requested": bool(write_project),
        "project_profile_written": (write_mode == "pf_and_project"),
    }
    write_json(pf / "profile_write_receipt.json", receipt)
    return receipt