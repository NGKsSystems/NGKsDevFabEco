from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ngksgraph.config import Config
from ngksgraph.graph import BuildGraph
from ngksgraph.hashutil import sha256_text
from ngksgraph.util import normalize_path


def load_compdb(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("compile_commands.json must contain a list")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("compile_commands.json entries must be objects")
        out.append(dict(item))
    return out


def _norm_for_hash(entry: dict[str, Any]) -> dict[str, Any]:
    data = dict(entry)
    for key in ["file", "directory", "output"]:
        if key in data and isinstance(data[key], str):
            data[key] = normalize_path(data[key])
    return data


def normalize_for_hash(entries: list[dict[str, Any]]) -> str:
    cooked = [_norm_for_hash(v) for v in entries]

    def _key(item: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(item.get("file", "")),
            str(item.get("directory", "")),
            str(item.get("output", "")),
        )

    cooked = sorted(cooked, key=_key)
    return json.dumps(cooked, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compdb_hash(entries: list[dict[str, Any]]) -> str:
    return sha256_text(normalize_for_hash(entries))


def _path_to_rel(file_path: str, repo_root: Path) -> str | None:
    p = Path(file_path)
    try:
        rel = p.resolve().relative_to(repo_root.resolve())
    except Exception:
        return None
    return normalize_path(rel)


def _extract_include_flags(command: str) -> list[str]:
    values: list[str] = []
    for m in re.finditer(r'(?:^|\s)(?:/I|-I)(?:"([^"]+)"|(\S+))', command):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        if raw:
            values.append(normalize_path(raw))
    return values


def _extract_define_flags(command: str) -> list[str]:
    values: list[str] = []
    for m in re.finditer(r'(?:^|\s)/D(?:"([^"]+)"|(\S+))', command):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        if raw:
            values.append(str(raw))
    return values


def _quote_violations(command: str, target_include_dirs: list[str], source_rel: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    if "\x00" in command or "\n" in command or "\r" in command:
        out.append(
            {
                "code": "BAD_QUOTING",
                "detail": "command contains control characters (newline/CR/NUL)",
                "hint": "emit single-line compile commands without embedded control characters",
            }
        )

    if command.count('"') % 2 != 0:
        out.append(
            {
                "code": "BAD_QUOTING",
                "detail": "command contains unmatched quotes",
                "hint": "quote each spaced path with balanced double quotes",
            }
        )

    for inc in target_include_dirs:
        norm_inc = normalize_path(inc)
        if " " in norm_inc:
            quoted = f'/I"{norm_inc}"'
            if quoted not in command:
                out.append(
                    {
                        "code": "BAD_QUOTING",
                        "detail": f"include path with spaces is not quoted: {norm_inc}",
                        "hint": "use /I\"path with spaces\"",
                    }
                )

    if source_rel and " " in source_rel:
        quoted_src = f'"{normalize_path(source_rel)}"'
        if quoted_src not in command:
            out.append(
                {
                    "code": "BAD_QUOTING",
                    "detail": f"source path with spaces is not quoted: {source_rel}",
                    "hint": "quote the /c source argument when path contains spaces",
                }
            )

    if re.search(r'(?:^|\s)(?:/I|-I)\s+[^"\s][^\n\r]*\s[^"\s]+', command):
        out.append(
            {
                "code": "BAD_QUOTING",
                "detail": "detected spaced include argument without quotes after /I or -I",
                "hint": "do not split include paths with spaces across tokens",
            }
        )

    return out


def validate_compdb(entries: list[dict[str, Any]], graph: BuildGraph, config: Config) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if not entries:
        return [
            {
                "code": "MISSING_ENTRY",
                "detail": "compile_commands.json is empty",
                "hint": "run configure to generate compile_commands.json",
            }
        ]

    directories = [str(v.get("directory", "")) for v in entries if str(v.get("directory", ""))]
    if not directories:
        return [
            {
                "code": "MISSING_ENTRY",
                "detail": "compile_commands.json entries have no directory",
                "hint": "ensure compdb writer fills directory for each entry",
            }
        ]

    repo_root = Path(sorted(directories)[0])

    source_owner: dict[str, str] = {}
    expected_sources: set[str] = set()
    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        for src in target.sources:
            rel = normalize_path(src)
            expected_sources.add(rel)
            source_owner[rel] = target_name

    seen_count: dict[str, int] = {}

    for entry in entries:
        file_path = str(entry.get("file", ""))
        command = str(entry.get("command", ""))
        source_rel = _path_to_rel(file_path, repo_root)

        if source_rel is None:
            violations.append(
                {
                    "code": "EXTRA_ENTRY",
                    "detail": f"entry file is outside repo root: {file_path}",
                    "file": file_path,
                    "hint": "ensure compile_commands only contains project translation units",
                }
            )
            continue

        seen_count[source_rel] = seen_count.get(source_rel, 0) + 1

        if source_rel not in expected_sources:
            violations.append(
                {
                    "code": "EXTRA_ENTRY",
                    "detail": f"unexpected translation unit in compdb: {source_rel}",
                    "file": source_rel,
                    "hint": "ensure compile_commands is generated from graph target sources only",
                }
            )
            continue

        target_name = source_owner[source_rel]
        target = graph.targets[target_name]

        include_flags = set(_extract_include_flags(command))
        for req in target.include_dirs:
            req_norm = normalize_path(req)
            if req_norm not in include_flags:
                code = "MISSING_GENERATED_INCLUDE" if req_norm.endswith("build/qt") else "MISSING_INCLUDE"
                violations.append(
                    {
                        "code": code,
                        "detail": f"missing include dir for {target_name}: {req_norm}",
                        "file": source_rel,
                        "hint": "ensure target include_dirs are fully propagated to compile command entries",
                    }
                )

        define_flags = set(_extract_define_flags(command))
        for define in target.defines:
            if define not in define_flags:
                violations.append(
                    {
                        "code": "MISSING_DEFINE",
                        "detail": f"missing define for {target_name}: {define}",
                        "file": source_rel,
                        "hint": "ensure target defines are propagated to each compile command",
                    }
                )

        std_flag = f"/std:c++{target.cxx_std}"
        if std_flag not in command:
            violations.append(
                {
                    "code": "MISSING_STD_FLAG",
                    "detail": f"missing language standard flag for {target_name}: {std_flag}",
                    "file": source_rel,
                    "hint": "ensure compile command emits configured C++ standard flag",
                }
            )

        violations.extend(_quote_violations(command, target.include_dirs, source_rel))

    for src in sorted(expected_sources):
        count = seen_count.get(src, 0)
        if count == 0:
            violations.append(
                {
                    "code": "MISSING_ENTRY",
                    "detail": f"missing translation unit entry: {src}",
                    "file": src,
                    "hint": "ensure all graph translation units are present in compile_commands.json",
                }
            )
        elif count > 1:
            violations.append(
                {
                    "code": "EXTRA_ENTRY",
                    "detail": f"duplicate translation unit entry ({count}x): {src}",
                    "file": src,
                    "hint": "ensure each translation unit appears exactly once in compile_commands.json",
                }
            )

    return violations
