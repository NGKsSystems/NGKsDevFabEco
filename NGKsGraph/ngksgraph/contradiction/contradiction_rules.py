from __future__ import annotations

import json
from pathlib import Path


_FALLBACK_RULES = {
    "dotnet_manifest_without_sources": {"severity": "high", "decision_impact": "fail_closed"},
    "framework_declared_without_source_001": {
        "severity": "medium",
        "decision_impact": "warn",
    },
    "cpp_standard_conflict_001": {"severity": "high", "decision_impact": "fail_closed"},
    "package_manager_mismatch_001": {"severity": "high", "decision_impact": "fail_closed"},
    "project_type_mismatch_001": {"severity": "high", "decision_impact": "fail_closed"},
    "native_foreign_disagree_001": {"severity": "high", "decision_impact": "fail_closed"},
}


def _rules_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "contradiction_rules.json"


def _load_rules() -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(_rules_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK_RULES)

    raw_rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rules, list):
        return dict(_FALLBACK_RULES)

    rules: dict[str, dict[str, str]] = {}
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            continue
        rules[rule_id] = {
            "severity": str(item.get("severity", "medium")),
            "decision_impact": str(item.get("decision_impact", item.get("decision", "warn"))),
        }

    return rules or dict(_FALLBACK_RULES)


_RULES = _load_rules()


def contradiction_ids() -> set[str]:
    return set(_RULES.keys())


def contradiction_policy(rule_id: str) -> dict[str, str]:
    return dict(_RULES.get(rule_id, {"severity": "medium", "decision_impact": "warn"}))
