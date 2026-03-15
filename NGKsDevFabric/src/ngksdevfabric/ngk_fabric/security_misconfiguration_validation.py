from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text

_DEFAULT_CONFIG = {
    "treat_hard_coded_secret_as_fail": True,
    "treat_insecure_protocol_as_fail": True,
    "treat_weak_crypto_as_fail": True,
    "allow_local_admin_interface": True,
    "strict_header_requirements": True,
}

_REQUIRED_SECURITY_HEADERS = [
    "x-frame-options",
    "content-security-policy",
    "x-content-type-options",
]

_SECRET_KEYWORDS = ["api_key", "password", "secret", "token"]
_INSECURE_PROTOCOL_PATTERN = re.compile(r"(?i)(http://|ftp://|telnet)")
_WEAK_CRYPTO_PATTERN = re.compile(r"(?i)\b(md5|sha1|des)\b")
_SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|password|secret|token)\b\s*[:=]\s*[^\s,;]+")


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


def _is_secret_value(value: object) -> bool:
    text = str(value).strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith("${") and lowered.endswith("}"):
        return False
    if lowered.startswith("env(") and lowered.endswith(")"):
        return False
    return True


def _local_host(value: str) -> bool:
    host = str(value).strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _headers_from_entry(entry: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    header_sources: list[object] = [entry.get("headers"), entry.get("security_headers")]
    for source in header_sources:
        if isinstance(source, dict):
            for key in source.keys():
                out.add(str(key).strip().lower())
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    out.add(str(item.get("name", "")).strip().lower())
                else:
                    out.add(str(item).strip().lower())
    return {item for item in out if item}


def _text_payload(entry: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("content", "config_text", "raw_text", "snippet"):
        if str(entry.get(key, "")).strip():
            chunks.append(str(entry.get(key, "")))

    settings = entry.get("settings", {}) if isinstance(entry.get("settings", {}), dict) else {}
    if settings:
        for key, value in settings.items():
            chunks.append(f"{key}={value}")

    return "\n".join(chunks)


class SecurityMisconfigurationValidationPlugin(ValidationPlugin):
    plugin_name = "security_misconfiguration_validation"
    plugin_version = "1.0.0"
    plugin_category = "SECURITY_CONFIGURATION_VALIDATION"

    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        self.context = dict(context)
        project_root = Path(str(context.get("project_root", "."))).resolve()
        pf = Path(str(context.get("pf", "."))).resolve()

        config_path = (project_root / "security_validation_config.json").resolve()
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
            "component_history_context": read_json(pf / "history" / "43_component_history_context.json"),
            "pattern_memory": read_json(pf / "intelligence" / "111_regression_pattern_memory.json"),
            "security_evidence": read_json(pf / "security" / "201_security_configuration_evidence.json"),
        }
        return self.inputs

    def _finding(
        self,
        *,
        finding_id: str,
        severity: str,
        component_or_target: str,
        source_path: str,
        risk_type: str,
        observed_value: str,
        threshold_or_rule_triggered: str,
        recommended_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "finding_id": finding_id,
            "severity": severity,
            "component_or_target": component_or_target,
            "source_path": source_path,
            "risk_type": risk_type,
            "observed_value": observed_value,
            "threshold_or_rule_triggered": threshold_or_rule_triggered,
            "recommended_actions": list(recommended_actions),
        }

    def run_analysis(self) -> dict[str, Any]:
        config = self.inputs.get("config", {}) if isinstance(self.inputs.get("config", {}), dict) else {}
        fail_secret = _as_bool(config.get("treat_hard_coded_secret_as_fail", _DEFAULT_CONFIG["treat_hard_coded_secret_as_fail"]), True)
        fail_protocol = _as_bool(config.get("treat_insecure_protocol_as_fail", _DEFAULT_CONFIG["treat_insecure_protocol_as_fail"]), True)
        fail_crypto = _as_bool(config.get("treat_weak_crypto_as_fail", _DEFAULT_CONFIG["treat_weak_crypto_as_fail"]), True)
        allow_local_admin = _as_bool(config.get("allow_local_admin_interface", _DEFAULT_CONFIG["allow_local_admin_interface"]), True)
        strict_headers = _as_bool(config.get("strict_header_requirements", _DEFAULT_CONFIG["strict_header_requirements"]), True)

        security_payload = self.inputs.get("security_evidence", {}) if isinstance(self.inputs.get("security_evidence", {}), dict) else {}
        rows = [row for row in security_payload.get("entries", []) if isinstance(row, dict)]

        if not rows:
            component_ctx = self.inputs.get("component_history_context", {}) if isinstance(self.inputs.get("component_history_context", {}), dict) else {}
            for row in component_ctx.get("rows", []):
                if not isinstance(row, dict):
                    continue
                source_path = str(row.get("source_path", row.get("component", "component_history"))).strip()
                candidate = {
                    "component": str(row.get("component", source_path)).strip() or "component_history",
                    "source_path": source_path or "component_history",
                    "content": str(row.get("config_text", row.get("raw_text", row.get("observed_payload", "")))),
                    "settings": row.get("settings", {}) if isinstance(row.get("settings", {}), dict) else {},
                    "headers": row.get("headers", []),
                }
                rows.append(candidate)

        secret_findings: list[dict[str, Any]] = []
        protocol_findings: list[dict[str, Any]] = []
        crypto_findings: list[dict[str, Any]] = []
        admin_findings: list[dict[str, Any]] = []
        access_findings: list[dict[str, Any]] = []
        header_findings: list[dict[str, Any]] = []

        for row in rows:
            component = str(row.get("component", row.get("target", "unknown_component"))).strip() or "unknown_component"
            source_path = str(row.get("source_path", row.get("path", component))).strip() or component
            settings = row.get("settings", {}) if isinstance(row.get("settings", {}), dict) else {}
            payload_text = _text_payload(row)

            if _SECRET_PATTERN.search(payload_text):
                secret_findings.append(
                    self._finding(
                        finding_id=f"HARD_CODED_SECRET_{_slug(component)}_{_slug(source_path)}",
                        severity="FAIL" if fail_secret else "WARNING",
                        component_or_target=component,
                        source_path=source_path,
                        risk_type="HARD_CODED_SECRET",
                        observed_value="inline credential-like token",
                        threshold_or_rule_triggered="secret keyword with concrete value",
                        recommended_actions=[
                            "move secrets to environment-backed secret manager",
                            "rotate exposed credentials",
                        ],
                    )
                )
            else:
                for key, value in settings.items():
                    key_l = str(key).strip().lower()
                    if any(word in key_l for word in _SECRET_KEYWORDS) and _is_secret_value(value):
                        secret_findings.append(
                            self._finding(
                                finding_id=f"HARD_CODED_SECRET_{_slug(component)}_{_slug(source_path)}_{_slug(key_l)}",
                                severity="FAIL" if fail_secret else "WARNING",
                                component_or_target=component,
                                source_path=source_path,
                                risk_type="HARD_CODED_SECRET",
                                observed_value=f"{key}={value}",
                                threshold_or_rule_triggered="secret-like key contains concrete value",
                                recommended_actions=[
                                    "move secrets to environment-backed secret manager",
                                    "rotate exposed credentials",
                                ],
                            )
                        )

            if _INSECURE_PROTOCOL_PATTERN.search(payload_text):
                protocol_findings.append(
                    self._finding(
                        finding_id=f"INSECURE_PROTOCOL_USAGE_{_slug(component)}_{_slug(source_path)}",
                        severity="FAIL" if fail_protocol else "WARNING",
                        component_or_target=component,
                        source_path=source_path,
                        risk_type="INSECURE_PROTOCOL_USAGE",
                        observed_value="http/ftp/telnet endpoint detected",
                        threshold_or_rule_triggered="insecure transport protocol reference",
                        recommended_actions=[
                            "replace insecure protocols with tls-protected alternatives",
                            "enforce secure URL scheme validation",
                        ],
                    )
                )

            if _WEAK_CRYPTO_PATTERN.search(payload_text):
                crypto_findings.append(
                    self._finding(
                        finding_id=f"WEAK_CRYPTO_CONFIGURATION_{_slug(component)}_{_slug(source_path)}",
                        severity="FAIL" if fail_crypto else "WARNING",
                        component_or_target=component,
                        source_path=source_path,
                        risk_type="WEAK_CRYPTO_CONFIGURATION",
                        observed_value="md5/sha1/des detected",
                        threshold_or_rule_triggered="weak cryptographic primitive configured",
                        recommended_actions=[
                            "upgrade to modern cryptographic algorithms",
                            "remove deprecated hashing and cipher usage",
                        ],
                    )
                )

            admin_host = str(settings.get("admin_host", row.get("admin_host", ""))).strip()
            admin_port = str(settings.get("admin_port", row.get("admin_port", ""))).strip().lower()
            public_admin_host = admin_host in {"0.0.0.0", "::"}
            open_admin_port = admin_port in {"open", "public", "any"}
            if public_admin_host or open_admin_port:
                if not (allow_local_admin and _local_host(admin_host)):
                    admin_findings.append(
                        self._finding(
                            finding_id=f"PUBLIC_EXPOSED_ADMIN_INTERFACE_{_slug(component)}_{_slug(source_path)}",
                            severity="FAIL",
                            component_or_target=component,
                            source_path=source_path,
                            risk_type="PUBLIC_EXPOSED_ADMIN_INTERFACE",
                            observed_value=f"admin_host={admin_host};admin_port={admin_port}",
                            threshold_or_rule_triggered="admin interface exposed without restriction",
                            recommended_actions=[
                                "bind admin interface to local or private network only",
                                "restrict admin port exposure via firewall and authn controls",
                            ],
                        )
                    )

            allow_all = _as_bool(settings.get("allow_all", row.get("allow_all", False)), False)
            role_value = str(settings.get("role", row.get("role", ""))).strip()
            if allow_all or role_value == "*":
                access_findings.append(
                    self._finding(
                        finding_id=f"PERMISSIVE_ACCESS_POLICY_{_slug(component)}_{_slug(source_path)}",
                        severity="FAIL",
                        component_or_target=component,
                        source_path=source_path,
                        risk_type="PERMISSIVE_ACCESS_POLICY",
                        observed_value=f"allow_all={allow_all};role={role_value}",
                        threshold_or_rule_triggered="wildcard or allow-all policy detected",
                        recommended_actions=[
                            "replace wildcard permissions with least-privilege roles",
                            "disable allow-all policy defaults",
                        ],
                    )
                )

            if strict_headers:
                present_headers = _headers_from_entry(row)
                missing_headers = [header for header in _REQUIRED_SECURITY_HEADERS if header not in present_headers]
                if missing_headers:
                    header_findings.append(
                        self._finding(
                            finding_id=f"MISSING_SECURITY_HEADERS_{_slug(component)}_{_slug(source_path)}",
                            severity="FAIL",
                            component_or_target=component,
                            source_path=source_path,
                            risk_type="MISSING_SECURITY_HEADERS",
                            observed_value=",".join(missing_headers),
                            threshold_or_rule_triggered="required response security headers missing",
                            recommended_actions=[
                                "configure required response security headers",
                                "add gateway policy to enforce security headers",
                            ],
                        )
                    )

        all_findings = [
            *secret_findings,
            *protocol_findings,
            *crypto_findings,
            *admin_findings,
            *access_findings,
            *header_findings,
        ]
        recommendations = [
            {
                "finding_id": str(row.get("finding_id", "")),
                "severity": str(row.get("severity", "INFO")),
                "component_or_target": str(row.get("component_or_target", "")),
                "risk_type": str(row.get("risk_type", "")),
                "recommended_actions": row.get("recommended_actions", []),
            }
            for row in all_findings
        ]

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
                "hard_coded_secret": secret_findings,
                "insecure_protocol": protocol_findings,
                "weak_crypto": crypto_findings,
                "admin_interface": admin_findings,
                "permissive_access": access_findings,
                "missing_headers": header_findings,
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
        security_dir = output_dir.parent / "security"
        findings = self.analysis.get("findings", {}) if isinstance(self.analysis.get("findings", {}), dict) else {}
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}

        secret_rows = findings.get("hard_coded_secret", []) if isinstance(findings.get("hard_coded_secret", []), list) else []
        protocol_rows = findings.get("insecure_protocol", []) if isinstance(findings.get("insecure_protocol", []), list) else []
        crypto_rows = findings.get("weak_crypto", []) if isinstance(findings.get("weak_crypto", []), list) else []
        admin_rows = findings.get("admin_interface", []) if isinstance(findings.get("admin_interface", []), list) else []
        access_rows = findings.get("permissive_access", []) if isinstance(findings.get("permissive_access", []), list) else []
        header_rows = findings.get("missing_headers", []) if isinstance(findings.get("missing_headers", []), list) else []
        recommendation_rows = self.analysis.get("recommendations", []) if isinstance(self.analysis.get("recommendations", []), list) else []

        write_json(security_dir / "270_secret_detection_report.json", {"rows": secret_rows, "summary": summary})
        write_json(security_dir / "271_protocol_security_report.json", {"rows": protocol_rows, "summary": summary})
        write_json(security_dir / "272_crypto_configuration_report.json", {"rows": crypto_rows, "summary": summary})
        write_json(security_dir / "273_admin_interface_report.json", {"rows": admin_rows, "summary": summary})
        write_json(security_dir / "274_access_policy_report.json", {"rows": access_rows, "summary": summary})
        write_json(security_dir / "275_security_headers_report.json", {"rows": header_rows, "summary": summary})
        write_json(security_dir / "276_security_recommendations.json", {"rows": recommendation_rows, "summary": summary})

        lines = [
            "# Security Misconfiguration Validation Summary",
            "",
            f"- plugin_status: {self.analysis.get('status', 'PASS')}",
            f"- finding_count: {summary.get('finding_count', 0)}",
            f"- fail_count: {summary.get('fail_count', 0)}",
            f"- warning_count: {summary.get('warning_count', 0)}",
            "",
            "## Top Findings",
        ]
        top_rows = sorted(
            [*secret_rows, *protocol_rows, *crypto_rows, *admin_rows, *access_rows, *header_rows],
            key=lambda row: (
                str(row.get("severity", "INFO")) != "FAIL",
                str(row.get("severity", "INFO")) != "WARNING",
                str(row.get("finding_id", "")),
            ),
        )
        if top_rows:
            for row in top_rows[:25]:
                lines.append(
                    "- finding_id="
                    + str(row.get("finding_id", ""))
                    + " severity="
                    + str(row.get("severity", ""))
                    + " component="
                    + str(row.get("component_or_target", ""))
                    + " source="
                    + str(row.get("source_path", ""))
                    + " risk_type="
                    + str(row.get("risk_type", ""))
                )
        else:
            lines.append("- no security misconfiguration findings detected")

        write_text(security_dir / "277_security_summary.md", "\n".join(lines) + "\n")

        return [
            "validation_plugins/security/270_secret_detection_report.json",
            "validation_plugins/security/271_protocol_security_report.json",
            "validation_plugins/security/272_crypto_configuration_report.json",
            "validation_plugins/security/273_admin_interface_report.json",
            "validation_plugins/security/274_access_policy_report.json",
            "validation_plugins/security/275_security_headers_report.json",
            "validation_plugins/security/276_security_recommendations.json",
            "validation_plugins/security/277_security_summary.md",
        ]

    def generate_summary(self) -> str:
        summary = self.analysis.get("summary", {}) if isinstance(self.analysis.get("summary", {}), dict) else {}
        return (
            f"plugin={self.plugin_name} status={self.analysis.get('status', 'PASS')} "
            f"findings={summary.get('finding_count', 0)} fails={summary.get('fail_count', 0)} warnings={summary.get('warning_count', 0)}"
        )
