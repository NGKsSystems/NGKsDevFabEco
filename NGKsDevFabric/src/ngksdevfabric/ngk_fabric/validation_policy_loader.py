from __future__ import annotations

import json
from pathlib import Path

from .validation_policy_types import ValidationPluginPolicy


def _as_tuple_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return tuple()
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_validation_policy(policy_file: Path) -> tuple[str, list[ValidationPluginPolicy]]:
    path = policy_file.resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("validation policy must be a JSON object")

    schema_version = str(payload.get("schema_version", "")).strip() or "1"
    rows = payload.get("plugins", []) if isinstance(payload.get("plugins", []), list) else []

    out: list[ValidationPluginPolicy] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        plugin_name = str(row.get("plugin_name", "")).strip()
        if not plugin_name:
            continue
        out.append(
            ValidationPluginPolicy(
                plugin_name=plugin_name,
                plugin_category=str(row.get("plugin_category", "GENERIC")).strip() or "GENERIC",
                trigger_stages=_as_tuple_list(row.get("trigger_stages", [])),
                required_artifact_types=_as_tuple_list(row.get("required_artifact_types", [])),
                required_project_capabilities=_as_tuple_list(row.get("required_project_capabilities", [])),
                required_languages=_as_tuple_list(row.get("required_languages", [])),
                required_target_types=_as_tuple_list(row.get("required_target_types", [])),
                mode=str(row.get("mode", "advisory")).strip() or "advisory",
                severity=str(row.get("severity", "medium")).strip() or "medium",
                default_enabled=bool(row.get("default_enabled", True)),
                blocking_stages=_as_tuple_list(row.get("blocking_stages", [])),
                advisory_stages=_as_tuple_list(row.get("advisory_stages", [])),
            )
        )

    return schema_version, out
