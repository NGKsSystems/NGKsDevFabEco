from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_REQUIRED_ARTIFACTS = [
    "baseline_manifest",
    "baseline_matrix",
    "diagnostic_metrics",
    "scenario_index",
]

_DEFAULT_OPTIONAL_ARTIFACTS = [
    "compatibility_classification",
    "compatibility_report",
]


@dataclass(frozen=True)
class SubtargetSpec:
    subtarget_id: str
    required: bool
    target_root: Path
    baseline_root: Path
    scenario_index_path: Path
    supported_baseline_versions: list[str]
    ready: bool
    warnings: list[str]
    errors: list[str]


@dataclass(frozen=True)
class TargetValidationResult:
    state: str
    warnings: list[str]
    errors: list[str]
    recommendations: list[str]
    project_name: str
    target_root: Path
    certification_root: Path
    baseline_root: Path
    scenario_index_path: Path
    supported_baseline_versions: list[str]
    execution_profile_hint: str
    subtargets: list[SubtargetSpec]
    artifacts: list[str]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve_path(base: Path, raw: str) -> Path:
    candidate = Path(str(raw).strip())
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _parse_subtargets(
    *,
    target_root: Path,
    contract_data: dict[str, Any],
    inherited_supported_versions: list[str],
) -> tuple[list[SubtargetSpec], list[str], list[str], list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    errors: list[str] = []
    recommendations: list[str] = []

    raw = contract_data.get("subtargets", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        warnings.append("subtargets_invalid_shape_ignored")
        recommendations.append("define_subtargets_as_array")
        return [], warnings, errors, recommendations, []

    parsed: list[SubtargetSpec] = []
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            warnings.append(f"subtarget_invalid_entry_ignored:index_{idx}")
            recommendations.append("use_object_entries_for_subtargets")
            continue

        subtarget_id_raw = str(item.get("subtarget_id", f"subtarget_{idx:02d}")).strip()
        subtarget_id = subtarget_id_raw or f"subtarget_{idx:02d}"
        if subtarget_id in seen_ids:
            errors.append(f"duplicate_subtarget_id:{subtarget_id}")
            recommendations.append("ensure_subtarget_ids_unique")
            continue
        seen_ids.add(subtarget_id)

        required = _safe_bool(item.get("required", True), True)
        target_root_path = _resolve_path(target_root, str(item.get("target_root", ".")))
        baseline_root = _resolve_path(target_root_path, str(item.get("baseline_root", "certification/baseline_v1")))
        scenario_index_path = _resolve_path(
            target_root_path,
            str(item.get("scenario_index_path", "certification/scenario_index.json")),
        )

        supported_versions_raw = item.get("supported_baseline_versions", inherited_supported_versions)
        supported_versions = [str(v).strip() for v in supported_versions_raw if str(v).strip()]
        if not supported_versions:
            supported_versions = list(inherited_supported_versions)

        sub_warnings: list[str] = []
        sub_errors: list[str] = []

        if not target_root_path.is_dir():
            sub_errors.append("target_root_missing")
        if not baseline_root.is_dir():
            sub_errors.append("baseline_root_missing")
        if not scenario_index_path.is_file():
            sub_errors.append("scenario_index_missing")

        required_artifacts = {
            "baseline_manifest": baseline_root / "baseline_manifest.json",
            "baseline_matrix": baseline_root / "baseline_matrix.json",
            "diagnostic_metrics": baseline_root / "diagnostic_metrics.json",
        }
        for name, path in required_artifacts.items():
            if not path.is_file():
                sub_errors.append(f"missing_required_artifact:{name}")

        if sub_errors:
            if required:
                errors.extend([f"required_subtarget_error:{subtarget_id}:{err}" for err in sub_errors])
            else:
                warnings.extend([f"optional_subtarget_warning:{subtarget_id}:{err}" for err in sub_errors])
                recommendations.append("optional_subtarget_not_ready_non_blocking")

        ready = not bool(sub_errors)
        parsed.append(
            SubtargetSpec(
                subtarget_id=subtarget_id,
                required=required,
                target_root=target_root_path,
                baseline_root=baseline_root,
                scenario_index_path=scenario_index_path,
                supported_baseline_versions=supported_versions,
                ready=ready,
                warnings=sorted(set(sub_warnings)),
                errors=sorted(set(sub_errors)),
            )
        )
        rows.append(
            {
                "subtarget_id": subtarget_id,
                "required": required,
                "target_root": str(target_root_path),
                "baseline_root": str(baseline_root),
                "scenario_index_path": str(scenario_index_path),
                "supported_baseline_versions": supported_versions,
                "ready": ready,
                "warnings": sorted(set(sub_warnings)),
                "errors": sorted(set(sub_errors)),
            }
        )

    parsed = sorted(parsed, key=lambda item: item.subtarget_id)
    rows = sorted(rows, key=lambda item: str(item.get("subtarget_id", "")))
    return parsed, warnings, errors, recommendations, rows


def _find_contract(project_root: Path, explicit_contract_path: Path | None) -> Path | None:
    if explicit_contract_path is not None:
        path = explicit_contract_path.resolve()
        return path if path.is_file() else None

    candidates = [
        project_root / "certification_target.json",
        project_root / "certification" / "certification_target.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def run_target_validation_precheck(
    *,
    project_root: Path,
    pf: Path,
    explicit_contract_path: Path | None = None,
    require_contract: bool = True,
) -> TargetValidationResult:
    out_dir = pf / "target_validation"
    warnings: list[str] = []
    errors: list[str] = []
    recommendations: list[str] = []

    target_root = project_root.resolve()
    contract_path = _find_contract(target_root, explicit_contract_path)
    contract_data: dict[str, Any] = {}
    contract_loaded = False

    if contract_path and contract_path.is_file():
        try:
            loaded = json.loads(contract_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                contract_data = loaded
                contract_loaded = True
            else:
                errors.append("target_contract_invalid_json_object")
                recommendations.append("repair_target_contract_shape")
        except (OSError, ValueError, TypeError):
            errors.append("target_contract_unreadable_or_invalid_json")
            recommendations.append("repair_target_contract_json")
    else:
        if require_contract:
            errors.append("target_contract_missing")
            recommendations.append("add_certification_target_json")
        else:
            warnings.append("target_contract_missing_using_inferred_defaults")
            recommendations.append("add_certification_target_json_for_explicit_target_model")

    project_name = str(contract_data.get("project_name", target_root.name)).strip() or target_root.name
    certification_root = _resolve_path(
        target_root,
        str(contract_data.get("certification_root", "certification")),
    )
    baseline_root = _resolve_path(
        target_root,
        str(contract_data.get("baseline_root", "certification/baseline_v1")),
    )
    scenario_index_path = _resolve_path(
        target_root,
        str(contract_data.get("scenario_index_path", "certification/scenario_index.json")),
    )
    execution_profile_hint = str(contract_data.get("execution_profile", "")).strip().upper()

    supported_versions_raw = contract_data.get("supported_baseline_versions", ["v1", "current_run"])
    supported_baseline_versions = [str(item).strip() for item in supported_versions_raw if str(item).strip()]
    if not supported_baseline_versions:
        supported_baseline_versions = ["v1", "current_run"]
        warnings.append("supported_baseline_versions_missing_using_defaults")
        recommendations.append("define_supported_baseline_versions_in_target_contract")

    subtargets, subtarget_warnings, subtarget_errors, subtarget_recommendations, subtarget_rows = _parse_subtargets(
        target_root=target_root,
        contract_data=contract_data,
        inherited_supported_versions=supported_baseline_versions,
    )
    warnings.extend(subtarget_warnings)
    errors.extend(subtarget_errors)
    recommendations.extend(subtarget_recommendations)

    required_artifacts_raw = contract_data.get("required_artifacts", _DEFAULT_REQUIRED_ARTIFACTS)
    required_artifacts = [str(item).strip() for item in required_artifacts_raw if str(item).strip()]
    if not required_artifacts:
        required_artifacts = list(_DEFAULT_REQUIRED_ARTIFACTS)

    optional_artifacts_raw = contract_data.get("optional_artifacts", _DEFAULT_OPTIONAL_ARTIFACTS)
    optional_artifacts = [str(item).strip() for item in optional_artifacts_raw if str(item).strip()]

    required_contract_fields = [
        "project_name",
        "target_root",
        "certification_root",
        "baseline_root",
        "scenario_index_path",
        "supported_baseline_versions",
        "required_artifacts",
        "optional_artifacts",
        "target_type",
        "schema_version",
    ]

    missing_contract_fields: list[str] = []
    if contract_loaded:
        for key in required_contract_fields:
            if key not in contract_data:
                missing_contract_fields.append(key)
        if missing_contract_fields:
            warnings.append("target_contract_missing_fields:" + ",".join(sorted(missing_contract_fields)))
            recommendations.append("complete_target_contract_required_fields")

    artifact_path_map: dict[str, Path] = {
        "baseline_manifest": baseline_root / "baseline_manifest.json",
        "baseline_matrix": baseline_root / "baseline_matrix.json",
        "diagnostic_metrics": baseline_root / "diagnostic_metrics.json",
        "scenario_index": scenario_index_path,
        "compatibility_classification": target_root / "_proof" / "latest" / "run" / "compatibility" / "07_compatibility_classification.json",
        "compatibility_report": target_root / "_proof" / "latest" / "run" / "compatibility" / "08_compatibility_report.md",
    }
    subtarget_mode = bool(subtargets)

    target_shape = {
        "target_root_exists": target_root.is_dir(),
        "certification_root_exists": certification_root.is_dir(),
        "baseline_root_exists": baseline_root.is_dir(),
        "scenario_index_exists": scenario_index_path.is_file(),
        "subtarget_mode": subtarget_mode,
        "subtarget_count": len(subtargets),
        "contract_required": bool(require_contract),
        "contract_loaded": contract_loaded,
    }

    if not target_shape["target_root_exists"]:
        errors.append("target_root_missing")
        recommendations.append("use_valid_project_root")
    if not target_shape["certification_root_exists"]:
        errors.append("certification_root_missing")
        recommendations.append("create_certification_root_or_fix_target_contract")
    if not target_shape["baseline_root_exists"]:
        if subtarget_mode:
            warnings.append("top_level_baseline_root_missing_subtarget_mode")
        else:
            errors.append("baseline_root_missing")
            recommendations.append("restore_baseline_root_or_fix_target_contract")

    artifact_check_required: dict[str, bool] = {}
    artifact_check_optional: dict[str, bool] = {}

    if not subtarget_mode:
        for name in required_artifacts:
            path = artifact_path_map.get(name)
            exists = path.is_file() if path else False
            artifact_check_required[name] = exists
            if not exists:
                errors.append(f"missing_required_artifact:{name}")
                recommendations.append("restore_required_target_artifacts")
    else:
        for name in required_artifacts:
            artifact_check_required[name] = False

    for name in optional_artifacts:
        path = artifact_path_map.get(name)
        exists = path.is_file() if path else False
        artifact_check_optional[name] = exists
        if not exists:
            warnings.append(f"missing_optional_artifact:{name}")
            recommendations.append("optional_artifact_missing_non_blocking")

    if errors:
        state = "CERTIFICATION_NOT_READY"
    elif warnings:
        state = "CERTIFICATION_READY_WITH_WARNINGS"
    else:
        state = "CERTIFICATION_READY"

    compare_ready = state != "CERTIFICATION_NOT_READY"
    gate_ready = state != "CERTIFICATION_NOT_READY"

    inputs_payload = {
        "project_root": str(target_root),
        "contract_path": str(contract_path) if contract_path else "",
        "require_contract": bool(require_contract),
        "explicit_contract_path": str(explicit_contract_path.resolve()) if explicit_contract_path else "",
    }

    contract_load_payload = {
        "contract_loaded": contract_loaded,
        "contract_path": str(contract_path) if contract_path else "",
        "project_name": project_name,
        "execution_profile": execution_profile_hint,
        "schema_version": str(contract_data.get("schema_version", "")),
        "target_type": str(contract_data.get("target_type", "")),
        "resolved": {
            "target_root": str(target_root),
            "certification_root": str(certification_root),
            "baseline_root": str(baseline_root),
            "scenario_index_path": str(scenario_index_path),
        },
        "supported_baseline_versions": supported_baseline_versions,
        "required_artifacts": required_artifacts,
        "optional_artifacts": optional_artifacts,
        "subtarget_mode": subtarget_mode,
        "subtarget_count": len(subtargets),
    }

    target_shape_payload = {
        "target_shape": target_shape,
        "missing_contract_fields": missing_contract_fields,
        "field_resolution_strategy": "contract_or_inferred_defaults",
    }

    artifact_check_payload = {
        "required_artifacts": artifact_check_required,
        "optional_artifacts": artifact_check_optional,
    }

    capability_payload = {
        "target_capability_state": state,
        "compare_ready": compare_ready,
        "gate_ready": gate_ready,
        "warnings": sorted(set(warnings)),
        "errors": sorted(set(errors)),
        "recommendations": sorted(set(recommendations)),
    }

    report_lines = [
        "# Certification Target Capability Report",
        "",
        f"- project_name: {project_name}",
        f"- target_capability_state: {state}",
        f"- compare_ready: {str(compare_ready).lower()}",
        f"- gate_ready: {str(gate_ready).lower()}",
        "",
        "## Resolved Target",
        f"- target_root: {target_root}",
        f"- certification_root: {certification_root}",
        f"- baseline_root: {baseline_root}",
        f"- scenario_index_path: {scenario_index_path}",
        "",
        "## Errors",
    ]
    if capability_payload["errors"]:
        report_lines.extend([f"- {item}" for item in capability_payload["errors"]])
    else:
        report_lines.append("- none")

    report_lines.extend(["", "## Warnings"])
    if capability_payload["warnings"]:
        report_lines.extend([f"- {item}" for item in capability_payload["warnings"]])
    else:
        report_lines.append("- none")

    report_lines.extend(["", "## Recommended Remediation"])
    if capability_payload["recommendations"]:
        report_lines.extend([f"- {item}" for item in capability_payload["recommendations"]])
    else:
        report_lines.append("- none")

    _write_json(out_dir / "00_target_inputs.json", inputs_payload)
    _write_json(out_dir / "01_target_contract_load.json", contract_load_payload)
    _write_json(out_dir / "02_target_shape_validation.json", target_shape_payload)
    _write_json(out_dir / "03_target_artifact_check.json", artifact_check_payload)
    _write_json(out_dir / "04_target_capability_classification.json", capability_payload)
    _write_text(out_dir / "05_target_report.md", "\n".join(report_lines) + "\n")
    if subtarget_mode:
        _write_json(out_dir / "06_subtarget_index.json", {"subtargets": subtarget_rows})
        _write_json(
            out_dir / "07_subtarget_validation.json",
            {
                "required_subtarget_count": sum(1 for item in subtargets if item.required),
                "optional_subtarget_count": sum(1 for item in subtargets if not item.required),
                "rows": subtarget_rows,
            },
        )

    artifacts = [
        "target_validation/00_target_inputs.json",
        "target_validation/01_target_contract_load.json",
        "target_validation/02_target_shape_validation.json",
        "target_validation/03_target_artifact_check.json",
        "target_validation/04_target_capability_classification.json",
        "target_validation/05_target_report.md",
    ]
    if subtarget_mode:
        artifacts.extend(
            [
                "target_validation/06_subtarget_index.json",
                "target_validation/07_subtarget_validation.json",
            ]
        )

    return TargetValidationResult(
        state=state,
        warnings=sorted(set(warnings)),
        errors=sorted(set(errors)),
        recommendations=sorted(set(recommendations)),
        project_name=project_name,
        target_root=target_root,
        certification_root=certification_root,
        baseline_root=baseline_root,
        scenario_index_path=scenario_index_path,
        supported_baseline_versions=supported_baseline_versions,
        execution_profile_hint=execution_profile_hint,
        subtargets=subtargets,
        artifacts=artifacts,
    )
