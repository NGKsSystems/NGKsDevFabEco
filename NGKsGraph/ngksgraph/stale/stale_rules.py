from __future__ import annotations

import json
from pathlib import Path


_FALLBACK_RULES = [
    {"path_glob": "build/**", "risk_level": "high", "action": "ignore"},
    {"path_glob": "out/**", "risk_level": "high", "action": "ignore"},
    {"path_glob": "**/CMakeCache.txt", "risk_level": "high", "action": "ignore"},
    {"path_glob": "**/build.ninja", "risk_level": "high", "action": "ignore"},
    {"path_glob": "**/compile_commands.json", "risk_level": "high", "action": "ignore"},
]


def _rules_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "stale_rules.json"


def _load_rules() -> list[dict[str, str]]:
    try:
        payload = json.loads(_rules_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(_FALLBACK_RULES)

    raw_rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rules, list):
        return list(_FALLBACK_RULES)

    rules: list[dict[str, str]] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        path_glob = str(item.get("path_glob", item.get("file", ""))).strip()
        if not path_glob:
            continue
        risk_level = str(item.get("risk_level", item.get("severity", "medium"))).strip().lower() or "medium"
        action = str(item.get("action", "ignore")).strip().lower() or "ignore"
        rules.append({"path_glob": path_glob, "risk_level": risk_level, "action": action})

    return rules or list(_FALLBACK_RULES)


STALE_RULES = _load_rules()
