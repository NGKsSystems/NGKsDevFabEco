from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .certification_status import inspect_certification_status
from .decision_replay_validator import validate_decision_chain_from_proof
from .feedback_replay_validator import validate_feedback_chain_from_proof
from .graph_state_manager import load_graph_state
from .workspace_integrity import run_workspace_integrity_check


_HEALTHY = "HEALTHY"
_HEALTHY_WARN = "HEALTHY_WITH_WARNINGS"
_ACTION_REQUIRED = "ACTION_REQUIRED"
_BLOCKED = "BLOCKED"
_UNKNOWN = "UNKNOWN"


def _normalize_reason_code(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "unknown_finding"
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch == "_":
            cleaned.append(ch)
        elif ch in {"-", " ", ".", "/"}:
            cleaned.append("_")
    normalized = "".join(cleaned).strip("_")
    return normalized or "unknown_finding"


def _default_stable_id(reason_code: str) -> str:
    token = _normalize_reason_code(reason_code).upper()
    return f"PHLTH_{token}"


# Stable mapping for finding identity and automation-facing metadata.
# This does not change finding generation logic or state classification.
_FINDING_REASON_CATALOG: dict[str, dict[str, str]] = {
    "workspace_integrity_failed": {
        "id": "PHLTH_001",
        "source": "workspace_integrity_check",
        "evidence_ref": "workspace_integrity_check:project_health_scope",
        "recommended_action": "Resolve workspace integrity violations and re-run project-health.",
    },
    "workspace_integrity_unknown": {
        "id": "PHLTH_002",
        "source": "workspace_integrity_check",
        "evidence_ref": "workspace_integrity_check_exception",
        "recommended_action": "Inspect workspace integrity execution errors and re-run project-health.",
    },
    "certification_status_unknown": {
        "id": "PHLTH_003",
        "source": "certification_status",
        "evidence_ref": "certification_status_read_failure",
        "recommended_action": "Verify certification artifacts are readable and retry.",
    },
    "certification_missing_certification_structure": {
        "id": "PHLTH_004",
        "source": "certification_status",
        "evidence_ref": "certification_target.json|certification/",
        "recommended_action": "Run bootstrap-certification to initialize certification structure.",
    },
    "certification_bootstrap_placeholder_only": {
        "id": "PHLTH_005",
        "source": "certification_status",
        "evidence_ref": "certification/bootstrap_placeholder_assets",
        "recommended_action": "Run certify to replace placeholder-only state with real evidence.",
    },
    "certification_partial_certification_drift": {
        "id": "PHLTH_006",
        "source": "certification_status",
        "evidence_ref": "certification/drift_markers",
        "recommended_action": "Repair certification drift and re-run certify.",
    },
    "certification_structurally_ready_without_evidence": {
        "id": "PHLTH_007",
        "source": "certification_status",
        "evidence_ref": "certification_state:CERTIFICATION_STRUCTURALLY_READY",
        "recommended_action": "Run certification to produce or confirm real evidence.",
    },
    "control_plane_propagation_partial": {
        "id": "PHLTH_008",
        "source": "control_plane_artifacts",
        "evidence_ref": "control_plane/67-70_propagation_files",
        "recommended_action": "Complete propagation artifact generation and re-run health check.",
    },
    "control_plane_decision_envelope_absent": {
        "id": "PHLTH_009",
        "source": "control_plane_artifacts",
        "evidence_ref": "control_plane/58_decision_envelope_chain.json",
        "recommended_action": "Run a full workflow that produces decision envelope artifacts.",
    },
    "replay_validation_failed": {
        "id": "PHLTH_010",
        "source": "decision_replay_validator",
        "evidence_ref": "control_plane/58_decision_envelope_chain.json|control_plane/65_outcome_feedback_chain.json",
        "recommended_action": "Run certify-validate and inspect replay validation outputs.",
    },
    "replay_validator_unavailable": {
        "id": "PHLTH_011",
        "source": "decision_replay_validator",
        "evidence_ref": "replay_validator_exception",
        "recommended_action": "Inspect replay validator availability and dependencies.",
    },
    "graph_state_unknown": {
        "id": "PHLTH_012",
        "source": "graph_state_manager",
        "evidence_ref": ".graph_state/graph_state.json",
        "recommended_action": "Refresh or regenerate graph state artifacts.",
    },
    "graph_state_dirty": {
        "id": "PHLTH_013",
        "source": "graph_state_manager",
        "evidence_ref": ".graph_state/graph_state.json",
        "recommended_action": "Run graph refresh/update to clear dirty state.",
    },
    "capability_not_ready": {
        "id": "PHLTH_014",
        "source": "target_capability_probe",
        "evidence_ref": "certification_target.json|certification/baseline_v1|certification/scenario_index.json",
        "recommended_action": "Initialize missing capability prerequisites before certify.",
    },
    "capability_unknown": {
        "id": "PHLTH_015",
        "source": "target_capability_probe",
        "evidence_ref": "capability_probe_exception",
        "recommended_action": "Inspect capability probe failures and retry.",
    },
}


def _apply_finding_normalization(finding: dict[str, Any]) -> None:
    reason_code = _normalize_reason_code(str(finding.get("code", "")))
    catalog = _FINDING_REASON_CATALOG.get(reason_code, {})

    finding["reason_code"] = reason_code
    finding["id"] = str(catalog.get("id") or _default_stable_id(reason_code))
    finding["source"] = str(catalog.get("source") or finding.get("lane") or "project_health")
    finding["evidence_ref"] = str(catalog.get("evidence_ref") or "not_available")
    finding["recommended_action"] = str(catalog.get("recommended_action") or "Review finding evidence and resolve lane-specific issue.")

# Codes whose warnings are actionable (drive ACTION_REQUIRED state).
_ACTIONABLE_WARNING_CODES: frozenset[str] = frozenset({
    "graph_state_dirty",
    "replay_validation_failed",
    "replay_validator_unavailable",
})

# Operator-facing semantics for each overall health state.
# These are display-only; they do not affect classification logic.
_STATE_SEMANTICS: dict[str, dict[str, str]] = {
    _HEALTHY: {
        "meaning": (
            "All evaluated readiness and integrity lanes pass with no outstanding issues."
        ),
        "non_meaning": (
            "Does not guarantee control-plane artifacts are fully populated "
            "or that certification has been exercised end-to-end."
        ),
        "typical_triggers": (
            "Graph clean, certification evidence present, replay PASS, "
            "workspace integrity OK, capability READY."
        ),
        "urgency": "NONE",
        "recommended_next_action": (
            "No action required. Project is ready for certification and build workflows."
        ),
    },
    _HEALTHY_WARN: {
        "meaning": (
            "All structural gates pass but one or more advisory lane signals "
            "are present and warrant attention."
        ),
        "non_meaning": (
            "Does not block certification workflows. Warnings are advisory and "
            "do not prevent certification or build pipelines from running."
        ),
        "typical_triggers": (
            "Certification is structurally ready but real run evidence is not confirmed yet. "
            "Non-actionable graph or capability advisories present."
        ),
        "urgency": "LOW",
        "recommended_next_action": (
            "Review warning findings and resolve advisories before the next certification cycle."
        ),
    },
    _ACTION_REQUIRED: {
        "meaning": (
            "No hard blockers, but specific actionable conditions require operator attention "
            "before certification or build workflows should proceed."
        ),
        "non_meaning": (
            "Does not indicate the project is structurally broken or that "
            "certification artifacts are invalid."
        ),
        "typical_triggers": (
            "Graph state is dirty or stale. Replay validation failed or validator unavailable."
        ),
        "urgency": "MEDIUM",
        "recommended_next_action": (
            "Resolve actionable findings: refresh graph state and/or re-run certify-validate "
            "to restore replay integrity before proceeding."
        ),
    },
    _BLOCKED: {
        "meaning": (
            "One or more hard certification or workspace prerequisites are missing or invalid. "
            "Certification and build workflows must not proceed."
        ),
        "non_meaning": (
            "Does not mean data is permanently corrupted. Blockers must be resolved "
            "before certification workflows can run."
        ),
        "typical_triggers": (
            "Missing certification structure, bootstrap placeholder artifacts only, "
            "certification drift detected, workspace integrity failed, "
            "capability prerequisites not met."
        ),
        "urgency": "HIGH",
        "recommended_next_action": (
            "Resolve all blocking findings. Run bootstrap-certification to initialize "
            "structure, or certify to re-establish evidence. Check workspace integrity."
        ),
    },
    _UNKNOWN: {
        "meaning": (
            "One or more core readiness lanes could not be evaluated. "
            "Project health cannot be determined."
        ),
        "non_meaning": (
            "Does not imply the project is healthy or unhealthy. "
            "Health state is indeterminate until lane errors are resolved."
        ),
        "typical_triggers": (
            "Workspace integrity check exception, graph state unreadable, "
            "capability detection failure, or missing project root configuration."
        ),
        "urgency": "MEDIUM",
        "recommended_next_action": (
            "Inspect lane configuration. Run a workspace integrity check and ensure "
            "graph state is initialized before re-evaluating project health."
        ),
    },
}


def _get_state_semantics(state: str) -> dict[str, str]:
    """Return operator-facing semantics for a given overall health state."""
    return _STATE_SEMANTICS.get(
        state,
        {
            "meaning": "Health state is not recognized.",
            "non_meaning": "",
            "typical_triggers": "",
            "urgency": "UNKNOWN",
            "recommended_next_action": "Inspect project-health configuration and re-run.",
        },
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _resolve_latest_proof_root(project_root: Path) -> Path | None:
    latest_pointer = project_root / "_proof" / "latest" / "latest_run_pointer.json"
    payload = _read_json(latest_pointer)
    proof_folder = str(payload.get("proof_folder", "")).strip()
    if proof_folder:
        candidate = Path(proof_folder).resolve()
        if candidate.is_dir():
            return candidate

    fallback = (project_root / "_proof" / "latest" / "run").resolve()
    if fallback.is_dir():
        return fallback
    return None


def _collect_workspace_lane() -> tuple[dict[str, str], list[dict[str, str]], bool]:
    findings: list[dict[str, str]] = []
    try:
        result, _ = run_workspace_integrity_check(scope="project_health", artifact_dir=None)
        integrity_state = "PASS" if result.ok else "FAIL"
        if not result.ok:
            findings.append(
                {
                    "severity": "blocking",
                    "code": "workspace_integrity_failed",
                    "message": "Workspace integrity check failed.",
                }
            )
        return {"integrity_state": integrity_state}, findings, False
    except Exception:
        findings.append(
            {
                "severity": "warning",
                "code": "workspace_integrity_unknown",
                "message": "Workspace integrity state could not be read.",
            }
        )
        return {"integrity_state": "UNKNOWN"}, findings, True


def _collect_certification_lane(project_root: Path) -> tuple[dict[str, str], list[dict[str, str]], bool]:
    findings: list[dict[str, str]] = []
    try:
        status = inspect_certification_status(project_root)
    except Exception:
        findings.append(
            {
                "severity": "warning",
                "code": "certification_status_unknown",
                "message": "Certification status could not be read.",
            }
        )
        return {
            "certification_state": "UNKNOWN",
            "placeholder_state": "UNKNOWN",
            "drift_state": "UNKNOWN",
        }, findings, True

    cert_state = str(status.state)
    placeholder_state = "BOOTSTRAP_PLACEHOLDER_ONLY" if cert_state == "BOOTSTRAP_PLACEHOLDER_ONLY" else "NO_PLACEHOLDER"
    drift_state = "DRIFT_DETECTED" if bool(status.drift_detected) or cert_state == "PARTIAL_CERTIFICATION_DRIFT" else "NO_DRIFT"

    if cert_state in {"MISSING_CERTIFICATION_STRUCTURE", "BOOTSTRAP_PLACEHOLDER_ONLY", "PARTIAL_CERTIFICATION_DRIFT"}:
        findings.append(
            {
                "severity": "blocking",
                "code": f"certification_{cert_state.lower()}",
                "message": f"Certification state is {cert_state}.",
            }
        )
    elif cert_state == "CERTIFICATION_STRUCTURALLY_READY":
        findings.append(
            {
                "severity": "warning",
                "code": "certification_structurally_ready_without_evidence",
                "message": "Certification structure is ready but real evidence is not confirmed.",
            }
        )

    return {
        "certification_state": cert_state,
        "placeholder_state": placeholder_state,
        "drift_state": drift_state,
    }, findings, False


def _collect_control_plane_lane(project_root: Path) -> tuple[dict[str, str], list[dict[str, str]], Path | None]:
    findings: list[dict[str, str]] = []
    proof_root = _resolve_latest_proof_root(project_root)
    if proof_root is None:
        return {
            "decision_envelope": "ABSENT",
            "feedback_chain": "ABSENT",
            "propagation_set": "ABSENT",
            "certification_cp_summary": "ABSENT",
            "operational_cp_summary": "ABSENT",
            "explain_cp_summary": "ABSENT",
        }, findings, None

    cp = proof_root / "control_plane"
    decision = cp / "58_decision_envelope_chain.json"
    feedback = cp / "65_outcome_feedback_chain.json"
    prop_files = [
        cp / "67_confidence_propagation.json",
        cp / "68_recurrence_propagation.json",
        cp / "69_predictive_calibration_propagation.json",
        cp / "70_certification_impact_propagation.json",
    ]
    cert_cp = cp / "72_certification_control_plane_summary.json"
    op_cp = cp / "73_operational_control_plane_summary.json"
    explain_cp = cp / "74_explain_control_plane_summary.json"

    prop_count = sum(1 for p in prop_files if p.is_file())
    if prop_count == 4:
        propagation_state = "PRESENT"
    elif prop_count == 0:
        propagation_state = "ABSENT"
    else:
        propagation_state = "PARTIAL"
        findings.append(
            {
                "severity": "warning",
                "code": "control_plane_propagation_partial",
                "message": "Control-plane propagation set is partial.",
            }
        )

    lane = {
        "decision_envelope": "PRESENT" if decision.is_file() else "ABSENT",
        "feedback_chain": "PRESENT" if feedback.is_file() else "ABSENT",
        "propagation_set": propagation_state,
        "certification_cp_summary": "PRESENT" if cert_cp.is_file() else "ABSENT",
        "operational_cp_summary": "PRESENT" if op_cp.is_file() else "ABSENT",
        "explain_cp_summary": "PRESENT" if explain_cp.is_file() else "ABSENT",
    }

    if lane["decision_envelope"] == "ABSENT":
        findings.append(
            {
                "severity": "warning",
                "code": "control_plane_decision_envelope_absent",
                "message": "Decision envelope artifact is absent in the latest proof root.",
            }
        )

    return lane, findings, proof_root


def _collect_replay_lane(proof_root: Path | None, control_plane_lane: dict[str, str]) -> tuple[dict[str, str], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    lane = {
        "replay_validator_available": "YES",
        "replay_applicability": "CERTIFY_VALIDATE_ONLY",
        "replay_state": "NOT_EVALUATED",
    }

    if proof_root is None:
        lane["replay_state"] = "NOT_AVAILABLE"
        return lane, findings

    if control_plane_lane.get("decision_envelope") != "PRESENT":
        lane["replay_state"] = "NOT_AVAILABLE"
        return lane, findings

    try:
        decision_result = validate_decision_chain_from_proof(proof_root=proof_root)
        decision_status = str(decision_result.get("status", "FAIL")).upper()

        feedback_status = "NOT_EVALUATED"
        if control_plane_lane.get("feedback_chain") == "PRESENT":
            feedback_result = validate_feedback_chain_from_proof(proof_root=proof_root)
            feedback_status = str(feedback_result.get("status", "FAIL")).upper()

        if decision_status == "PASS" and feedback_status in {"PASS", "NOT_EVALUATED"}:
            lane["replay_state"] = "PASS"
        else:
            lane["replay_state"] = "FAIL"
            findings.append(
                {
                    "severity": "warning",
                    "code": "replay_validation_failed",
                    "message": "Replay validation failed for available control-plane chains.",
                }
            )
    except Exception:
        lane["replay_validator_available"] = "NO"
        lane["replay_state"] = "UNAVAILABLE"
        findings.append(
            {
                "severity": "warning",
                "code": "replay_validator_unavailable",
                "message": "Replay validator could not evaluate current proof root.",
            }
        )

    return lane, findings


def _collect_graph_lane(project_root: Path) -> tuple[dict[str, str], list[dict[str, str]], bool]:
    findings: list[dict[str, str]] = []
    try:
        state = load_graph_state(project_root)
    except Exception:
        findings.append(
            {
                "severity": "warning",
                "code": "graph_state_unknown",
                "message": "Graph state could not be read.",
            }
        )
        return {"graph_state": "UNKNOWN"}, findings, True

    dirty = bool(state.get("dirty", True))
    last_refresh_status = str(state.get("last_refresh_status", "none"))

    if dirty:
        graph_state = "DIRTY"
        findings.append(
            {
                "severity": "warning",
                "code": "graph_state_dirty",
                "message": "Graph state is dirty or stale.",
            }
        )
    elif last_refresh_status == "success":
        graph_state = "CLEAN"
    else:
        graph_state = "UNKNOWN"

    return {"graph_state": graph_state}, findings, graph_state == "UNKNOWN"


def _collect_capability_lane(project_root: Path) -> tuple[dict[str, str], list[dict[str, str]], bool]:
    findings: list[dict[str, str]] = []
    try:
        contract_candidates = [
            project_root / "certification_target.json",
            project_root / "certification" / "certification_target.json",
        ]
        contract_exists = any(p.is_file() for p in contract_candidates)

        baseline_root = project_root / "certification" / "baseline_v1"
        required_files = [
            baseline_root / "baseline_manifest.json",
            baseline_root / "baseline_matrix.json",
            baseline_root / "diagnostic_metrics.json",
            project_root / "certification" / "scenario_index.json",
        ]
        required_exist = all(p.is_file() for p in required_files)

        if contract_exists and required_exist:
            capability_state = "READY"
        elif contract_exists or any(p.is_file() for p in required_files):
            capability_state = "NOT_READY"
        else:
            capability_state = "NOT_READY"

        if capability_state == "NOT_READY":
            findings.append(
                {
                    "severity": "blocking",
                    "code": "capability_not_ready",
                    "message": "Certification target capability prerequisites are not fully ready.",
                }
            )

        return {"capability_state": capability_state}, findings, False
    except Exception:
        findings.append(
            {
                "severity": "warning",
                "code": "capability_unknown",
                "message": "Capability readiness could not be determined.",
            }
        )
        return {"capability_state": "UNKNOWN"}, findings, True


def _classify_overall_state(
    *,
    blocking_count: int,
    warning_count: int,
    actionable_warning_count: int,
    unknown_core: bool,
) -> str:
    if unknown_core and blocking_count == 0:
        return _UNKNOWN
    if blocking_count > 0:
        return _BLOCKED
    if actionable_warning_count > 0:
        return _ACTION_REQUIRED
    if warning_count > 0:
        return _HEALTHY_WARN
    return _HEALTHY


def collect_project_health(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()

    workspace, ws_findings, ws_unknown = _collect_workspace_lane()
    certification, cert_findings, cert_unknown = _collect_certification_lane(project_root)
    control_plane, cp_findings, proof_root = _collect_control_plane_lane(project_root)
    replay, replay_findings = _collect_replay_lane(proof_root, control_plane)
    graph, graph_findings, graph_unknown = _collect_graph_lane(project_root)
    capability, cap_findings, cap_unknown = _collect_capability_lane(project_root)

    # Tag each finding with its source lane before merging.
    for f in ws_findings:
        f["lane"] = "workspace"
    for f in cert_findings:
        f["lane"] = "certification"
    for f in cp_findings:
        f["lane"] = "control-plane"
    for f in replay_findings:
        f["lane"] = "replay"
    for f in graph_findings:
        f["lane"] = "graph"
    for f in cap_findings:
        f["lane"] = "capability"

    findings = [*ws_findings, *cert_findings, *cp_findings, *replay_findings, *graph_findings, *cap_findings]

    blocking_count = sum(1 for row in findings if str(row.get("severity", "")) == "blocking")
    warning_count = sum(1 for row in findings if str(row.get("severity", "")) != "blocking")
    actionable_warning_count = sum(
        1
        for row in findings
        if str(row.get("severity", "")) != "blocking"
        and str(row.get("code", "")) in _ACTIONABLE_WARNING_CODES
    )

    unknown_core = ws_unknown or cert_unknown or cap_unknown or graph_unknown

    overall_state = _classify_overall_state(
        blocking_count=blocking_count,
        warning_count=warning_count,
        actionable_warning_count=actionable_warning_count,
        unknown_core=unknown_core,
    )

    # Enrich findings with stable identity and normalized automation fields.
    # severity_band provides a four-tier operator-facing severity label:
    #   BLOCKING          → hard prerequisite missing or invalid (drives BLOCKED state)
    #   ACTIONABLE_WARNING → warning that drives ACTION_REQUIRED state
    #   WARNING           → advisory only (drives HEALTHY_WITH_WARNINGS at most)
    #   INFORMATIONAL     → reserved for future informational-only signals
    for f in findings:
        _apply_finding_normalization(f)
        code = str(f.get("code", ""))
        sev = str(f.get("severity", ""))
        if sev == "blocking":
            f["severity_band"] = "BLOCKING"
        elif code in _ACTIONABLE_WARNING_CODES:
            f["severity_band"] = "ACTIONABLE_WARNING"
        else:
            f["severity_band"] = "WARNING"
        f["affects_overall_state"] = True

    semantics = _get_state_semantics(overall_state)
    return {
        "project": str(project_root),
        "workspace": workspace,
        "certification": certification,
        "control-plane": control_plane,
        "replay": replay,
        "graph": graph,
        "capability": capability,
        "overall": {
            "project_health_state": overall_state,
            "overall_meaning": semantics["meaning"],
            "blocking_findings_count": blocking_count,
            "actionable_warning_findings_count": actionable_warning_count,
            "warning_findings_count": warning_count,
            "recommended_next_action": semantics["recommended_next_action"],
        },
        "findings": findings,
    }


def format_project_health_console(report: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    overall = report.get("overall", {}) if isinstance(report.get("overall", {}), dict) else {}
    state = overall.get("project_health_state", _UNKNOWN)
    meaning = overall.get("overall_meaning") or _get_state_semantics(state).get("meaning", "")
    recommended = overall.get("recommended_next_action") or _get_state_semantics(state).get("recommended_next_action", "")
    blocking_count = overall.get("blocking_findings_count", 0)
    warning_count = overall.get("warning_findings_count", 0)

    lines.append("----------------------------------------")
    lines.append("PROJECT HEALTH")
    lines.append(f"project={report.get('project', '')}")
    lines.append(f"overall={state}")
    lines.append(f"meaning={meaning}")
    lines.append(f"blocking_findings={blocking_count}")
    lines.append(f"warning_findings={warning_count}")
    lines.append(f"recommended_next_action={recommended}")
    lines.append("----------------------------------------")
    lines.append("")

    # Top findings summary (up to 5): blocking first, then actionable, then advisory.
    findings = report.get("findings", [])
    if findings and isinstance(findings, list):
        lines.append("[findings_summary]")
        ordered = (
            [f for f in findings if str(f.get("severity_band", "")) == "BLOCKING"]
            + [f for f in findings if str(f.get("severity_band", "")) == "ACTIONABLE_WARNING"]
            + [f for f in findings if str(f.get("severity_band", "")) not in {"BLOCKING", "ACTIONABLE_WARNING"}]
        )
        for f in ordered[:5]:
            band = str(f.get("severity_band") or f.get("severity", "").upper())
            fid = str(f.get("id", ""))
            lane = str(f.get("lane", ""))
            msg = str(f.get("message", ""))
            tag = f"[{lane}|{fid}]" if fid and lane else ""
            lines.append(f"{band}: {msg} {tag}".rstrip())
        lines.append("")

    workspace = report.get("workspace", {}) if isinstance(report.get("workspace", {}), dict) else {}
    lines.append("[workspace]")
    lines.append(f"integrity_state={workspace.get('integrity_state', 'UNKNOWN')}")
    lines.append("")

    cert = report.get("certification", {}) if isinstance(report.get("certification", {}), dict) else {}
    lines.append("[certification]")
    lines.append(f"certification_state={cert.get('certification_state', 'UNKNOWN')}")
    lines.append(f"placeholder_state={cert.get('placeholder_state', 'UNKNOWN')}")
    lines.append(f"drift_state={cert.get('drift_state', 'UNKNOWN')}")
    lines.append("")

    cp = report.get("control-plane", {}) if isinstance(report.get("control-plane", {}), dict) else {}
    lines.append("[control-plane]")
    lines.append(f"decision_envelope={cp.get('decision_envelope', 'ABSENT')}")
    lines.append(f"feedback_chain={cp.get('feedback_chain', 'ABSENT')}")
    lines.append(f"propagation_set={cp.get('propagation_set', 'ABSENT')}")
    lines.append(f"certification_cp_summary={cp.get('certification_cp_summary', 'ABSENT')}")
    lines.append(f"operational_cp_summary={cp.get('operational_cp_summary', 'ABSENT')}")
    lines.append(f"explain_cp_summary={cp.get('explain_cp_summary', 'ABSENT')}")
    lines.append("")

    replay = report.get("replay", {}) if isinstance(report.get("replay", {}), dict) else {}
    lines.append("[replay]")
    lines.append(f"replay_validator_available={replay.get('replay_validator_available', 'NO')}")
    lines.append(f"replay_applicability={replay.get('replay_applicability', 'CERTIFY_VALIDATE_ONLY')}")
    lines.append(f"replay_state={replay.get('replay_state', 'NOT_EVALUATED')}")
    lines.append("")

    graph = report.get("graph", {}) if isinstance(report.get("graph", {}), dict) else {}
    lines.append("[graph]")
    lines.append(f"graph_state={graph.get('graph_state', 'UNKNOWN')}")
    lines.append("")

    capability = report.get("capability", {}) if isinstance(report.get("capability", {}), dict) else {}
    lines.append("[capability]")
    lines.append(f"capability_state={capability.get('capability_state', 'UNKNOWN')}")
    lines.append("")

    lines.append("[overall]")
    lines.append(f"project_health_state={overall.get('project_health_state', _UNKNOWN)}")
    lines.append(f"blocking_findings_count={overall.get('blocking_findings_count', 0)}")
    lines.append(f"actionable_warning_findings_count={overall.get('actionable_warning_findings_count', 0)}")
    lines.append(f"warning_findings_count={overall.get('warning_findings_count', 0)}")

    return lines
