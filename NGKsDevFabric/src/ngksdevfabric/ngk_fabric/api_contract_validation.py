from __future__ import annotations

from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_DEFAULT_CONFIG = {
    "strict_unknown_fields": True,
    "max_version_drift_minor": 1,
    "treat_nullability_violation_as_fail": True,
    "treat_type_mismatch_as_fail": True,
    "treat_missing_required_field_as_fail": True,
}


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _slug(value: str) -> str:
    text = str(value).strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    compact = "".join(chars)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_") or "item"


def _parse_version(value: str) -> tuple[int, int, int]:
    parts = str(value).strip().split(".")
    padded = (parts + ["0", "0", "0"])[:3]
    return (_safe_int(padded[0]), _safe_int(padded[1]), _safe_int(padded[2]))


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _schema_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows", []) if isinstance(payload.get("rows", []), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _expected_map(expected_fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in expected_fields:
        field = str(row.get("field_path", row.get("field", ""))).strip()
        if field:
            out[field] = row
    return out


class APIContractValidationPlugin(ValidationPlugin):
    plugin_name = "api_contract_validation"
    plugin_version = "1.0.0"
    plugin_category = "API_CONTRACT_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        project_root = Path(str(context.get("project_root", "."))).resolve()
        pf = Path(str(context.get("pf", "."))).resolve()

        config_path = (project_root / "api_contract_validation_config.json").resolve()
        loaded_config = read_json(config_path)
        config = dict(_DEFAULT_CONFIG)
        for key, default in _DEFAULT_CONFIG.items():
            if key not in loaded_config:
                continue
            if isinstance(default, bool):
                config[key] = _as_bool(loaded_config.get(key, default), default)
            else:
                config[key] = _safe_int(loaded_config.get(key, default))

        self.inputs = {
            "config": config,
            "config_path": str(config_path),
            "certification_target": read_json(project_root / "certification_target.json"),
            "subtarget_results": read_json(pf / "rollup" / "02_subtarget_results.json"),
            "component_history_context": read_json(pf / "history" / "43_component_history_context.json"),
            "pattern_memory": read_json(pf / "intelligence" / "111_regression_pattern_memory.json"),
            "contract_evidence": read_json(pf / "api_contract" / "201_contract_evidence.json"),
        }
        return self.inputs

    def _finding(
        self,
        *,
        finding_id: str,
        severity: str,
        contract_name_or_component: str,
        field_path: str,
        risk_type: str,
        expected_value_or_type: str,
        observed_value_or_type: str,
        threshold_or_rule_triggered: str,
        recommended_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "contract_name_or_component": contract_name_or_component,
            "field_path": field_path,
            "risk_type": risk_type,
            "expected_value_or_type": expected_value_or_type,
            "observed_value_or_type": observed_value_or_type,
            "threshold_or_rule_triggered": threshold_or_rule_triggered,
            "recommended_actions": list(recommended_actions),
        }

    def run_analysis(self) -> dict[str, Any]:
        config = self.inputs.get("config", {}) if isinstance(self.inputs.get("config", {}), dict) else {}
        strict_unknown_fields = _as_bool(config.get("strict_unknown_fields", _DEFAULT_CONFIG["strict_unknown_fields"]), True)
        max_version_drift_minor = _safe_int(config.get("max_version_drift_minor", _DEFAULT_CONFIG["max_version_drift_minor"]))
        fail_nullability = _as_bool(config.get("treat_nullability_violation_as_fail", _DEFAULT_CONFIG["treat_nullability_violation_as_fail"]), True)
        fail_type = _as_bool(config.get("treat_type_mismatch_as_fail", _DEFAULT_CONFIG["treat_type_mismatch_as_fail"]), True)
        fail_missing = _as_bool(config.get("treat_missing_required_field_as_fail", _DEFAULT_CONFIG["treat_missing_required_field_as_fail"]), True)

        contract_payload = self.inputs.get("contract_evidence", {}) if isinstance(self.inputs.get("contract_evidence", {}), dict) else {}
        contracts = [row for row in contract_payload.get("contracts", []) if isinstance(row, dict)]

        if not contracts:
            component_ctx = self.inputs.get("component_history_context", {}) if isinstance(self.inputs.get("component_history_context", {}), dict) else {}
            for row in _schema_rows(component_ctx):
                contract_name = str(row.get("component", "")).strip()
                if not contract_name:
                    continue
                expected_fields = row.get("expected_contract_fields", []) if isinstance(row.get("expected_contract_fields", []), list) else []
                observed_payload = row.get("observed_payload", {}) if isinstance(row.get("observed_payload", {}), dict) else {}
                if expected_fields or observed_payload:
                    contracts.append(
                        {
                            "contract_name": contract_name,
                            "expected_fields": expected_fields,
                            "observed_payload": observed_payload,
                            "caller_version": str(row.get("caller_version", "1.0.0")),
                            "callee_version": str(row.get("callee_version", "1.0.0")),
                            "strict_unknown_fields": strict_unknown_fields,
                        }
                    )

        required_field_findings: list[dict[str, Any]] = []
        type_mismatch_findings: list[dict[str, Any]] = []
        unknown_field_findings: list[dict[str, Any]] = []
        version_drift_findings: list[dict[str, Any]] = []
        shape_findings: list[dict[str, Any]] = []

        for contract in contracts:
            contract_name = str(contract.get("contract_name", contract.get("component", "unknown_contract"))).strip() or "unknown_contract"
            expected_fields = contract.get("expected_fields", []) if isinstance(contract.get("expected_fields", []), list) else []
            observed_payload = contract.get("observed_payload", {}) if isinstance(contract.get("observed_payload", {}), dict) else {}
            strict_mode = _as_bool(contract.get("strict_unknown_fields", strict_unknown_fields), strict_unknown_fields)
            expected_map = _expected_map([row for row in expected_fields if isinstance(row, dict)])

            for field_path, spec in expected_map.items():
                expected_type = str(spec.get("type", spec.get("expected_type", "any"))).strip() or "any"
                required = _as_bool(spec.get("required", False), False)
                nullable = _as_bool(spec.get("nullable", True), True)
                allowed_values = spec.get("enum", spec.get("allowed_values", []))
                enum_values = [str(item) for item in allowed_values] if isinstance(allowed_values, list) else []

                exists = field_path in observed_payload
                observed_value = observed_payload.get(field_path) if exists else None

                if required and not exists:
                    required_field_findings.append(
                        self._finding(
                            finding_id=f"MISSING_REQUIRED_FIELD_{_slug(contract_name)}_{_slug(field_path)}",
                            severity="FAIL" if fail_missing else "WARNING",
                            contract_name_or_component=contract_name,
                            field_path=field_path,
                            risk_type="MISSING_REQUIRED_FIELD",
                            expected_value_or_type=expected_type,
                            observed_value_or_type="<missing>",
                            threshold_or_rule_triggered="required_field_missing",
                            recommended_actions=[
                                "add missing required field in caller payload",
                                "perform explicit contract review for this component boundary",
                            ],
                        )
                    )
                    continue

                if exists and observed_value is None and not nullable:
                    type_mismatch_findings.append(
                        self._finding(
                            finding_id=f"NULLABILITY_VIOLATION_{_slug(contract_name)}_{_slug(field_path)}",
                            severity="FAIL" if fail_nullability else "WARNING",
                            contract_name_or_component=contract_name,
                            field_path=field_path,
                            risk_type="NULLABILITY_VIOLATION",
                            expected_value_or_type="non-null",
                            observed_value_or_type="null",
                            threshold_or_rule_triggered="non_nullable_field_was_null",
                            recommended_actions=[
                                "add nullable handling or tighten non-null guarantees",
                                "align caller type with contract schema",
                            ],
                        )
                    )

                if exists and observed_value is not None and expected_type != "any":
                    observed_type = _type_name(observed_value)
                    type_aliases = {
                        "string": "str",
                        "str": "str",
                        "integer": "int",
                        "int": "int",
                        "number": "float",
                        "float": "float",
                        "boolean": "bool",
                        "bool": "bool",
                        "object": "dict",
                        "dict": "dict",
                        "array": "list",
                        "list": "list",
                    }
                    normalized_expected = type_aliases.get(expected_type.lower(), expected_type.lower())
                    normalized_observed = type_aliases.get(observed_type.lower(), observed_type.lower())
                    if normalized_expected != normalized_observed:
                        type_mismatch_findings.append(
                            self._finding(
                                finding_id=f"TYPE_MISMATCH_{_slug(contract_name)}_{_slug(field_path)}",
                                severity="FAIL" if fail_type else "WARNING",
                                contract_name_or_component=contract_name,
                                field_path=field_path,
                                risk_type="TYPE_MISMATCH",
                                expected_value_or_type=normalized_expected,
                                observed_value_or_type=normalized_observed,
                                threshold_or_rule_triggered="field_type_mismatch",
                                recommended_actions=[
                                    "align caller type with contract schema",
                                    "perform explicit contract review for this component boundary",
                                ],
                            )
                        )

                if exists and enum_values:
                    observed_text = str(observed_value)
                    if observed_text not in enum_values:
                        type_mismatch_findings.append(
                            self._finding(
                                finding_id=f"ENUM_VALUE_VIOLATION_{_slug(contract_name)}_{_slug(field_path)}",
                                severity="FAIL",
                                contract_name_or_component=contract_name,
                                field_path=field_path,
                                risk_type="ENUM_VALUE_VIOLATION",
                                expected_value_or_type="|".join(enum_values),
                                observed_value_or_type=observed_text,
                                threshold_or_rule_triggered="value_not_in_allowed_enum_set",
                                recommended_actions=[
                                    "update enum/value mapping",
                                    "align caller type with contract schema",
                                ],
                            )
                        )

                if exists and isinstance(spec.get("shape", {}), dict):
                    expected_shape = spec.get("shape", {}) if isinstance(spec.get("shape", {}), dict) else {}
                    if expected_shape and isinstance(observed_value, dict):
                        expected_keys = {str(key) for key in expected_shape.keys()}
                        observed_keys = {str(key) for key in observed_value.keys()}
                        missing_keys = sorted(expected_keys - observed_keys)
                        if missing_keys:
                            shape_findings.append(
                                self._finding(
                                    finding_id=f"PAYLOAD_SHAPE_INCOMPATIBILITY_{_slug(contract_name)}_{_slug(field_path)}",
                                    severity="FAIL",
                                    contract_name_or_component=contract_name,
                                    field_path=field_path,
                                    risk_type="PAYLOAD_SHAPE_INCOMPATIBILITY",
                                    expected_value_or_type=",".join(sorted(expected_keys)),
                                    observed_value_or_type=",".join(sorted(observed_keys)),
                                    threshold_or_rule_triggered="nested_shape_missing_required_keys",
                                    recommended_actions=[
                                        "align caller type with contract schema",
                                        "perform explicit contract review for this component boundary",
                                    ],
                                )
                            )

            if strict_mode:
                for observed_field in sorted(observed_payload.keys()):
                    if str(observed_field) not in expected_map:
                        unknown_field_findings.append(
                            self._finding(
                                finding_id=f"UNKNOWN_FIELD_VIOLATION_{_slug(contract_name)}_{_slug(str(observed_field))}",
                                severity="WARNING",
                                contract_name_or_component=contract_name,
                                field_path=str(observed_field),
                                risk_type="UNKNOWN_FIELD_VIOLATION",
                                expected_value_or_type="known_contract_field",
                                observed_value_or_type="unknown_field",
                                threshold_or_rule_triggered="strict_unknown_fields=true",
                                recommended_actions=[
                                    "remove or whitelist unknown field",
                                    "perform explicit contract review for this component boundary",
                                ],
                            )
                        )

            caller_version = str(contract.get("caller_version", "1.0.0"))
            callee_version = str(contract.get("callee_version", "1.0.0"))
            caller_major, caller_minor, _caller_patch = _parse_version(caller_version)
            callee_major, callee_minor, _callee_patch = _parse_version(callee_version)
            major_mismatch = caller_major != callee_major
            minor_drift = abs(caller_minor - callee_minor)
            if major_mismatch or minor_drift > max_version_drift_minor:
                severity = "FAIL" if major_mismatch else "WARNING"
                version_drift_findings.append(
                    self._finding(
                        finding_id=f"VERSION_DRIFT_WARNING_{_slug(contract_name)}",
                        severity=severity,
                        contract_name_or_component=contract_name,
                        field_path="contract_version",
                        risk_type="VERSION_DRIFT_WARNING",
                        expected_value_or_type=f"minor_drift<={max_version_drift_minor}",
                        observed_value_or_type=f"caller={caller_version},callee={callee_version}",
                        threshold_or_rule_triggered="contract_version_incompatible_or_drifted",
                        recommended_actions=[
                            "add version compatibility shim",
                            "bump contract version and update consumers",
                            "perform explicit contract review for this component boundary",
                        ],
                    )
                )

        all_findings = [
            *required_field_findings,
            *type_mismatch_findings,
            *unknown_field_findings,
            *version_drift_findings,
            *shape_findings,
        ]
        recommendations: list[dict[str, Any]] = []
        for row in all_findings:
            recommendations.append(
                {
                    "finding_id": str(row.get("finding_id", "")),
                    "severity": str(row.get("severity", "INFO")),
                    "contract_name_or_component": str(row.get("contract_name_or_component", "")),
                    "risk_type": str(row.get("risk_type", "")),
                    "recommended_actions": row.get("recommended_actions", []),
                }
            )

        fail_count = sum(1 for row in all_findings if str(row.get("severity", "INFO")).upper() == "FAIL")
        warning_count = sum(1 for row in all_findings if str(row.get("severity", "INFO")).upper() == "WARNING")
        status = "PASS"
        if fail_count > 0:
            status = "FAIL"
        elif warning_count > 0:
            status = "WARNING"

        self.analysis = {
            "status": status,
            "config": config,
            "findings": {
                "required_fields": required_field_findings,
                "type_mismatch": type_mismatch_findings,
                "unknown_fields": unknown_field_findings,
                "version_drift": version_drift_findings,
                "shape_incompatibility": shape_findings,
            },
            "recommendations": recommendations,
            "summary": {
                "finding_count": len(all_findings),
                "fail_count": fail_count,
                "warning_count": warning_count,
            },
        }
        return self.analysis

    def generate_artifacts(self, output_dir: Path) -> list[str]:
        contract_dir = output_dir.parent / "api_contract" / "api_contract"
        # Remove legacy placeholder artifacts from older stub runs so bundles reflect live plugin output.
        stale_candidates = [
            output_dir / "not_implemented.json",
            output_dir / "api_contract" / "not_implemented.json",
            contract_dir / "not_implemented.json",
        ]
        for stale_path in stale_candidates:
            try:
                if stale_path.is_file():
                    stale_path.unlink()
            except OSError:
                pass

        findings = self.analysis.get("findings", {}) if isinstance(self.analysis.get("findings", {}), dict) else {}
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        required_rows = findings.get("required_fields", []) if isinstance(findings.get("required_fields", []), list) else []
        type_rows = findings.get("type_mismatch", []) if isinstance(findings.get("type_mismatch", []), list) else []
        unknown_rows = findings.get("unknown_fields", []) if isinstance(findings.get("unknown_fields", []), list) else []
        version_rows = findings.get("version_drift", []) if isinstance(findings.get("version_drift", []), list) else []
        shape_rows = findings.get("shape_incompatibility", []) if isinstance(findings.get("shape_incompatibility", []), list) else []
        recommendation_rows = self.analysis.get("recommendations", []) if isinstance(self.analysis.get("recommendations", []), list) else []

        write_json(contract_dir / "260_required_field_report.json", {"rows": required_rows, "summary": summary})
        write_json(contract_dir / "261_type_mismatch_report.json", {"rows": [*type_rows, *shape_rows], "summary": summary})
        write_json(contract_dir / "262_unknown_field_report.json", {"rows": unknown_rows, "summary": summary})
        write_json(contract_dir / "263_version_drift_report.json", {"rows": version_rows, "summary": summary})
        write_json(contract_dir / "264_contract_recommendations.json", {"rows": recommendation_rows, "summary": summary})

        lines = [
            "# API Contract Validation Summary",
            "",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- finding_count: {summary.get('finding_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Top Findings",
        ]
        top_rows = sorted(
            [*required_rows, *type_rows, *unknown_rows, *version_rows, *shape_rows],
            key=lambda row: (
                str(row.get("severity", "INFO")) != "FAIL",
                str(row.get("severity", "INFO")) != "WARNING",
                str(row.get("finding_id", "")),
            ),
        )
        if top_rows:
            for row in top_rows[:20]:
                lines.append(
                    "- finding_id="
                    + str(row.get("finding_id", ""))
                    + " severity="
                    + str(row.get("severity", ""))
                    + " contract="
                    + str(row.get("contract_name_or_component", ""))
                    + " field="
                    + str(row.get("field_path", ""))
                    + " risk_type="
                    + str(row.get("risk_type", ""))
                )
        else:
            lines.append("- no api contract misuse findings detected")

        write_text(contract_dir / "265_contract_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/api_contract/api_contract/260_required_field_report.json",
            "validation_plugins/api_contract/api_contract/261_type_mismatch_report.json",
            "validation_plugins/api_contract/api_contract/262_unknown_field_report.json",
            "validation_plugins/api_contract/api_contract/263_version_drift_report.json",
            "validation_plugins/api_contract/api_contract/264_contract_recommendations.json",
            "validation_plugins/api_contract/api_contract/265_contract_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"findings={summary.get('finding_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
