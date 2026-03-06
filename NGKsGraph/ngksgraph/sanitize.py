from __future__ import annotations

import copy
import re
from typing import Any


_DRIVE_RE = re.compile(r"[A-Za-z]:")


def _replace_drive(value: str) -> str:
    return _DRIVE_RE.sub("<DRIVE>", value)


def _sanitize_string(value: str, repo_root: str, out_dir: str) -> str:
    normalized = value.replace("\\", "/")
    repo_norm = repo_root.replace("\\", "/")
    out_norm = out_dir.replace("\\", "/")

    if out_norm:
        normalized = normalized.replace(out_norm, "<OUT>")
    if repo_norm:
        normalized = normalized.replace(repo_norm, "<REPO>")
    normalized = _replace_drive(normalized)
    return normalized


def _sanitize_value(value: Any, repo_root: str, out_dir: str) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v, repo_root, out_dir) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v, repo_root, out_dir) for v in value]
    if isinstance(value, str):
        return _sanitize_string(value, repo_root, out_dir)
    return value


def sanitize_graph_dict(d: dict, repo_root: str, out_dir: str) -> dict:
    return _sanitize_value(copy.deepcopy(d), repo_root=repo_root, out_dir=out_dir)


def sanitize_compile_commands(entries: list) -> list:
    return _sanitize_value(copy.deepcopy(entries), repo_root="", out_dir="")
