from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_WORKSPACE_ROOT = Path("C:/Users/suppo/Desktop/NGKsSystems").resolve()
_MODULES = ("ngksdevfabric", "ngksgraph", "ngksbuildcore")


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    workspace_root: str
    python_executable: str
    module_resolution: dict[str, str]
    violations: list[str]


def _resolve_module_file(module_name: str) -> str:
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", "") or ""
    return str(Path(module_file).resolve()) if module_file else ""


def _is_under_workspace(path_str: str) -> bool:
    if not path_str:
        return False
    try:
        path = Path(path_str).resolve()
        path.relative_to(_WORKSPACE_ROOT)
        return True
    except Exception:
        return False


def _collect_module_resolution() -> dict[str, str]:
    resolved: dict[str, str] = {}
    for module_name in _MODULES:
        try:
            resolved[module_name] = _resolve_module_file(module_name)
        except Exception as exc:
            resolved[module_name] = f"IMPORT_ERROR: {exc}"
    return resolved


def _apply_simulated_bad_resolution(module_resolution: dict[str, str]) -> None:
    forced_module = os.environ.get("NGKS_INTEGRITY_FORCE_BAD_MODULE", "").strip().lower()
    if not forced_module:
        return
    if forced_module in module_resolution:
        module_resolution[forced_module] = "C:/stale/site-packages/simulated_bad_resolution.py"


def _build_result() -> IntegrityResult:
    module_resolution = _collect_module_resolution()
    _apply_simulated_bad_resolution(module_resolution)

    violations: list[str] = []
    for module_name, module_file in module_resolution.items():
        if module_file.startswith("IMPORT_ERROR:"):
            violations.append(f"{module_name}: {module_file}")
            continue
        if not _is_under_workspace(module_file):
            violations.append(
                f"{module_name}: resolves outside workspace root ({module_file})"
            )

    return IntegrityResult(
        ok=(len(violations) == 0),
        workspace_root=str(_WORKSPACE_ROOT),
        python_executable=str(Path(sys.executable).resolve()),
        module_resolution=module_resolution,
        violations=violations,
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_integrity_artifacts(artifact_dir: Path, result: IntegrityResult, scope: str) -> list[str]:
    artifact_dir = artifact_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    python_path = artifact_dir / "00_python_executable.txt"
    module_resolution_path = artifact_dir / "01_module_resolution.json"
    report_path = artifact_dir / "02_workspace_integrity_report.json"
    summary_path = artifact_dir / "03_workspace_integrity_summary.md"

    _write_text(python_path, result.python_executable + "\n")
    _write_json(
        module_resolution_path,
        {
            "workspace_root": result.workspace_root,
            "python_executable": result.python_executable,
            "module_resolution": result.module_resolution,
        },
    )
    _write_json(
        report_path,
        {
            "status": "PASS" if result.ok else "FAIL",
            "scope": scope,
            "workspace_root": result.workspace_root,
            "python_executable": result.python_executable,
            "module_resolution": result.module_resolution,
            "violations": result.violations,
        },
    )

    summary_lines = [
        "# Workspace Integrity Summary",
        "",
        f"- scope: {scope}",
        f"- status: {'PASS' if result.ok else 'FAIL'}",
        f"- workspace_root: {result.workspace_root}",
        f"- python_executable: {result.python_executable}",
    ]
    if result.violations:
        summary_lines.append("- violations:")
        for violation in result.violations:
            summary_lines.append(f"  - {violation}")
    else:
        summary_lines.append("- violations: none")
    summary_lines.append("")
    _write_text(summary_path, "\n".join(summary_lines))

    return [
        str(python_path),
        str(module_resolution_path),
        str(report_path),
        str(summary_path),
    ]


def run_workspace_integrity_check(*, scope: str, artifact_dir: Path | None = None) -> tuple[IntegrityResult, list[str]]:
    result = _build_result()
    artifact_paths: list[str] = []
    if artifact_dir is not None:
        artifact_paths = write_integrity_artifacts(artifact_dir, result, scope)
    return result, artifact_paths
