from __future__ import annotations

import os
from pathlib import Path

from ngksgraph.env.compiler_contracts import compiler_family
from ngksgraph.env.runtime_contracts import has_qt_runtime


def _has_vcvars() -> bool:
    return bool(os.environ.get("VCINSTALLDIR") or os.environ.get("VSCMD_ARG_TGT_ARCH") or os.environ.get("VSINSTALLDIR"))


def _qt_on_path() -> bool:
    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    return any("qt" in entry.lower() for entry in path_entries)


def _has_project_venv(repo_root: Path) -> bool:
    if os.name == "nt":
        return (repo_root / ".venv" / "Scripts" / "python.exe").exists()
    return (repo_root / ".venv" / "bin" / "python").exists()


def build_env_contract(
    repo_root: Path,
    requirements: list[dict[str, object]],
    tool_lookup: dict[str, str | None],
    *,
    msvc_env_active_override: bool = False,
) -> dict[str, object]:
    required_tools = sorted({tool for req in requirements for tool in req.get("required_tools", [])})
    missing_tools: list[str] = []
    required_env = sorted({env for req in requirements for env in req.get("required_env", [])})
    missing_env: list[str] = []
    msvc_required = any(tool in {"cl.exe", "link.exe", "lib.exe"} for tool in required_tools)
    msvc_satisfied = bool(tool_lookup.get("cxx")) or bool(
        tool_lookup.get("cl.exe") and tool_lookup.get("link.exe") and tool_lookup.get("lib.exe")
    )

    for tool in required_tools:
        if tool in {"cl.exe", "link.exe", "lib.exe"}:
            if msvc_required and not msvc_satisfied and "cxx" not in missing_tools:
                missing_tools.append("cxx")
            continue
        if tool == "qt":
            if not has_qt_runtime():
                missing_tools.append("qt")
            continue
        if not tool_lookup.get(tool):
            missing_tools.append(tool)

    for env_requirement in required_env:
        normalized = env_requirement.strip().lower()
        if normalized == "vcvars active" and not (_has_vcvars() or msvc_env_active_override) and msvc_required:
            missing_env.append("vcvars active")
        elif normalized in {"qt bin on path", "path contains qt bin"} and not _qt_on_path() and not has_qt_runtime():
            missing_env.append("Qt bin on PATH")
        elif normalized == "project venv present" and not _has_project_venv(repo_root):
            missing_env.append("project venv present")

    required_flags = sorted({flag for req in requirements for flag in req.get("required_flags", {}).get("msvc", [])})
    cfamily = compiler_family()
    status = "pass"
    if missing_tools:
        status = "fail"
    elif missing_env:
        status = "warn"

    return {
        "repo_root": str(repo_root),
        "subprojects": [
            {
                "subproject_id": "root",
                "compiler_family": cfamily,
                "compiler_min_version": "19.x" if cfamily == "msvc" else "",
                "language_standard": "c++17" if any(req["requirement_id"] in {"qt6_msvc_cpp17", "juce_cpp17"} for req in requirements) else "",
                "required_tools": required_tools,
                "required_env": required_env,
                "required_flags": required_flags,
                "missing": missing_tools,
                "missing_env": missing_env,
                "status": status,
            }
        ],
    }
