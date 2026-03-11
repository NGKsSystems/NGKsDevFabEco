from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .receipts import run_command_capture, utc_now_iso, write_json
from .resolver import resolve_tools


PRIMARY_ORDER = ["flutter", "graph", "meson", "npm", "python"]


PATTERN_MAP: dict[str, tuple[str, bool]] = {
    "meson.build": ("meson", False),
    "package.json": ("npm", False),
    "pubspec.yaml": ("flutter_pubspec", False),
    "pyproject.toml": ("python_pyproject", False),
    "requirements.txt": ("python_requirements", False),
    "enter_msvc_env.ps1": ("bootstrap_enter_msvc_ps1", False),
    "build.ps1": ("bootstrap_build_ps1", False),
    "msvc_x64.cmd": ("bootstrap_msvc_cmd", False),
    "scripts": ("scripts_folder", True),
    "build": ("build_dirs_build", True),
    "out": ("build_dirs_out", True),
    ".vs": ("build_dirs_vs", True),
}


def _empty_fingerprints() -> dict[str, list[str]]:
    keys = [
        "flutter_pubspec",
        "dart_sources",
        "sln",
        "vcxproj",
        "meson",
        "npm",
        "python_pyproject",
        "python_requirements",
        "bootstrap_msvc_cmd",
        "bootstrap_enter_msvc_ps1",
        "bootstrap_build_ps1",
        "scripts_folder",
        "build_dirs_build",
        "build_dirs_out",
        "build_dirs_vs",
        "csproj",
    ]
    return {key: [] for key in keys}


def _build_fingerprints(project_path: Path, max_depth: int = 6, max_files: int = 5000) -> tuple[dict[str, list[str]], dict[str, Any]]:
    started = time.perf_counter()
    found: dict[str, set[str]] = defaultdict(set)
    scanned_files_count = 0
    stop_reason = "completed"
    confidence_hint = 0

    root_parts = len(project_path.parts)
    for dirpath, dirnames, filenames in project_path.walk(top_down=True):
        current = Path(dirpath)
        depth = len(current.parts) - root_parts
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [name for name in dirnames if name not in {".git", "node_modules", ".venv", "__pycache__"}]

        for dirname in list(dirnames):
            key_entry = PATTERN_MAP.get(dirname)
            if key_entry and key_entry[1]:
                key = key_entry[0]
                rel = str((current / dirname).relative_to(project_path)).replace("\\", "/")
                found[key].add(rel)

        for filename in filenames:
            scanned_files_count += 1
            if scanned_files_count >= max_files:
                stop_reason = f"max_files:{max_files}"
                break

            key_entry = PATTERN_MAP.get(filename)
            if key_entry and not key_entry[1]:
                key = key_entry[0]
                rel = str((current / filename).relative_to(project_path)).replace("\\", "/")
                found[key].add(rel)

            lower = filename.lower()
            if lower.endswith(".sln"):
                found["sln"].add(str((current / filename).relative_to(project_path)).replace("\\", "/"))
            elif lower.endswith(".vcxproj"):
                found["vcxproj"].add(str((current / filename).relative_to(project_path)).replace("\\", "/"))
            elif lower.endswith(".csproj"):
                found["csproj"].add(str((current / filename).relative_to(project_path)).replace("\\", "/"))
            elif lower.endswith(".dart"):
                found["dart_sources"].add(str((current / filename).relative_to(project_path)).replace("\\", "/"))

        f = _empty_fingerprints()
        for key, entries in found.items():
            if key in f:
                f[key] = sorted(entries)
        _, _, confidence_hint, _ = _classify(f)
        if confidence_hint >= 90:
            stop_reason = f"confidence:{confidence_hint}"
            break
        if scanned_files_count >= max_files:
            break

    fingerprint_map = _empty_fingerprints()
    for key, entries in found.items():
        if key in fingerprint_map:
            fingerprint_map[key] = sorted(entries)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    stats = {
        "scanned_files_count": scanned_files_count,
        "elapsed_ms": elapsed_ms,
        "stop_reason": stop_reason,
        "max_depth": max_depth,
        "max_files": max_files,
    }
    return fingerprint_map, stats


