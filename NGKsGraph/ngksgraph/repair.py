from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from ngksgraph.config import Config, TargetConfig
from ngksgraph.graph import build_graph_from_project
from ngksgraph.util import normalize_path, rel_path

ALLOWED_CONFIG_ADD_FIELDS = {"include_dirs", "libs", "lib_dirs", "defines", "cflags", "ldflags"}
ALLOWED_TARGET_SET_FIELDS = {"include_dirs", "defines", "cflags", "libs", "lib_dirs", "ldflags", "links", "src_glob", "cxx_std"}
SYMBOL_LIB_MAP = {
    "messagebox": "user32",
    "gdi": "gdi32",
    "winsock": "ws2_32",
    "shell": "shell32",
}


def parse_errors(log_text: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for line in log_text.splitlines():
        c1083 = re.search(r"C1083: Cannot open include file: '([^']+)'", line, flags=re.IGNORECASE)
        if c1083:
            errors.append({"type": "C1083", "header": c1083.group(1), "line": line.strip()})
            continue

        lnk1104 = re.search(r"LNK1104: cannot open file '([^']+)'", line, flags=re.IGNORECASE)
        if lnk1104:
            errors.append({"type": "LNK1104", "lib": lnk1104.group(1), "line": line.strip()})
            continue

        if "LNK2019" in line.upper():
            errors.append({"type": "LNK2019", "line": line.strip()})
    return errors


def _search_file_by_name(repo_root: Path, filename: str, exclude_dir: str) -> list[Path]:
    exclude_norm = normalize_path((repo_root / exclude_dir).resolve())
    matches: list[Path] = []
    for found in repo_root.rglob(filename):
        if not found.is_file():
            continue
        parent_norm = normalize_path(found.resolve())
        if parent_norm.startswith(exclude_norm):
            continue
        matches.append(found)
    return sorted(matches, key=lambda p: normalize_path(p.resolve()))


def _target_for_action(config: Config, target_name: str | None) -> TargetConfig:
    if target_name:
        return config.get_target(target_name)
    return config.targets[0]


def _validate_graph_integrity(config: Config) -> None:
    source_map = {target.name: [] for target in config.targets}
    build_graph_from_project(config, source_map=source_map, msvc_auto=False)


def _apply_with_rollback(config: Config, fn) -> bool:
    backup = copy.deepcopy(config)
    try:
        fn(config)
        config.normalize()
        _validate_graph_integrity(config)
        return True
    except Exception:
        config.__dict__.clear()
        config.__dict__.update(copy.deepcopy(backup.__dict__))
        return False


def apply_action(config: Config, action: dict[str, Any], target_name: str | None = None) -> bool:
    return apply_ai_action(config, action, target_name=target_name)


def apply_ai_action(config: Config, action: dict[str, Any], target_name: str | None = None) -> bool:
    op = str(action.get("op", "")).strip()

    if op == "config.add":
        field = str(action.get("field", "")).strip()
        value = str(action.get("value", "")).strip()
        if field not in ALLOWED_CONFIG_ADD_FIELDS or not value:
            return False

        target = _target_for_action(config, target_name)
        current = getattr(target, field)
        if field == "libs" and value.lower().endswith(".lib"):
            value = value[:-4]
        if value in current:
            return False

        def mutate(c: Config) -> None:
            t = _target_for_action(c, target_name)
            getattr(t, field).append(value)

        return _apply_with_rollback(config, mutate)

    if op == "target.add":
        payload = action.get("target")
        if not isinstance(payload, dict):
            return False
        name = str(payload.get("name", "")).strip()
        ttype = str(payload.get("type", "staticlib")).strip()
        if not name or ttype not in {"staticlib", "exe"}:
            return False

        if any(t.name == name for t in config.targets):
            return False

        def mutate(c: Config) -> None:
            c.targets.append(
                TargetConfig(
                    name=name,
                    type=ttype,
                    src_glob=[str(v) for v in payload.get("src_glob", [])],
                    include_dirs=[str(v) for v in payload.get("include_dirs", [])],
                    defines=[str(v) for v in payload.get("defines", [])],
                    cflags=[str(v) for v in payload.get("cflags", [])],
                    libs=[str(v) for v in payload.get("libs", [])],
                    lib_dirs=[str(v) for v in payload.get("lib_dirs", [])],
                    ldflags=[str(v) for v in payload.get("ldflags", [])],
                    cxx_std=int(payload.get("cxx_std", c.cxx_std)),
                    links=[str(v) for v in payload.get("links", [])],
                )
            )

        return _apply_with_rollback(config, mutate)

    if op == "target.link_add":
        target = str(action.get("target", "")).strip()
        value = str(action.get("value", "")).strip()
        if not target or not value:
            return False

        def mutate(c: Config) -> None:
            t = c.get_target(target)
            if value not in t.links:
                t.links.append(value)

        return _apply_with_rollback(config, mutate)

    if op == "target.set_field":
        target = str(action.get("target", "")).strip()
        field = str(action.get("field", "")).strip()
        value = action.get("value")
        if not target or field not in ALLOWED_TARGET_SET_FIELDS:
            return False

        def mutate(c: Config) -> None:
            t = c.get_target(target)
            if field == "cxx_std":
                setattr(t, field, int(value))
            else:
                if not isinstance(value, list):
                    raise ValueError("target.set_field list field requires list value")
                setattr(t, field, [str(v) for v in value])

        return _apply_with_rollback(config, mutate)

    return False


def deterministic_fix(
    config: Config,
    errors: list[dict[str, str]],
    repo_root: Path,
    target_name: str | None = None,
) -> dict[str, Any] | None:
    for err in errors:
        if err["type"] == "C1083":
            header = err.get("header", "")
            header_name = Path(header).name
            if not header_name:
                continue
            matches = _search_file_by_name(repo_root, header_name, config.out_dir)
            if matches:
                candidate = rel_path(matches[0].parent, repo_root)
                action = {"op": "config.add", "field": "include_dirs", "value": candidate}
                if apply_ai_action(config, action, target_name=target_name):
                    return {
                        "source": "deterministic",
                        "reason": "Resolved missing include directory from C1083",
                        "action": action,
                    }

        if err["type"] == "LNK1104":
            lib_name = Path(err.get("lib", "")).name
            if not lib_name:
                continue
            matches = _search_file_by_name(repo_root, lib_name, config.out_dir)
            if matches:
                candidate = rel_path(matches[0].parent, repo_root)
                action = {"op": "config.add", "field": "lib_dirs", "value": candidate}
                if apply_ai_action(config, action, target_name=target_name):
                    return {
                        "source": "deterministic",
                        "reason": "Resolved missing library directory from LNK1104",
                        "action": action,
                    }

        if err["type"] == "LNK2019":
            line = err.get("line", "")
            lower = line.lower()
            for token, lib in SYMBOL_LIB_MAP.items():
                if token in lower:
                    action = {"op": "config.add", "field": "libs", "value": lib}
                    if apply_ai_action(config, action, target_name=target_name):
                        return {
                            "source": "deterministic",
                            "reason": f"Mapped unresolved external to library '{lib}'",
                            "action": action,
                        }
    return None


def sanitize_for_ai(
    repo_root: Path,
    config: Config,
    errors: list[dict[str, str]],
    log_tail: str,
    attempt: int,
) -> dict[str, Any]:
    return {
        "repo_root": "<redacted_path>",
        "config": config.as_sanitized_dict(),
        "errors": errors,
        "log_tail": log_tail,
        "attempt": attempt,
    }


def validate_ai_actions(actions: list[dict[str, Any]], max_actions: int, config: Config | None = None) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    pending_targets: set[str] = set()

    existing_targets = set(t.name for t in config.targets) if config else set()

    for raw in actions[:max_actions]:
        op = str(raw.get("op", "")).strip()

        if op == "config.add":
            field = str(raw.get("field", "")).strip()
            value = str(raw.get("value", "")).strip()
            if field not in ALLOWED_CONFIG_ADD_FIELDS or not value:
                continue
            key = f"{op}:{field}:{value.lower()}"
            if key in seen:
                continue
            seen.add(key)
            validated.append({"op": op, "field": field, "value": value})
            continue

        if op == "target.add":
            payload = raw.get("target")
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name", "")).strip()
            ttype = str(payload.get("type", "staticlib")).strip()
            if not name or ttype not in {"staticlib", "exe"}:
                continue
            if name in existing_targets or name in pending_targets:
                continue
            pending_targets.add(name)
            validated.append(
                {
                    "op": "target.add",
                    "target": {
                        "name": name,
                        "type": ttype,
                        "src_glob": [str(v) for v in payload.get("src_glob", [])],
                        "include_dirs": [str(v) for v in payload.get("include_dirs", [])],
                        "defines": [str(v) for v in payload.get("defines", [])],
                        "cflags": [str(v) for v in payload.get("cflags", [])],
                        "libs": [str(v) for v in payload.get("libs", [])],
                        "lib_dirs": [str(v) for v in payload.get("lib_dirs", [])],
                        "ldflags": [str(v) for v in payload.get("ldflags", [])],
                        "cxx_std": int(payload.get("cxx_std", 20)),
                        "links": [str(v) for v in payload.get("links", [])],
                    },
                }
            )
            continue

        if op == "target.link_add":
            target = str(raw.get("target", "")).strip()
            value = str(raw.get("value", "")).strip()
            known = existing_targets | pending_targets
            if not target or not value or target not in known or value not in known:
                continue
            key = f"{op}:{target}:{value}"
            if key in seen:
                continue
            seen.add(key)
            validated.append({"op": op, "target": target, "value": value})
            continue

        if op == "target.set_field":
            target = str(raw.get("target", "")).strip()
            field = str(raw.get("field", "")).strip()
            value = raw.get("value")
            known = existing_targets | pending_targets
            if target not in known or field not in ALLOWED_TARGET_SET_FIELDS:
                continue
            if field == "cxx_std":
                try:
                    value = int(value)
                except Exception:
                    continue
            else:
                if not isinstance(value, list):
                    continue
                value = [str(v) for v in value]
            validated.append({"op": op, "target": target, "field": field, "value": value})

    return validated
