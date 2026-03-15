from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validation_plugin_registry import execute_validation_plugins
from .validation_policy_loader import load_validation_policy
from .validation_policy_types import ValidationPluginPolicy


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _has_any_match(root: Path, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        for _ in root.rglob(pattern):
            return True
    return False


def _collect_project_context(project_root: Path, stage: str, profile: str, target: str) -> dict[str, Any]:
    root = project_root.resolve()
    artifact_types: set[str] = set()
    languages: set[str] = set()
    capabilities: set[str] = set()

    has_ui = _has_any_match(root, ("*.ui", "*.qml", "*.tsx", "*.jsx"))
    if has_ui:
        artifact_types.add("ui")
        capabilities.add("ui.present")

    has_api = _has_any_match(root, ("*openapi*.json", "*swagger*.json", "*schema*.json"))
    if has_api:
        artifact_types.add("api_contract")
        capabilities.add("api.contract.present")

    has_config = _has_any_match(root, ("*.env", "*.ini", "*.cfg", "*.yaml", "*.yml", "*.toml", "*.json"))
    if has_config:
        artifact_types.update({"config", "env"})
        capabilities.add("security.relevant.config")

    has_manifest = _has_any_match(root, ("package.json", "pyproject.toml", "requirements.txt", "CMakeLists.txt", "build.ninja"))
    if has_manifest:
        artifact_types.add("manifest")

    has_code = _has_any_match(root, ("*.py", "*.cpp", "*.c", "*.h", "*.cs", "*.ts", "*.js"))
    if has_code:
        artifact_types.add("code")

    if _has_any_match(root, ("*.py",)):
        languages.add("python")
    if _has_any_match(root, ("*.cpp", "*.h")):
        languages.add("cpp")
    if _has_any_match(root, ("*.ts", "*.js")):
        languages.add("javascript")

    workspace_integrity_report = root / "_proof" / "workspace_integrity" / "02_workspace_integrity_report.json"

    return {
        "stage": stage,
        "project_root": str(root),
        "active_profile": profile,
        "active_target": target,
        "artifact_types": sorted(artifact_types),
        "project_capabilities": sorted(capabilities),
        "languages": sorted(languages),
        "target_types": [target] if target else [],
        "workspace_integrity_report_present": workspace_integrity_report.exists(),
    }


def _required_subset(required: tuple[str, ...], present: list[str]) -> bool:
    if not required:
        return True
    present_set = {str(item).strip() for item in present}
    return all(item in present_set for item in required)


def _evaluate_policy_row(policy: ValidationPluginPolicy, context: dict[str, Any]) -> tuple[bool, str]:
    stage = str(context.get("stage", "")).strip()
    if not policy.default_enabled:
        return False, "default_disabled"
    if stage not in policy.trigger_stages:
        return False, "stage_not_triggered"
    if not _required_subset(policy.required_artifact_types, list(context.get("artifact_types", []))):
        return False, "required_artifact_types_missing"
    if not _required_subset(policy.required_project_capabilities, list(context.get("project_capabilities", []))):
        return False, "required_project_capabilities_missing"
    if policy.required_languages and not any(lang in set(context.get("languages", [])) for lang in policy.required_languages):
        return False, "required_languages_missing"
    if policy.required_target_types and not any(target in set(context.get("target_types", [])) for target in policy.required_target_types):
        return False, "required_target_types_missing"
    return True, "policy_match"


def evaluate_validation_policy(
    *,
    project_root: Path,
    pf: Path,
    stage: str,
    profile: str,
    target: str,
) -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parent / "validation_plugin_policy.json"
    schema_version, policies = load_validation_policy(policy_path)

    context = _collect_project_context(project_root, stage, profile, target)
    matrix: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for policy in sorted(policies, key=lambda row: row.plugin_name):
        selected_flag, reason = _evaluate_policy_row(policy, context)
        row = {
            "plugin_name": policy.plugin_name,
            "plugin_category": policy.plugin_category,
            "selected": selected_flag,
            "reason": reason,
            "blocking_stages": list(policy.blocking_stages),
            "advisory_stages": list(policy.advisory_stages),
            "mode": policy.mode,
            "severity": policy.severity,
        }
        matrix.append(row)
        if selected_flag:
            selected.append(row)
        else:
            skipped.append(row)

    blocking_plugins = [
        row["plugin_name"]
        for row in selected
        if stage in set(row.get("blocking_stages", []))
    ]
    advisory_plugins = [
        row["plugin_name"]
        for row in selected
        if stage in set(row.get("advisory_stages", [])) and row["plugin_name"] not in blocking_plugins
    ]

    _write_json(pf / "30_policy_input_context.json", context)
    _write_json(
        pf / "31_plugin_policy_matrix.json",
        {
            "schema_version": schema_version,
            "policy_path": str(policy_path),
            "rows": matrix,
        },
    )
    _write_json(
        pf / "32_selected_plugins.json",
        {
            "stage": stage,
            "selected_plugins": [row["plugin_name"] for row in selected],
            "rows": selected,
            "blocking_plugins": blocking_plugins,
            "advisory_plugins": advisory_plugins,
        },
    )
    _write_json(
        pf / "33_skipped_plugins.json",
        {
            "stage": stage,
            "skipped_plugins": [row["plugin_name"] for row in skipped],
            "rows": skipped,
        },
    )
    _write_json(
        pf / "34_policy_gate_rules.json",
        {
            "stage": stage,
            "blocking_plugins": blocking_plugins,
            "advisory_plugins": advisory_plugins,
            "gate_rule": "blocking plugin FAIL => stage FAIL; advisory plugin FAIL => warning only",
        },
    )

    lines = [
        "# Validation Policy Summary",
        "",
        f"- stage: {stage}",
        f"- selected_plugins: {', '.join([row['plugin_name'] for row in selected]) if selected else 'none'}",
        f"- skipped_plugins: {', '.join([row['plugin_name'] for row in skipped]) if skipped else 'none'}",
        f"- blocking_plugins: {', '.join(blocking_plugins) if blocking_plugins else 'none'}",
        f"- advisory_plugins: {', '.join(advisory_plugins) if advisory_plugins else 'none'}",
        "",
    ]
    _write_text(pf / "35_policy_summary.md", "\n".join(lines))

    plugin_result = execute_validation_plugins(
        project_root=project_root,
        pf=pf,
        view_name=f"runtime_policy_{stage}",
        selected_plugin_names=[row["plugin_name"] for row in selected],
    )

    plugin_rows = plugin_result.get("rows", []) if isinstance(plugin_result.get("rows", []), list) else []
    failing_plugin_names = [
        str(row.get("plugin_name", ""))
        for row in plugin_rows
        if str(row.get("status", "")).upper() == "FAIL"
    ]

    blocking_failures = [name for name in failing_plugin_names if name in set(blocking_plugins)]
    advisory_failures = [name for name in failing_plugin_names if name not in set(blocking_plugins)]

    gate_status = "PASS"
    gate_reason = "policy_gate_passed"
    if blocking_failures:
        gate_status = "FAIL"
        gate_reason = "blocking_plugin_failure"

    return {
        "stage": stage,
        "selected_plugins": [row["plugin_name"] for row in selected],
        "skipped_plugins": [row["plugin_name"] for row in skipped],
        "blocking_plugins": blocking_plugins,
        "advisory_plugins": advisory_plugins,
        "blocking_failures": blocking_failures,
        "advisory_failures": advisory_failures,
        "gate_status": gate_status,
        "gate_reason": gate_reason,
        "plugin_result": plugin_result,
    }