def _classify(f: dict[str, list[str]]) -> tuple[str, list[str], int, list[str]]:
    def _is_generated_path(rel_path: str) -> bool:
        normalized = rel_path.replace("\\", "/").lower()
        generated_prefixes = (
            "build/",
            "out/",
            "dist/",
            "target/",
            ".dart_tool/",
            "cmake-build/",
            "cmake-build-",
        )
        return normalized.startswith(generated_prefixes)

    def _non_generated(paths: list[str]) -> list[str]:
        return [path for path in paths if not _is_generated_path(path)]

    signals: list[str] = []
    primary = "unknown"
    non_generated_graph_signals = _non_generated(f["sln"]) + _non_generated(f["csproj"])
    has_generated_only_graph_signals = bool((f["sln"] or f["csproj"]) and not non_generated_graph_signals)
    flutter_detected = bool(f["flutter_pubspec"])
    dart_detected = bool(f["dart_sources"])

    if flutter_detected:
        primary = "flutter"
        signals.append("pubspec.yaml found")
        if dart_detected:
            signals.append("Dart sources found")
    elif non_generated_graph_signals:
        primary = "graph"
        signals.append("Solution/project files found")
    elif has_generated_only_graph_signals:
        primary = "graph"
        signals.append("Generated solution/project artifacts found")
    elif f["meson"]:
        primary = "meson"
        signals.append("meson.build found")
    elif f["npm"]:
        primary = "npm"
        signals.append("package.json found")
    elif f["python_pyproject"] or f["python_requirements"]:
        primary = "python"
        signals.append("Python project files found")

    secondary: list[str] = []
    for candidate in PRIMARY_ORDER:
        if candidate == primary:
            continue
        if candidate == "flutter" and flutter_detected:
            secondary.append(candidate)
        elif candidate == "graph" and (f["sln"] or f["csproj"]):
            secondary.append(candidate)
        elif candidate == "meson" and f["meson"]:
            secondary.append(candidate)
        elif candidate == "npm" and f["npm"]:
            secondary.append(candidate)
        elif candidate == "python" and (f["python_pyproject"] or f["python_requirements"]):
            secondary.append(candidate)

    confidence = 20
    if primary == "flutter":
        confidence = 90 if dart_detected else 85
    elif primary == "graph":
        confidence = 70 if has_generated_only_graph_signals else 90
    elif primary in {"meson", "npm", "python"}:
        confidence = 75
    if len(secondary) > 0:
        confidence = max(0, confidence - min(20, len(secondary) * 5))
        signals.append("Multiple build ecosystems detected")

    return primary, secondary, confidence, signals


def _recommended_commands(primary: str, f: dict[str, list[str]]) -> list[str]:
    commands: list[str] = []
    if primary == "flutter":
        commands.append("flutter doctor -v")
        commands.append("dart --version")
    elif primary == "graph":
        commands.append("dotnet --version")
    elif primary == "meson":
        commands.append("meson --version")
    elif primary == "npm":
        commands.append("npm --version")
    elif primary == "python":
        commands.append("python --version")

    if f["bootstrap_msvc_cmd"]:
        commands.append("cmd.exe /c tools\\msvc_x64.cmd")
    if f["bootstrap_enter_msvc_ps1"]:
        commands.append("powershell -NoProfile -ExecutionPolicy Bypass -File enter_msvc_env.ps1")

    return commands


def _bootstrap_candidates(f: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    for key in ["bootstrap_msvc_cmd", "bootstrap_enter_msvc_ps1", "bootstrap_build_ps1"]:
        for item in f.get(key, []):
            candidates.append(item)
    return candidates


def _flatten_fingerprints(f: dict[str, list[str]]) -> list[str]:
    values: list[str] = []
    for key, items in f.items():
        if items:
            values.append(key)
            values.extend(items)
    return values


def probe_project(project_path: Path, pf: Path, run_dynamic_checks: bool = True) -> dict[str, Any]:
    project_path = project_path.resolve()
    pf.mkdir(parents=True, exist_ok=True)

    tool_resolve = resolve_tools(pf)
    fingerprint_map, scan_stats = _build_fingerprints(project_path, max_depth=6, max_files=5000)
    write_json(pf / "probe_scan_stats.json", scan_stats)
    primary, secondary, confidence, reasons = _classify(fingerprint_map)

    tool_notes: list[str] = []
    if run_dynamic_checks and primary == "unknown":
        tool_notes.append("No known build path detected")

    report: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "project_path": str(project_path),
        "fingerprints_found": _flatten_fingerprints(fingerprint_map),
        "fingerprint_map": fingerprint_map,
        "primary_path": primary,
        "secondary_paths": secondary,
        "confidence": {"score": confidence, "reasons": reasons},
        "recommended_commands": _recommended_commands(primary, fingerprint_map),
        "bootstrap_ritual_candidates": _bootstrap_candidates(fingerprint_map),
        "tool_resolve": tool_resolve,
        "notes": tool_notes,
    }

    write_json(pf / "probe_report.json", report)
    return report
