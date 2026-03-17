from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .root_cause_types import RootCauseClassification, RootCauseInputContext


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _bool_payload(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "pass"}


def _first_existing_ref(proof_dir: Path, candidates: list[str]) -> list[str]:
    out: list[str] = []
    for rel in candidates:
        if (proof_dir / rel).exists():
            out.append(rel)
    return out


def _compiler_like(stderr_blob: str) -> bool:
    patterns = [
        r"\bCS\d{4}\b",
        r"\berror\s+C\d+\b",
        r"\bfatal\s+error\s+C\d+\b",
        r"\bgcc\b.*\berror\b",
        r"\bclang\b.*\berror\b",
        r"\bcompilation\s+terminated\b",
    ]
    return any(re.search(pattern, stderr_blob, flags=re.IGNORECASE) for pattern in patterns)


def _linker_like(stderr_blob: str) -> bool:
    patterns = [
        r"\bLNK\d{4}\b",
        r"\bunresolved\s+external\s+symbol\b",
        r"\bundefined\s+reference\b",
        r"\bcannot\s+find\s+-l\w+\b",
        r"\bld\b.*\berror\b",
        r"\bcollect2\b.*\berror\b",
    ]
    return any(re.search(pattern, stderr_blob, flags=re.IGNORECASE) for pattern in patterns)


def _packaging_like(stderr_blob: str) -> bool:
    patterns = [
        r"\bpackag(e|ing)\b",
        r"\bbdist\b",
        r"\bwheel\b",
        r"\bpyproject\.toml\b",
        r"\bpip\s+build\b",
    ]
    return any(re.search(pattern, stderr_blob, flags=re.IGNORECASE) for pattern in patterns)


