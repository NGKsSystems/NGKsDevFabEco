from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_REQUIRED_SNAPSHOT_FILES = [
    "component_graph.json",
    "dependency_contract.json",
    "runtime_resolution.json",
    "scenario_index.json",
]

_REQUIRED_POLICY_STATES = [
    "CERTIFIED_IMPROVEMENT",
    "CERTIFIED_STABLE",
    "CERTIFIED_REGRESSION",
    "CERTIFICATION_INCONCLUSIVE",
]


@dataclass(frozen=True)
class CompatibilityResult:
    state: str
    warnings: list[str]
    errors: list[str]
    recommendations: list[str]
    artifacts: list[str]


def _is_numeric(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_compatibility_preflight(
    *,
    repo_root: Path,
    pf: Path,
    baseline_bundle_root: Path,
    baseline_matrix_path: Path,
    baseline_metrics_path: Path,
    baseline_manifest_path: Path,
    current_bundle_root: Path,
    current_source_mode: str,
    current_matrix_path: Path | None,
    current_metrics_path: Path | None,
    current_manifest_path: Path | None,
    current_scenario_proof_root: Path | None,
    baseline_matrix: dict[str, Any],
    baseline_metrics: dict[str, Any],
    baseline_manifest: dict[str, Any],
    current_matrix: dict[str, Any],
    current_metrics: dict[str, Any],
    current_manifest: dict[str, Any],
    required_metric_keys: list[str],
) -> CompatibilityResult:
    out_dir = pf / "compatibility"
    warnings: list[str] = []
    errors: list[str] = []
    recommendations: list[str] = []

    baseline_scenarios = baseline_matrix.get("scenarios", []) if isinstance(baseline_matrix.get("scenarios"), list) else []
    current_scenarios = current_matrix.get("scenarios", []) if isinstance(current_matrix.get("scenarios"), list) else []

    baseline_ids = {
        str(item.get("scenario_id", "")).strip()
        for item in baseline_scenarios
        if isinstance(item, dict) and str(item.get("scenario_id", "")).strip()
    }
    current_ids = {
        str(item.get("scenario_id", "")).strip()
        for item in current_scenarios
        if isinstance(item, dict) and str(item.get("scenario_id", "")).strip()
    }

    baseline_version = str(baseline_manifest.get("baseline_version", "")).strip()
    supported_baseline_versions = {"v1", "current_run", "fixture_improvement", "fixture_regression", "fixture_inconclusive"}

    inputs_payload = {
        "baseline_bundle_root": str(baseline_bundle_root.resolve()),
        "baseline_matrix": str(baseline_matrix_path.resolve()),
        "baseline_metrics": str(baseline_metrics_path.resolve()),
        "baseline_manifest": str(baseline_manifest_path.resolve()),
        "current_bundle_root": str(current_bundle_root.resolve()),
        "current_source_mode": current_source_mode,
        "current_matrix": str(current_matrix_path.resolve()) if current_matrix_path else "generated_from_scenario_proofs",
        "current_metrics": str(current_metrics_path.resolve()) if current_metrics_path else "generated_from_scenario_proofs",
        "current_manifest": str(current_manifest_path.resolve()) if current_manifest_path else "generated_from_scenario_proofs",
        "current_scenario_proof_root": str(current_scenario_proof_root.resolve()) if current_scenario_proof_root else "",
    }

    baseline_schema = {
        "files_exist": {
            "baseline_matrix": baseline_matrix_path.is_file(),
            "diagnostic_metrics": baseline_metrics_path.is_file(),
            "baseline_manifest": baseline_manifest_path.is_file(),
        },
        "baseline_version": baseline_version,
        "baseline_version_supported": baseline_version in supported_baseline_versions,
        "required_fields": {
            "manifest.baseline_version": bool(baseline_version),
            "matrix.scenarios": isinstance(baseline_matrix.get("scenarios"), list),
        },
        "required_metric_keys": {k: (k in baseline_metrics) for k in required_metric_keys},
    }

    if not baseline_schema["baseline_version_supported"]:
        errors.append(f"unsupported_baseline_version:{baseline_version or 'missing'}")
        recommendations.append("use_supported_baseline_version_or_upgrade_compatibility_policy")

    for key, exists in baseline_schema["required_metric_keys"].items():
        if not exists:
            errors.append(f"baseline_missing_metric_key:{key}")
            recommendations.append("regenerate_baseline_metrics_with_required_keys")

    current_schema = {
        "source_mode": current_source_mode,
        "scenario_count": len(current_ids),
        "required_metric_keys": {k: (k in current_metrics) for k in required_metric_keys},
        "diagnostic_score_numeric": _is_numeric(current_metrics.get("average_diagnostic_score")),
    }

    for key, exists in current_schema["required_metric_keys"].items():
        if not exists:
            errors.append(f"current_missing_metric_key:{key}")
            recommendations.append("repair_current_result_set_metric_schema")

    if not current_schema["diagnostic_score_numeric"]:
        errors.append("current_average_diagnostic_score_not_numeric")
        recommendations.append("ensure_current_diagnostic_metrics_are_numeric")

    scenario_compat = {
        "baseline_scenario_count": len(baseline_ids),
        "current_scenario_count": len(current_ids),
        "missing_in_current": sorted(baseline_ids - current_ids),
        "extra_in_current": sorted(current_ids - baseline_ids),
        "compatibility": "exact_match",
    }
    if scenario_compat["missing_in_current"]:
        scenario_compat["compatibility"] = "incompatible_missing_scenarios"
        errors.append("missing_scenarios_in_current:" + ",".join(scenario_compat["missing_in_current"]))
        recommendations.append("rebuild_current_result_set_with_full_scenario_coverage")
    elif scenario_compat["extra_in_current"]:
        scenario_compat["compatibility"] = "additive_drift"
        warnings.append("additional_scenarios_present_in_current:" + ",".join(scenario_compat["extra_in_current"]))
        recommendations.append("review_additive_scenarios_and_consider_baseline_refresh")

    metric_schema = {
        "required_keys": required_metric_keys,
        "baseline_numeric_keys": {k: _is_numeric(baseline_metrics.get(k)) for k in required_metric_keys},
        "current_numeric_keys": {k: _is_numeric(current_metrics.get(k)) for k in required_metric_keys},
        "diagnostic_score_range_check": {
            "baseline_average_diagnostic_score": baseline_metrics.get("average_diagnostic_score"),
            "current_average_diagnostic_score": current_metrics.get("average_diagnostic_score"),
            "range_assumption": "0_to_1",
            "baseline_in_range": False,
            "current_in_range": False,
        },
    }
    bds = baseline_metrics.get("average_diagnostic_score")
    cds = current_metrics.get("average_diagnostic_score")
    if _is_numeric(bds):
        metric_schema["diagnostic_score_range_check"]["baseline_in_range"] = 0.0 <= float(bds) <= 1.0
    if _is_numeric(cds):
        metric_schema["diagnostic_score_range_check"]["current_in_range"] = 0.0 <= float(cds) <= 1.0

    for key, ok in metric_schema["baseline_numeric_keys"].items():
        if not ok:
            errors.append(f"baseline_metric_not_numeric:{key}")
            recommendations.append("repair_baseline_metric_numeric_types")
    for key, ok in metric_schema["current_numeric_keys"].items():
        if not ok:
            errors.append(f"current_metric_not_numeric:{key}")
            recommendations.append("repair_current_metric_numeric_types")

    if not metric_schema["diagnostic_score_range_check"]["baseline_in_range"]:
        warnings.append("baseline_average_diagnostic_score_outside_normalized_range")
        recommendations.append("confirm_baseline_diagnostic_score_normalization")
    if not metric_schema["diagnostic_score_range_check"]["current_in_range"]:
        warnings.append("current_average_diagnostic_score_outside_normalized_range")
        recommendations.append("confirm_current_diagnostic_score_normalization")

    policy_file = (repo_root / "certification_gate_policy.json").resolve()
    policy_compat: dict[str, Any] = {
        "policy_file": str(policy_file),
        "policy_file_exists": policy_file.is_file(),
        "required_states_present": {},
        "shape_valid": False,
    }
    if policy_file.is_file():
        try:
            policy_data = json.loads(policy_file.read_text(encoding="utf-8"))
            states = policy_data.get("states", {}) if isinstance(policy_data, dict) else {}
            policy_compat["shape_valid"] = isinstance(states, dict)
            for state in _REQUIRED_POLICY_STATES:
                present = isinstance(states, dict) and state in states
                policy_compat["required_states_present"][state] = present
                if not present:
                    errors.append(f"gate_policy_missing_state:{state}")
                    recommendations.append("repair_certification_gate_policy_state_mapping")
            if not policy_compat["shape_valid"]:
                errors.append("gate_policy_shape_invalid")
                recommendations.append("repair_certification_gate_policy_schema")
        except (OSError, ValueError, TypeError):
            errors.append("gate_policy_unreadable_or_invalid_json")
            recommendations.append("repair_certification_gate_policy_json")
    else:
        warnings.append("gate_policy_file_missing_optional")
        recommendations.append("add_certification_gate_policy_json_for_ci_consumers")

    snapshot_dir = baseline_bundle_root / "system_snapshot"
    snapshot_required = snapshot_dir.exists() or (baseline_bundle_root / "baseline_v1" / "system_snapshot").exists()
    if not snapshot_dir.exists() and (baseline_bundle_root / "baseline_v1" / "system_snapshot").exists():
        snapshot_dir = baseline_bundle_root / "baseline_v1" / "system_snapshot"

    snapshot_compat = {
        "snapshot_required": bool(snapshot_required),
        "snapshot_dir": str(snapshot_dir.resolve()),
        "required_files": {name: (snapshot_dir / name).is_file() for name in _REQUIRED_SNAPSHOT_FILES},
    }
    if snapshot_required:
        for name, ok in snapshot_compat["required_files"].items():
            if not ok:
                errors.append(f"missing_snapshot_file:{name}")
                recommendations.append("restore_required_system_snapshot_files")

    if errors:
        state = "INCOMPATIBLE"
    elif warnings:
        state = "COMPATIBLE_WITH_WARNINGS"
    else:
        state = "COMPATIBLE"

    classification = {
        "compatibility_state": state,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "recommendations": sorted(set(recommendations)),
        "comparison_trustworthy": state != "INCOMPATIBLE",
    }

    report_lines = [
        "# Certification Compatibility Report",
        "",
        f"- compatibility_state: {state}",
        f"- comparison_trustworthy: {str(state != 'INCOMPATIBLE').lower()}",
        "",
        "## Errors",
    ]
    if classification["errors"]:
        report_lines.extend([f"- {item}" for item in classification["errors"]])
    else:
        report_lines.append("- none")
    report_lines.extend(["", "## Warnings"])
    if classification["warnings"]:
        report_lines.extend([f"- {item}" for item in classification["warnings"]])
    else:
        report_lines.append("- none")
    report_lines.extend(["", "## Recommended Remediation"])
    if classification["recommendations"]:
        report_lines.extend([f"- {item}" for item in classification["recommendations"]])
    else:
        report_lines.append("- none")

    _write_json(out_dir / "00_compatibility_inputs.json", inputs_payload)
    _write_json(out_dir / "01_baseline_schema_check.json", baseline_schema)
    _write_json(out_dir / "02_current_run_schema_check.json", current_schema)
    _write_json(out_dir / "03_scenario_compatibility.json", scenario_compat)
    _write_json(out_dir / "04_metric_schema_compatibility.json", metric_schema)
    _write_json(out_dir / "05_policy_compatibility.json", policy_compat)
    _write_json(out_dir / "06_snapshot_compatibility.json", snapshot_compat)
    _write_json(out_dir / "07_compatibility_classification.json", classification)
    _write_text(out_dir / "08_compatibility_report.md", "\n".join(report_lines) + "\n")

    artifacts = [
        "compatibility/00_compatibility_inputs.json",
        "compatibility/01_baseline_schema_check.json",
        "compatibility/02_current_run_schema_check.json",
        "compatibility/03_scenario_compatibility.json",
        "compatibility/04_metric_schema_compatibility.json",
        "compatibility/05_policy_compatibility.json",
        "compatibility/06_snapshot_compatibility.json",
        "compatibility/07_compatibility_classification.json",
        "compatibility/08_compatibility_report.md",
    ]

    return CompatibilityResult(
        state=state,
        warnings=sorted(set(warnings)),
        errors=sorted(set(errors)),
        recommendations=sorted(set(recommendations)),
        artifacts=artifacts,
    )
