from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .root_cause_rules import classify_root_cause
from .root_cause_types import RootCauseInputContext


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


def _artifact_rel(path: Path, pf: Path) -> str:
    try:
        return path.resolve().relative_to(pf.resolve()).as_posix()
    except Exception:
        return path.name


def _discover_capability_reports(pf: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    candidates = [
        pf / "target_validation" / "04_target_capability_classification.json",
        pf / "14_resolution_report.json",
        pf / "capability_resolution_report.json",
    ]
    for path in candidates:
        payload = _read_json(path)
        if payload:
            reports.append(payload)
    return reports


def analyze_failure(
    *,
    project_root: Path,
    pf: Path,
    command_name: str,
    stage_hint: str,
    failure_reason: str,
    exit_code: int,
    source_layer_hint: str,
    stderr_text: str = "",
    stdout_text: str = "",
    buildcore_reached: bool | None = None,
    failed_before_validation_gate: bool | None = None,
    failed_after_validation_gate: bool | None = None,
    extra_evidence_paths: list[str] | None = None,
) -> dict[str, Any]:
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)

    workspace_integrity = _read_json(pf / "workspace_integrity" / "02_workspace_integrity_report.json")
    graph_refresh = _read_json(pf / "23_graph_refresh_action.json")
    if not graph_refresh:
        graph_refresh = _read_json(pf / "20_graph_auto_refresh" / "23_graph_refresh_action.json")
    if not graph_refresh:
        graph_refresh = _read_json(pf / "20_graph_auto_refresh_orchestrator" / "23_graph_refresh_action.json")

    policy_gate = _read_json(pf / "build_pipeline_execution.json")
    if not policy_gate:
        policy_gate = {
            "gate_status": "FAIL" if "validation_policy" in stage_hint.lower() else "",
            "failing_step": stage_hint,
        }

    plugin_results = _read_json(pf / "validation_plugins" / "221_plugin_results.json")
    buildcore_execution = _read_json(pf / "buildcore_execution_report.json")
    build_pipeline = _read_json(pf / "build_pipeline_execution.json")

    auto_stdout = _read_text(pf / "pipeline_build_run" / "build_stdout.txt")
    auto_stderr = _read_text(pf / "pipeline_build_run" / "build_stderr.txt")
    stderr_blob = "\n".join([stderr_text, auto_stderr]).strip()
    stdout_blob = "\n".join([stdout_text, auto_stdout]).strip()

    if buildcore_reached is None:
        buildcore_reached = bool(buildcore_execution) or "buildcore" in str(build_pipeline.get("failing_step", "")).lower()

    if failed_before_validation_gate is None:
        failed_before_validation_gate = "workspace_integrity" in stage_hint.lower() or "graph" in stage_hint.lower()

    if failed_after_validation_gate is None:
        failed_after_validation_gate = bool(buildcore_reached)

    input_context = RootCauseInputContext(
        project_root=str(project_root.resolve()),
        proof_dir=str(pf),
        command_name=command_name,
        stage_hint=stage_hint,
        failure_reason=failure_reason,
        exit_code=int(exit_code),
        buildcore_reached=bool(buildcore_reached),
        failed_before_validation_gate=bool(failed_before_validation_gate),
        failed_after_validation_gate=bool(failed_after_validation_gate),
        stderr_excerpt=(stderr_blob or "")[-4000:],
        stdout_excerpt=(stdout_blob or "")[-4000:],
    )

    capability_reports = _discover_capability_reports(pf)

    classification = classify_root_cause(
        input_context=input_context,
        workspace_integrity=workspace_integrity,
        graph_refresh=graph_refresh,
        policy_gate=policy_gate,
        plugin_results=plugin_results,
        buildcore_execution=buildcore_execution,
        build_pipeline=build_pipeline,
        capability_reports=capability_reports,
        stderr_blob=stderr_blob,
    )

    evidence_paths: list[str] = []
    for rel in classification.evidence_refs:
        evidence_paths.append(rel)
    for rel in list(extra_evidence_paths or []):
        if rel and rel not in evidence_paths:
            evidence_paths.append(rel)

    input_payload = {
        "generated_at": _iso_now(),
        "project_root": input_context.project_root,
        "proof_dir": input_context.proof_dir,
        "command_name": input_context.command_name,
        "stage_hint": input_context.stage_hint,
        "failure_reason": input_context.failure_reason,
        "exit_code": input_context.exit_code,
        "source_layer_hint": source_layer_hint,
        "buildcore_reached": input_context.buildcore_reached,
        "failed_before_validation_gate": input_context.failed_before_validation_gate,
        "failed_after_validation_gate": input_context.failed_after_validation_gate,
        "stderr_excerpt": input_context.stderr_excerpt,
        "stdout_excerpt": input_context.stdout_excerpt,
        "discovered_artifacts": {
            "workspace_integrity": _artifact_rel(pf / "workspace_integrity" / "02_workspace_integrity_report.json", pf),
            "graph_refresh": _artifact_rel(pf / "23_graph_refresh_action.json", pf),
            "policy_gate": _artifact_rel(pf / "build_pipeline_execution.json", pf),
            "plugin_results": _artifact_rel(pf / "validation_plugins" / "221_plugin_results.json", pf),
            "buildcore_execution": _artifact_rel(pf / "buildcore_execution_report.json", pf),
            "build_stdout": _artifact_rel(pf / "pipeline_build_run" / "build_stdout.txt", pf),
            "build_stderr": _artifact_rel(pf / "pipeline_build_run" / "build_stderr.txt", pf),
        },
    }

    classification_payload = {
        "generated_at": _iso_now(),
        "failure_stage": classification.failure_stage,
        "root_cause_code": classification.root_cause_code,
        "summary": classification.summary,
        "evidence_refs": evidence_paths,
        "recommended_fix": classification.recommended_fix,
        "confidence_score": classification.confidence_score,
        "blocking": classification.blocking,
        "source_layer": classification.source_layer,
    }

    evidence_payload = {
        "generated_at": _iso_now(),
        "failure_stage": classification.failure_stage,
        "evidence_refs": evidence_paths,
        "observed": {
            "workspace_integrity_status": str(workspace_integrity.get("status", "")),
            "graph_refresh_status": str(graph_refresh.get("status", "")),
            "policy_gate_status": str(policy_gate.get("gate_status", "")),
            "plugin_overall_status": str(plugin_results.get("overall_status", plugin_results.get("summary", {}).get("overall_status", ""))),
            "buildcore_exit_code": int(buildcore_execution.get("exit_code", build_pipeline.get("exit_code", input_context.exit_code))),
        },
    }

    recommendation_payload = {
        "generated_at": _iso_now(),
        "failure_stage": classification.failure_stage,
        "root_cause_code": classification.root_cause_code,
        "recommended_fix": classification.recommended_fix,
        "blocking": classification.blocking,
    }

    confidence_payload = {
        "generated_at": _iso_now(),
        "failure_stage": classification.failure_stage,
        "confidence_score": classification.confidence_score,
        "confidence_band": "HIGH" if classification.confidence_score >= 0.9 else ("MEDIUM" if classification.confidence_score >= 0.7 else "LOW"),
        "explainability": "deterministic_rule_match",
    }

    summary_lines = [
        "# Failure Summary",
        "",
        f"- command_name: {input_context.command_name}",
        f"- failure_stage: {classification.failure_stage}",
        f"- root_cause_code: {classification.root_cause_code}",
        f"- summary: {classification.summary}",
        f"- source_layer: {classification.source_layer}",
        f"- confidence_score: {classification.confidence_score:.2f}",
        f"- blocking: {classification.blocking}",
        f"- buildcore_reached: {input_context.buildcore_reached}",
        f"- failed_before_validation_gate: {input_context.failed_before_validation_gate}",
        f"- failed_after_validation_gate: {input_context.failed_after_validation_gate}",
        f"- recommended_fix: {classification.recommended_fix}",
        "",
        "## Evidence Refs",
    ]
    if evidence_paths:
        for rel in evidence_paths:
            summary_lines.append(f"- {rel}")
    else:
        summary_lines.append("- none")
    summary_lines.append("")

    _write_json(pf / "40_root_cause_input_context.json", input_payload)
    _write_json(pf / "41_failure_stage_classification.json", classification_payload)
    _write_json(pf / "42_root_cause_evidence.json", evidence_payload)
    _write_json(pf / "43_fix_recommendations.json", recommendation_payload)
    _write_json(pf / "44_confidence_report.json", confidence_payload)
    _write_text(pf / "45_failure_summary.md", "\n".join(summary_lines))

    # Compatibility names requested by milestone statement.
    _write_json(pf / "root_cause_classification.json", classification_payload)
    _write_json(pf / "root_cause_evidence.json", evidence_payload)
    _write_json(pf / "fix_recommendations.json", recommendation_payload)
    _write_text(pf / "failure_summary.md", "\n".join(summary_lines))

    return {
        "failure_stage": classification.failure_stage,
        "root_cause_code": classification.root_cause_code,
        "summary": classification.summary,
        "recommended_fix": classification.recommended_fix,
        "confidence_score": classification.confidence_score,
        "artifact_names": [
            "40_root_cause_input_context.json",
            "41_failure_stage_classification.json",
            "42_root_cause_evidence.json",
            "43_fix_recommendations.json",
            "44_confidence_report.json",
            "45_failure_summary.md",
        ],
    }