def classify_root_cause(
    *,
    input_context: RootCauseInputContext,
    workspace_integrity: dict[str, Any],
    graph_refresh: dict[str, Any],
    policy_gate: dict[str, Any],
    plugin_results: dict[str, Any],
    buildcore_execution: dict[str, Any],
    build_pipeline: dict[str, Any],
    capability_reports: list[dict[str, Any]],
    stderr_blob: str,
) -> RootCauseClassification:
    proof_dir = Path(input_context.proof_dir)
    stage_hint = _norm(input_context.stage_hint)
    reason = _norm(input_context.failure_reason)

    workspace_status = _norm(str(workspace_integrity.get("status", "")))
    if workspace_status == "fail" or "workspace_integrity" in stage_hint or "workspace_integrity" in reason:
        refs = _first_existing_ref(proof_dir, [
            "workspace_integrity/02_workspace_integrity_report.json",
            "workspace_integrity/03_workspace_integrity_summary.md",
        ])
        return RootCauseClassification(
            failure_stage="WORKSPACE_INTEGRITY_FAILURE",
            root_cause_code="WORKSPACE_PACKAGE_INTEGRITY_VIOLATION",
            summary="Workspace package integrity check failed before command execution.",
            evidence_refs=tuple(refs),
            recommended_fix="Reinstall editable workspace packages and ensure active interpreter resolves modules from workspace root.",
            confidence_score=0.99,
            blocking=True,
            source_layer="WorkspaceIntegrity",
        )

    refresh_status = _norm(str(graph_refresh.get("status", "")))
    refresh_reason = _norm(str(graph_refresh.get("reason", "")))
    if refresh_status == "failed" or "graph_refresh" in stage_hint or "graph_state" in stage_hint:
        refs = _first_existing_ref(proof_dir, [
            "23_graph_refresh_action.json",
            "22_graph_dirty_reasons.json",
            "25_graph_state_summary.md",
        ])
        stage = "GRAPH_REFRESH_FAILURE" if ("refresh" in stage_hint or refresh_reason == "dirty_graph_state") else "GRAPH_STATE_FAILURE"
        code = "GRAPH_AUTO_REFRESH_FAILED" if stage == "GRAPH_REFRESH_FAILURE" else "GRAPH_STATE_DIRTY_BLOCKING"
        summary = "Graph refresh failed and BuildCore was blocked." if stage == "GRAPH_REFRESH_FAILURE" else "Graph state validation failed before BuildCore execution."
        return RootCauseClassification(
            failure_stage=stage,
            root_cause_code=code,
            summary=summary,
            evidence_refs=tuple(refs),
            recommended_fix="Refresh graph state artifacts and resolve tracked dirty reasons before retrying.",
            confidence_score=0.97,
            blocking=True,
            source_layer="GraphStateManager",
        )

    for report in capability_reports:
        build_allowed = report.get("build_allowed")
        target_state = _norm(str(report.get("target_capability_state", "")))
        if build_allowed is False or target_state in {"fail", "blocked", "missing", "invalid", "error"}:
            refs = _first_existing_ref(proof_dir, [
                "target_validation/04_target_capability_classification.json",
                "14_resolution_report.json",
            ])
            return RootCauseClassification(
                failure_stage="CAPABILITY_RESOLUTION_FAILURE",
                root_cause_code="MISSING_REQUIRED_CAPABILITY",
                summary="Required target capability is not available for the active target specification.",
                evidence_refs=tuple(refs),
                recommended_fix="Install or expose the required capability in the active toolchain, or correct the canonical target spec.",
                confidence_score=0.98,
                blocking=True,
                source_layer="NGKsGraph",
            )

    gate_status = _norm(str(policy_gate.get("gate_status", "")))
    if gate_status == "fail" or "validation_policy" in stage_hint:
        refs = _first_existing_ref(proof_dir, [
            "34_policy_gate_rules.json",
            "35_policy_summary.md",
            "validation_plugins/221_plugin_results.json",
        ])
        return RootCauseClassification(
            failure_stage="VALIDATION_POLICY_BLOCK",
            root_cause_code="BLOCKING_VALIDATION_PLUGIN_FAILURE",
            summary="Validation policy gate blocked execution due to a failing blocking plugin.",
            evidence_refs=tuple(refs),
            recommended_fix="Fix the failing blocking validation plugin findings before continuing the pipeline.",
            confidence_score=0.99,
            blocking=True,
            source_layer="ValidationPolicyEngine",
        )

    for row in list(plugin_results.get("rows", []) or []):
        if _norm(str(row.get("status", ""))) == "fail":
            refs = _first_existing_ref(proof_dir, [
                "validation_plugins/221_plugin_results.json",
                "validation_plugins/222_plugin_summary.md",
            ])
            return RootCauseClassification(
                failure_stage="VALIDATION_PLUGIN_FAILURE",
                root_cause_code="VALIDATION_PLUGIN_EXECUTION_FAIL",
                summary=f"Validation plugin '{str(row.get('plugin_name', 'unknown'))}' failed.",
                evidence_refs=tuple(refs),
                recommended_fix="Inspect the failing plugin artifact details and remediate the reported issue.",
                confidence_score=0.96,
                blocking=True,
                source_layer="ValidationPlugins",
            )

    if "dispatch" in stage_hint or "argparse" in reason or "invalid choice" in stderr_blob.lower():
        refs = _first_existing_ref(proof_dir, ["40_root_cause_input_context.json"])
        return RootCauseClassification(
            failure_stage="COMMAND_DISPATCH_FAILURE",
            root_cause_code="INVALID_COMMAND_SHAPE",
            summary="CLI command dispatch failed due to malformed or unsupported invocation.",
            evidence_refs=tuple(refs),
            recommended_fix="Correct the command/subcommand shape and rerun with supported arguments.",
            confidence_score=0.98,
            blocking=True,
            source_layer="CLI",
        )

    if "profile" in stage_hint or "profile" in reason:
        refs = _first_existing_ref(proof_dir, ["run_build/00_selected_path.json", "40_root_cause_input_context.json"])
        return RootCauseClassification(
            failure_stage="PROFILE_LOAD_FAILURE",
            root_cause_code="PROFILE_JSON_INVALID_OR_MISSING",
            summary="Build profile could not be loaded or parsed.",
            evidence_refs=tuple(refs),
            recommended_fix="Generate or repair the profile JSON and ensure the profile path resolves correctly in runwrap.",
            confidence_score=0.97,
            blocking=True,
            source_layer="Runwrap",
        )

    buildcore_exit = int(buildcore_execution.get("exit_code", build_pipeline.get("exit_code", input_context.exit_code)))
    pipeline_step = _norm(str(build_pipeline.get("failing_step", "")))
    if buildcore_exit != 0 or "buildcore" in stage_hint or "execute_buildcore_plan" in pipeline_step:
        refs = _first_existing_ref(proof_dir, [
            "buildcore_execution_report.json",
            "pipeline_build_run/build_stderr.txt",
            "pipeline_build_run/build_stdout.txt",
            "build_pipeline_execution.json",
        ])
        stderr_l = stderr_blob or ""
        if _compiler_like(stderr_l):
            return RootCauseClassification(
                failure_stage="COMPILER_FAILURE",
                root_cause_code="COMPILER_DIAGNOSTIC_DETECTED",
                summary="Compiler diagnostics were detected after BuildCore execution reached compile actions.",
                evidence_refs=tuple(refs),
                recommended_fix="Inspect compile command, include paths, and flags for the failing translation unit.",
                confidence_score=0.97,
                blocking=True,
                source_layer="BuildCore",
            )
        if _linker_like(stderr_l):
            return RootCauseClassification(
                failure_stage="LINKER_FAILURE",
                root_cause_code="LINKER_DIAGNOSTIC_DETECTED",
                summary="Linker diagnostics were detected after compile stage execution.",
                evidence_refs=tuple(refs),
                recommended_fix="Inspect unresolved symbols, missing libraries, and linker subsystem/output settings.",
                confidence_score=0.96,
                blocking=True,
                source_layer="BuildCore",
            )
        if _packaging_like(stderr_l):
            return RootCauseClassification(
                failure_stage="PACKAGING_FAILURE",
                root_cause_code="PACKAGING_STEP_FAILED",
                summary="Packaging/build artifact assembly failed after execution started.",
                evidence_refs=tuple(refs),
                recommended_fix="Review packaging configuration and generated artifact paths, then rerun packaging.",
                confidence_score=0.92,
                blocking=True,
                source_layer="BuildCore",
            )

        return RootCauseClassification(
            failure_stage="BUILDCORE_EXECUTION_FAILURE",
            root_cause_code="BUILDCORE_NONZERO_EXIT",
            summary="BuildCore execution returned a non-zero exit code.",
            evidence_refs=tuple(refs),
            recommended_fix="Inspect BuildCore node stderr/stdout and failed node diagnostics to identify the failing command.",
            confidence_score=0.88,
            blocking=True,
            source_layer="BuildCore",
        )

    refs = _first_existing_ref(proof_dir, [
        "40_root_cause_input_context.json",
        "build_pipeline_execution.json",
        "pipeline_summary.md",
    ])
    return RootCauseClassification(
        failure_stage="UNKNOWN_FAILURE",
        root_cause_code="NO_DETERMINISTIC_RULE_MATCH",
        summary="Failure did not match a deterministic classifier rule; preserved evidence for manual triage.",
        evidence_refs=tuple(refs),
        recommended_fix="Inspect captured evidence and add a deterministic rule if this pattern recurs.",
        confidence_score=0.45,
        blocking=True,
        source_layer="RootCauseAnalyzer",
    )
