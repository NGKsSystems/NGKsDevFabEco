from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certification_policy_surface import evaluate_structural_certification_state, evaluate_target_capability_state
from .certification_status import inspect_certification_status
from .certification_target import run_target_validation_precheck


@dataclass(frozen=True)
class EnforcementFinding:
    code: str
    severity: str
    message: str
    evidence: str


@dataclass(frozen=True)
class CertificationEnforcementResult:
    project_root: Path
    enforcement_state: str
    allow_execution: bool
    target_state: str
    structural_state: str
    block_count: int
    warning_count: int
    info_count: int
    findings: list[EnforcementFinding]
    status_json_path: Path
    report_txt_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "enforcement_state": self.enforcement_state,
            "allow_execution": self.allow_execution,
            "target_state": self.target_state,
            "structural_state": self.structural_state,
            "block_count": self.block_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "findings": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "evidence": item.evidence,
                }
                for item in self.findings
            ],
            "status_json_path": str(self.status_json_path),
            "report_txt_path": str(self.report_txt_path),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _is_non_blocking_warning(code: str) -> bool:
    return code.startswith("missing_optional_artifact:") or code.startswith("optional_subtarget_warning:")


def run_certification_enforcement(*, project_root: Path, pf: Path, require_contract: bool = True) -> CertificationEnforcementResult:
    project_root = project_root.resolve()
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)

    target_result = run_target_validation_precheck(
        project_root=project_root,
        pf=pf,
        explicit_contract_path=None,
        require_contract=require_contract,
    )
    structural_result = inspect_certification_status(project_root)

    findings: list[EnforcementFinding] = []

    target_policy = evaluate_target_capability_state(target_result.state)
    if not target_policy.allow:
        findings.append(
            EnforcementFinding(
                code=f"target_policy:{target_policy.reason_code}",
                severity="BLOCK",
                message=f"Target capability state blocks execution: {target_result.state}",
                evidence="certification_target.json + target_validation artifacts",
            )
        )

    structural_policy = evaluate_structural_certification_state(structural_result.state)
    if not structural_policy.allow:
        findings.append(
            EnforcementFinding(
                code=f"structural_policy:{structural_policy.reason_code}",
                severity="BLOCK",
                message=f"Structural certification state blocks execution: {structural_result.state}",
                evidence="certification status inspector",
            )
        )

    for item in target_result.errors:
        findings.append(
            EnforcementFinding(
                code=f"target_error:{item}",
                severity="BLOCK",
                message=f"Target validation error: {item}",
                evidence="target_validation/04_target_capability_classification.json",
            )
        )

    for item in target_result.warnings:
        severity = "WARNING" if _is_non_blocking_warning(item) else "BLOCK"
        findings.append(
            EnforcementFinding(
                code=f"target_warning:{item}",
                severity=severity,
                message=f"Target validation warning: {item}",
                evidence="target_validation/04_target_capability_classification.json",
            )
        )

    if structural_result.drift_detected:
        for reason in structural_result.drift_reasons:
            findings.append(
                EnforcementFinding(
                    code=f"structural_drift:{reason}",
                    severity="BLOCK",
                    message=f"Certification drift detected: {reason}",
                    evidence="certification_status_result",
                )
            )

    findings.append(
        EnforcementFinding(
            code="enforcement_preflight_executed",
            severity="INFO",
            message="Certification enforcement preflight executed before workflow run",
            evidence="certification_status.json",
        )
    )

    block_count = sum(1 for item in findings if item.severity == "BLOCK")
    warning_count = sum(1 for item in findings if item.severity == "WARNING")
    info_count = sum(1 for item in findings if item.severity == "INFO")
    allow_execution = block_count == 0
    enforcement_state = "CERTIFICATION_ENFORCED" if allow_execution else "CERTIFICATION_ENFORCED_BLOCKED"

    status_json_path = pf / "certification_status.json"
    report_txt_path = pf / "certification_report.txt"

    result = CertificationEnforcementResult(
        project_root=project_root,
        enforcement_state=enforcement_state,
        allow_execution=allow_execution,
        target_state=target_result.state,
        structural_state=structural_result.state,
        block_count=block_count,
        warning_count=warning_count,
        info_count=info_count,
        findings=sorted(findings, key=lambda item: (item.severity, item.code)),
        status_json_path=status_json_path,
        report_txt_path=report_txt_path,
    )

    _write_json(status_json_path, result.to_dict())

    report_lines = [
        "CERTIFICATION ENFORCEMENT REPORT",
        f"timestamp_utc={datetime.now(timezone.utc).isoformat()}",
        f"project_root={project_root}",
        f"enforcement_state={result.enforcement_state}",
        f"allow_execution={'true' if result.allow_execution else 'false'}",
        f"target_state={result.target_state}",
        f"structural_state={result.structural_state}",
        f"block_count={result.block_count}",
        f"warning_count={result.warning_count}",
        f"info_count={result.info_count}",
        "",
        "FINDINGS:",
    ]
    for item in result.findings:
        report_lines.append(f"- severity={item.severity} code={item.code} message={item.message} evidence={item.evidence}")

    _write_text(report_txt_path, "\n".join(report_lines) + "\n")
    return result
