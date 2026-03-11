from __future__ import annotations

import json
from pathlib import Path


_FALLBACK_RULES = [
    {
        "tool_or_file": "CMakeLists.txt",
        "role": "foreign_build_description",
        "authoritative": False,
        "import_strategy": "parse_only",
        "reason": "foreign authored config may inform but cannot govern native NGKs build",
    },
    {
        "tool_or_file": "build.ninja",
        "role": "foreign_executor_artifact",
        "authoritative": False,
        "import_strategy": "ignore",
        "reason": "generated artifact with high stale risk",
    },
    {
        "tool_or_file": "compile_commands.json",
        "role": "foreign_generated_hint",
        "authoritative": False,
        "import_strategy": "hint_only",
        "reason": "useful for diagnostics but not authoritative for planning",
    },
    {
        "tool_or_file": "CMakeCache.txt",
        "role": "cache",
        "authoritative": False,
        "import_strategy": "ignore",
        "reason": "configure cache is stale-prone and never authoritative",
    },
]


def _rules_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "authority_rules.json"


def _load_rules_from_json() -> list[dict[str, object]]:
    try:
        payload = json.loads(_rules_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(_FALLBACK_RULES)

    raw_rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rules, list):
        return list(_FALLBACK_RULES)

    result: list[dict[str, object]] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool_or_file")
        if not isinstance(tool, str) or not tool.strip():
            continue
        result.append(
            {
                "tool_or_file": tool,
                "role": str(item.get("role", "foreign_generated_hint")),
                "authoritative": bool(item.get("authoritative", False)),
                "import_strategy": str(item.get("import_strategy", "ignore")),
                "reason": str(item.get("reason", "foreign hint policy rule")),
            }
        )

    return result or list(_FALLBACK_RULES)


def default_authority_items() -> list[dict[str, object]]:
    return _load_rules_from_json()
