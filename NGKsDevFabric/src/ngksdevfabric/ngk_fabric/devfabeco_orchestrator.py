from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation_policy_engine import evaluate_validation_policy
from .workspace_integrity import run_workspace_integrity_check
from .graph_state_manager import ensure_graph_state_fresh
from .root_cause_analyzer import analyze_failure
from .decision_envelope_manager import create_manager, make_finding
from .outcome_feedback_manager import create_feedback_manager


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _pipeline_run_id(pf: Path) -> str:
    return f"devfabric_run_{pf.name}"


def _latest_envelope_hash(pf: Path) -> str:
    payload = _read_json(pf / "control_plane" / "58_decision_envelope_chain.json")
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list) or not entries:
        return "UNAVAILABLE"
    last = entries[-1] if isinstance(entries[-1], dict) else {}
    return str(last.get("entry_hash", "UNAVAILABLE"))


def _policy_findings(policy_result: dict[str, Any], *, stage_name: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for reason in policy_result.get("blocking_failures", []):
        findings.append(
            make_finding(
                source_component="DevFabric",
                source_artifact="validation_plugins/221_plugin_results.json",
                severity="error",
                reason_code="VALIDATION_POLICY_BLOCK",
                confidence_score=0.95,
                blocking=True,
                evidence_refs=["validation_plugins/220_plugin_execution_plan.json", "validation_plugins/221_plugin_results.json"],
                stage_name=stage_name,
            )
        )
    for reason in policy_result.get("advisory_failures", []):
        findings.append(
            make_finding(
                source_component="DevFabric",
                source_artifact="validation_plugins/221_plugin_results.json",
                severity="warning",
                reason_code="DIAGNOSTICS_WARN",
                confidence_score=0.6,
                blocking=False,
                evidence_refs=["validation_plugins/221_plugin_results.json", str(reason)],
                stage_name=stage_name,
            )
        )
    return findings


def _tracked_graph_inputs(project_root: Path) -> list[Path]:
    include_suffixes = {
        ".py",
        ".ps1",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".txt",
        ".md",
        ".csproj",
        ".sln",
        ".props",
        ".targets",
    }
    include_names = {
        "pyproject.toml",
        "requirements.txt",
        "requirements.local.txt",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "global.json",
        "directory.build.props",
        "directory.build.targets",
        "nuget.config",
        "env_capsule.lock.json",
    }
    blocked_dirs = {
        ".git",
        "_proof",
        ".venv",
        "_validation_venv",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        "releases",
        "wheelhouse",
    }

    out: list[Path] = []
    root = project_root.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.as_posix().lower() == ".ngks/graph_state_manifest.json":
            continue
        if any(part.lower() in blocked_dirs for part in rel.parts):
            continue
        name_l = path.name.lower()
        if name_l in include_names or path.suffix.lower() in include_suffixes:
            out.append(path)
    out.sort(key=lambda p: p.as_posix().lower())
    return out


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def ensure_graph_state_current(project_root: Path, pf: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    state_dir = project_root / ".ngks"
    state_dir.mkdir(parents=True, exist_ok=True)

    tracked = _tracked_graph_inputs(project_root)
    manifest_rows: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for file_path in tracked:
        rel = file_path.relative_to(project_root).as_posix()
        stat = file_path.stat()
        sha = _file_sha256(file_path)
        row = {
            "path": rel,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": sha,
        }
        manifest_rows.append(row)
        aggregate.update(rel.encode("utf-8"))
        aggregate.update(str(stat.st_size).encode("utf-8"))
        aggregate.update(str(stat.st_mtime_ns).encode("utf-8"))
        aggregate.update(sha.encode("utf-8"))

    current_hash = aggregate.hexdigest()
    manifest_file = state_dir / "graph_state_manifest.json"
    previous = _read_json(manifest_file)
    previous_hash = str(previous.get("manifest_hash", "")).strip()
    changed = previous_hash != current_hash

    payload = {
        "generated_at": _iso_now(),
        "project_root": str(project_root),
        "manifest_hash": current_hash,
        "tracked_file_count": len(manifest_rows),
        "changed_since_last": changed,
        "rows": manifest_rows,
    }
    _write_json(manifest_file, payload)
    _write_json(
        pf / "graph_validation_report.json",
        {
            "status": "PASS",
            "generated_at": _iso_now(),
            "graph_state_manifest": str(manifest_file),
            "tracked_file_count": len(manifest_rows),
            "manifest_hash": current_hash,
            "previous_manifest_hash": previous_hash,
            "graph_refresh_required": changed,
            "validation_rule": "graph_must_refresh_when_project_state_changes",
        },
    )
    return payload


def generate_graph_plan(project_root: Path, pf: Path, graph_state: dict[str, Any]) -> dict[str, Any]:
    refresh_required = bool(graph_state.get("changed_since_last", False))
    payload = {
        "status": "PASS",
        "generated_at": _iso_now(),
        "project_root": str(project_root.resolve()),
        "graph_refresh_triggered": refresh_required,
        "planning_mode": "deterministic",
        "notes": [
            "Build pipeline executes graph planning before BuildCore execution.",
            "Graph refresh is required whenever tracked project state changes.",
        ],
    }
    _write_json(pf / "graph_plan_report.json", payload)
    return payload


@dataclass(frozen=True)
class StageOutcome:
    status: str
    exit_code: int
    message: str
    details: dict[str, Any]


def execute_buildcore_plan(
    project_root: Path,
    pf: Path,
    *,
    mode: str,
    target: str | None,
    profile: str | None,
) -> StageOutcome:
    command = [sys.executable, "-m", "ngksdevfabric", "run", "--project", str(project_root.resolve()), "--mode", "ecosystem"]
    if profile:
        command.extend(["--profile", str(profile)])
    if target:
        command.extend(["--target", str(target)])

    run_dir = pf / "pipeline_build_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "build_stdout.txt"
    stderr_path = run_dir / "build_stderr.txt"

    env = dict(os.environ)
    env["NGKS_ALLOW_DIRECT_BUILDCORE"] = "1"

    proc = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    status = "PASS" if int(proc.returncode) == 0 else "FAIL"
    payload = {
        "status": status,
        "exit_code": int(proc.returncode),
        "generated_at": _iso_now(),
        "command": command,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    _write_json(pf / "buildcore_execution_report.json", payload)
    return StageOutcome(status=status, exit_code=int(proc.returncode), message="buildcore stage complete", details=payload)


def run_devfabric_diagnostics(
    project_root: Path,
    pf: Path,
    *,
    stage: str,
    profile: str,
    target: str,
) -> dict[str, Any]:
    result = evaluate_validation_policy(
        project_root=project_root.resolve(),
        pf=pf.resolve(),
        stage=stage,
        profile=profile,
        target=target,
    )
    payload = {
        "status": str(result.get("gate_status", "PASS")),
        "generated_at": _iso_now(),
        "plugin_count": len(result.get("selected_plugins", [])),
        "fail_count": len(result.get("blocking_failures", [])),
        "warning_count": len(result.get("advisory_failures", [])),
        "blocking_failures": result.get("blocking_failures", []),
        "advisory_failures": result.get("advisory_failures", []),
    }
    _write_json(pf / "devfabric_diagnostics_report.json", payload)
    return payload


def _write_failure_diagnostics(
    *,
    pf: Path,
    failing_step: str,
    message: str,
    traceback_text: str,
    buildcore_exit_code: int,
) -> None:
    _write_json(
        pf / "failure_trace.json",
        {
            "generated_at": _iso_now(),
            "failing_step": failing_step,
            "message": message,
            "traceback": traceback_text,
            "buildcore_exit_code": int(buildcore_exit_code),
        },
    )

    classification = "GRAPH_VALIDATION_FAILURE" if failing_step.startswith("graph") else "BUILDCORE_FAILURE"
    _write_json(
        pf / "root_cause_classification.json",
        {
            "generated_at": _iso_now(),
            "classification": classification,
            "failing_step": failing_step,
            "buildcore_exit_code": int(buildcore_exit_code),
        },
    )

    recommendations = [
        "Review graph_validation_report.json and graph_plan_report.json for stale state triggers.",
        "Inspect buildcore_execution_report.json and captured stderr for failing command details.",
        "Use validation_plugins/220_plugin_execution_plan.json and 221_plugin_results.json to prioritize remediation.",
    ]
    _write_json(
        pf / "fix_recommendations.json",
        {
            "generated_at": _iso_now(),
            "failing_step": failing_step,
            "recommendations": recommendations,
        },
    )

    _write_text(
        pf / "failure_summary.md",
        "\n".join(
            [
                "# Build Failure Summary",
                "",
                f"- failing_step: {failing_step}",
                f"- message: {message}",
                f"- buildcore_exit_code: {int(buildcore_exit_code)}",
                "- diagnostics: validation plugin bundle generated automatically",
                "",
            ]
        ),
    )


def run_build_pipeline(
    *,
    project_root: Path,
    pf: Path,
    mode: str = "debug",
    target: str | None = None,
    profile: str | None = None,
    trigger: str = "ngks build",
) -> dict[str, Any]:
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)
    run_id = _pipeline_run_id(pf)
    envelope = create_manager(pf=pf, run_id=run_id, trigger=trigger)
    feedback = create_feedback_manager(pf=pf, run_id=run_id)

    def _feedback_safe(**kwargs: Any) -> None:
        try:
            feedback.append_feedback(**kwargs)
        except Exception as exc:
            _write_text(pf / "control_plane" / "outcome_feedback_write_error.txt", str(exc) + "\n")

    integrity_result, integrity_artifacts = run_workspace_integrity_check(
        scope="orchestrator_preflight",
        artifact_dir=pf / "workspace_integrity",
    )
    envelope.write_stage(
        stage_name="preflight",
        gate_decision="PASS" if integrity_result.ok else "FAIL",
        reason_codes=["WORKSPACE_INTEGRITY_OK" if integrity_result.ok else "WORKSPACE_INTEGRITY_FAILED"],
        evidence_refs=["workspace_integrity/02_workspace_integrity_report.json"],
        missing_inputs=[] if integrity_result.ok else ["workspace_integrity_ok"],
        normalized_findings=[]
        if integrity_result.ok
        else [
            make_finding(
                source_component="DevFabric",
                source_artifact="workspace_integrity/02_workspace_integrity_report.json",
                severity="error",
                reason_code="WORKSPACE_INTEGRITY_FAILED",
                confidence_score=1.0,
                blocking=True,
                evidence_refs=["workspace_integrity/02_workspace_integrity_report.json"],
                stage_name="preflight",
            )
        ],
    )
    if not integrity_result.ok:
        _feedback_safe(
            stage_id="preflight",
            stage_name="preflight",
            linked_envelope_hash=_latest_envelope_hash(pf),
            action_id="workspace_integrity_failure_proposal",
            action_proposed=True,
            action_taken=False,
            action_executor="system",
            observed_result_code="ACTION_PROPOSED_FROM_ROOT_CAUSE",
            observed_result_summary="Workspace integrity failure generated remediation proposal.",
            observed_gate_change="FAIL",
            confidence_adjustment_delta=0.0,
            confidence_adjustment_reason="proposal_only",
            recurrence_impact_category="unchanged",
            recurrence_impact_delta=0.0,
            predictive_calibration_delta=0.0,
            predictive_calibration_reason="metrics_only_no_model_mutation",
            certification_impact="none",
            supporting_evidence_refs=["workspace_integrity/02_workspace_integrity_report.json", "43_fix_recommendations.json"],
        )
        envelope.finalize_missing_stages()
        _write_json(
            pf / "build_pipeline_execution.json",
            {
                "status": "FAIL",
                "generated_at": _iso_now(),
                "trigger": trigger,
                "failing_step": "workspace_integrity_check",
                "workspace_root": integrity_result.workspace_root,
                "python_executable": integrity_result.python_executable,
                "module_resolution": integrity_result.module_resolution,
                "violations": integrity_result.violations,
                "integrity_artifacts": integrity_artifacts,
            },
        )
        _write_text(
            pf / "pipeline_summary.md",
            "\n".join(
                [
                    "# DevFabEco Build Pipeline Summary",
                    "",
                    "- status: FAIL",
                    "- failing_step: workspace_integrity_check",
                    f"- workspace_root: {integrity_result.workspace_root}",
                    f"- python_executable: {integrity_result.python_executable}",
                    "",
                ]
            ),
        )
        analyze_failure(
            project_root=project_root,
            pf=pf,
            command_name=trigger,
            stage_hint="WORKSPACE_INTEGRITY_FAILURE",
            failure_reason="workspace_integrity_check_failed",
            exit_code=2,
            source_layer_hint="WorkspaceIntegrity",
            stderr_text="\n".join(integrity_result.violations),
            buildcore_reached=False,
            failed_before_validation_gate=True,
            failed_after_validation_gate=False,
        )
        return {
            "status": "FAIL",
            "exit_code": 2,
            "pipeline_execution_order": ["workspace_integrity_check"],
            "artifacts": [
                "workspace_integrity/00_python_executable.txt",
                "workspace_integrity/01_module_resolution.json",
                "workspace_integrity/02_workspace_integrity_report.json",
                "workspace_integrity/03_workspace_integrity_summary.md",
                "build_pipeline_execution.json",
                "pipeline_summary.md",
            ],
        }

    graph_artifact_root = (pf / "20_graph_auto_refresh_orchestrator").resolve()

    def _refresh_graph_callback() -> tuple[bool, str]:
        try:
            graph_artifact_root.mkdir(parents=True, exist_ok=True)
            graph_state = ensure_graph_state_current(project_root=project_root, pf=graph_artifact_root)
            generate_graph_plan(project_root=project_root, pf=graph_artifact_root, graph_state=graph_state)
            return True, "graph_refresh_completed"
        except Exception as exc:
            return False, str(exc)

    graph_state_outcome = ensure_graph_state_fresh(
        project_root=project_root,
        pf=pf,
        active_profile=str(profile or "debug"),
        active_target=str(target or "build"),
        graph_artifact_root=graph_artifact_root,
        refresh_callback=_refresh_graph_callback,
    )
    envelope.write_stage(
        stage_name="planning",
        gate_decision="PASS" if bool(graph_state_outcome.get("ok", False)) else "FAIL",
        reason_codes=["GRAPH_STATE_FRESH" if bool(graph_state_outcome.get("ok", False)) else "GRAPH_REFRESH_FAILED"],
        evidence_refs=[
            "20_graph_state_before.json",
            "21_graph_fingerprint_current.json",
            "22_graph_dirty_reasons.json",
            "23_graph_refresh_action.json",
            "24_graph_state_after.json",
            "25_graph_state_summary.md",
        ],
        missing_inputs=[] if bool(graph_state_outcome.get("ok", False)) else ["graph_refresh_success"],
    )
    if not bool(graph_state_outcome.get("ok", False)):
        _feedback_safe(
            stage_id="planning",
            stage_name="planning",
            linked_envelope_hash=_latest_envelope_hash(pf),
            action_id="graph_refresh_failure_proposal",
            action_proposed=True,
            action_taken=False,
            action_executor="system",
            observed_result_code="ACTION_PROPOSED_FROM_ROOT_CAUSE",
            observed_result_summary="Graph refresh failure generated remediation proposal.",
            observed_gate_change="FAIL",
            confidence_adjustment_delta=0.0,
            confidence_adjustment_reason="proposal_only",
            recurrence_impact_category="unchanged",
            recurrence_impact_delta=0.0,
            predictive_calibration_delta=0.0,
            predictive_calibration_reason="metrics_only_no_model_mutation",
            certification_impact="none",
            supporting_evidence_refs=["23_graph_refresh_action.json", "43_fix_recommendations.json"],
        )
        envelope.finalize_missing_stages()
        refresh_action = graph_state_outcome.get("refresh_action", {})
        _write_json(
            pf / "build_pipeline_execution.json",
            {
                "status": "FAIL",
                "generated_at": _iso_now(),
                "trigger": trigger,
                "failing_step": "graph_state_auto_refresh",
                "dirty_reasons": graph_state_outcome.get("dirty_reasons", []),
                "refresh_action": refresh_action,
                "graph_state_path": graph_state_outcome.get("state_path", ""),
                "buildcore_blocked": True,
            },
        )
        _write_text(
            pf / "pipeline_summary.md",
            "\n".join(
                [
                    "# DevFabEco Build Pipeline Summary",
                    "",
                    "- status: FAIL",
                    "- failing_step: graph_state_auto_refresh",
                    f"- dirty_reasons: {', '.join(graph_state_outcome.get('dirty_reasons', []))}",
                    f"- refresh_status: {str(refresh_action.get('status', 'failed'))}",
                    "- buildcore_blocked: true",
                    "",
                ]
            ),
        )
        analyze_failure(
            project_root=project_root,
            pf=pf,
            command_name=trigger,
            stage_hint="GRAPH_REFRESH_FAILURE",
            failure_reason=str(refresh_action.get("reason", "graph_state_auto_refresh_failed")),
            exit_code=2,
            source_layer_hint="GraphStateManager",
            stderr_text=str(refresh_action.get("reason", "")),
            buildcore_reached=False,
            failed_before_validation_gate=True,
            failed_after_validation_gate=False,
        )
        return {
            "status": "FAIL",
            "exit_code": 2,
            "pipeline_execution_order": ["workspace_integrity_check", "graph_state_auto_refresh"],
            "artifacts": [
                "20_graph_state_before.json",
                "21_graph_fingerprint_current.json",
                "22_graph_dirty_reasons.json",
                "23_graph_refresh_action.json",
                "24_graph_state_after.json",
                "25_graph_state_summary.md",
                "build_pipeline_execution.json",
                "pipeline_summary.md",
            ],
        }

    policy_result = evaluate_validation_policy(
        project_root=project_root,
        pf=pf,
        stage="build",
        profile=str(profile or "debug"),
        target=str(target or "build"),
    )
    policy_pass = str(policy_result.get("gate_status", "PASS")).upper() == "PASS"
    envelope.write_stage(
        stage_name="pre-build",
        gate_decision="PASS" if policy_pass else "BLOCK",
        reason_codes=["VALIDATION_POLICY_PASS" if policy_pass else "VALIDATION_POLICY_BLOCK"],
        evidence_refs=[
            "30_policy_input_context.json",
            "31_plugin_policy_matrix.json",
            "32_selected_plugins.json",
            "33_skipped_plugins.json",
            "34_policy_gate_rules.json",
            "35_policy_summary.md",
            "validation_plugins/220_plugin_execution_plan.json",
            "validation_plugins/221_plugin_results.json",
            "validation_plugins/222_plugin_summary.md",
        ],
        missing_inputs=[] if policy_pass else ["policy_gate_pass"],
        normalized_findings=_policy_findings(policy_result, stage_name="pre-build"),
    )
    if str(policy_result.get("gate_status", "PASS")).upper() != "PASS":
        _feedback_safe(
            stage_id="pre-build",
            stage_name="pre-build",
            linked_envelope_hash=_latest_envelope_hash(pf),
            action_id="validation_policy_block_proposal",
            action_proposed=True,
            action_taken=False,
            action_executor="system",
            observed_result_code="ACTION_PROPOSED_FROM_REMEDIATION_GUIDANCE",
            observed_result_summary="Validation policy blocking failures captured as proposed remediation actions.",
            observed_gate_change="BLOCK",
            confidence_adjustment_delta=0.0,
            confidence_adjustment_reason="proposal_only",
            recurrence_impact_category="unchanged",
            recurrence_impact_delta=0.0,
            predictive_calibration_delta=0.0,
            predictive_calibration_reason="metrics_only_no_model_mutation",
            certification_impact="blocked",
            supporting_evidence_refs=["34_policy_gate_rules.json", "validation_plugins/221_plugin_results.json", "43_fix_recommendations.json"],
        )
        envelope.finalize_missing_stages()
        _write_json(
            pf / "build_pipeline_execution.json",
            {
                "status": "FAIL",
                "generated_at": _iso_now(),
                "trigger": trigger,
                "failing_step": "validation_policy_gate",
                "gate_status": policy_result.get("gate_status", "FAIL"),
                "gate_reason": policy_result.get("gate_reason", "blocking_plugin_failure"),
                "blocking_failures": policy_result.get("blocking_failures", []),
                "advisory_failures": policy_result.get("advisory_failures", []),
                "selected_plugins": policy_result.get("selected_plugins", []),
                "buildcore_blocked": True,
            },
        )
        _write_text(
            pf / "pipeline_summary.md",
            "\n".join(
                [
                    "# DevFabEco Build Pipeline Summary",
                    "",
                    "- status: FAIL",
                    "- failing_step: validation_policy_gate",
                    f"- blocking_failures: {', '.join(policy_result.get('blocking_failures', []))}",
                    "- buildcore_blocked: true",
                    "",
                ]
            ),
        )
        analyze_failure(
            project_root=project_root,
            pf=pf,
            command_name=trigger,
            stage_hint="VALIDATION_POLICY_BLOCK",
            failure_reason=str(policy_result.get("gate_reason", "blocking_plugin_failure")),
            exit_code=2,
            source_layer_hint="ValidationPolicyEngine",
            stderr_text="\n".join(str(item) for item in policy_result.get("blocking_failures", [])),
            buildcore_reached=False,
            failed_before_validation_gate=False,
            failed_after_validation_gate=False,
        )
        return {
            "status": "FAIL",
            "exit_code": 2,
            "pipeline_execution_order": ["workspace_integrity_check", "graph_state_auto_refresh", "validation_policy_gate"],
            "artifacts": [
                "30_policy_input_context.json",
                "31_plugin_policy_matrix.json",
                "32_selected_plugins.json",
                "33_skipped_plugins.json",
                "34_policy_gate_rules.json",
                "35_policy_summary.md",
                "validation_plugins/220_plugin_execution_plan.json",
                "validation_plugins/221_plugin_results.json",
                "validation_plugins/222_plugin_summary.md",
                "build_pipeline_execution.json",
                "pipeline_summary.md",
            ],
        }

    started_at = _iso_now()
    failure_step = ""
    failure_message = ""
    traceback_text = ""
    buildcore_outcome: StageOutcome | None = None

    try:
        graph_state = ensure_graph_state_current(project_root=project_root, pf=pf)
        graph_validation = _read_json(pf / "graph_validation_report.json")
        graph_plan = generate_graph_plan(project_root=project_root, pf=pf, graph_state=graph_state)

        buildcore_outcome = execute_buildcore_plan(
            project_root=project_root,
            pf=pf,
            mode=mode,
            target=target,
            profile=profile,
        )
        envelope.write_stage(
            stage_name="execution",
            gate_decision="PASS" if int(buildcore_outcome.exit_code) == 0 else "FAIL",
            reason_codes=["BUILD_EXECUTION_PASS" if int(buildcore_outcome.exit_code) == 0 else "BUILD_EXECUTION_FAILED"],
            evidence_refs=["buildcore_execution_report.json", "pipeline_build_run/build_stdout.txt", "pipeline_build_run/build_stderr.txt"],
            missing_inputs=[] if int(buildcore_outcome.exit_code) == 0 else ["buildcore_success"],
            normalized_findings=[]
            if int(buildcore_outcome.exit_code) == 0
            else [
                make_finding(
                    source_component="NGKsBuildCore",
                    source_artifact="buildcore_execution_report.json",
                    severity="error",
                    reason_code="BUILD_EXECUTION_FAILED",
                    confidence_score=0.98,
                    blocking=True,
                    evidence_refs=["buildcore_execution_report.json", "pipeline_build_run/build_stderr.txt"],
                    stage_name="execution",
                )
            ],
        )
        diagnostics = run_devfabric_diagnostics(
            project_root=project_root,
            pf=pf,
            stage="build",
            profile=str(profile or "debug"),
            target=str(target or "build"),
        )
        diag_status = str(diagnostics.get("status", "PASS")).upper()
        if diag_status == "PASS":
            post_gate = "PASS"
            post_reason = "DIAGNOSTICS_PASS"
        elif diag_status in {"WARN", "ADVISORY"}:
            post_gate = "WARN"
            post_reason = "DIAGNOSTICS_WARN"
        else:
            post_gate = "FAIL"
            post_reason = "DIAGNOSTICS_FAIL"
        envelope.write_stage(
            stage_name="post-build",
            gate_decision=post_gate,
            reason_codes=[post_reason],
            evidence_refs=["devfabric_diagnostics_report.json", "validation_plugins/221_plugin_results.json"],
            missing_inputs=[],
        )
        _feedback_safe(
            stage_id="execution",
            stage_name="execution",
            linked_envelope_hash=_latest_envelope_hash(pf),
            action_id="build_pipeline_execution_action",
            action_proposed=True,
            action_taken=True,
            action_executor="system",
            observed_result_code="ACTION_EXECUTED_SYSTEM",
            observed_result_summary="Build pipeline execution action completed.",
            observed_gate_change="PASS" if int(buildcore_outcome.exit_code) == 0 else "FAIL",
            confidence_adjustment_delta=0.0,
            confidence_adjustment_reason="execution_observation_only",
            recurrence_impact_category="unchanged",
            recurrence_impact_delta=0.0,
            predictive_calibration_delta=0.0,
            predictive_calibration_reason="metrics_only_no_model_mutation",
            certification_impact="none",
            supporting_evidence_refs=["buildcore_execution_report.json", "devfabric_diagnostics_report.json"],
        )

        rerun_summary_path = pf / "pipeline" / "142_certification_rerun_summary.json"
        if rerun_summary_path.exists():
            _feedback_safe(
                stage_id="rerun-remediation",
                stage_name="rerun-remediation",
                linked_envelope_hash=_latest_envelope_hash(pf),
                action_id="rerun_cycle_completed",
                action_proposed=True,
                action_taken=True,
                action_executor="system",
                observed_result_code="RERUN_CYCLE_COMPLETED",
                observed_result_summary="Rerun cycle completion observed from pipeline artifacts.",
                observed_gate_change=str(_read_json(rerun_summary_path).get("enforced_gate", "UNCHANGED")),
                confidence_adjustment_delta=0.0,
                confidence_adjustment_reason="rerun_observation_only",
                recurrence_impact_category="unchanged",
                recurrence_impact_delta=0.0,
                predictive_calibration_delta=0.0,
                predictive_calibration_reason="metrics_only_no_model_mutation",
                certification_impact=str(_read_json(rerun_summary_path).get("certification_decision", "none")),
                supporting_evidence_refs=["pipeline/142_certification_rerun_summary.json", "pipeline/143_pipeline_chain_decision.json"],
            )

        envelope.finalize_missing_stages()

        overall_status = "PASS" if buildcore_outcome.exit_code == 0 else "FAIL"
        if overall_status != "PASS":
            failure_step = "execute_buildcore_plan"
            failure_message = "build stage failed"
            _write_failure_diagnostics(
                pf=pf,
                failing_step=failure_step,
                message=failure_message,
                traceback_text="",
                buildcore_exit_code=buildcore_outcome.exit_code,
            )
            analyze_failure(
                project_root=project_root,
                pf=pf,
                command_name=trigger,
                stage_hint="BUILDCORE_EXECUTION_FAILURE",
                failure_reason=failure_message,
                exit_code=int(buildcore_outcome.exit_code),
                source_layer_hint="BuildCore",
                stderr_text=_read_text(pf / "pipeline_build_run" / "build_stderr.txt"),
                stdout_text=_read_text(pf / "pipeline_build_run" / "build_stdout.txt"),
                buildcore_reached=True,
                failed_before_validation_gate=False,
                failed_after_validation_gate=True,
            )
            _feedback_safe(
                stage_id="post-build",
                stage_name="post-build",
                linked_envelope_hash=_latest_envelope_hash(pf),
                action_id="post_build_failure_proposal",
                action_proposed=True,
                action_taken=False,
                action_executor="system",
                observed_result_code="BUILD_OUTCOME_UNCHANGED",
                observed_result_summary="Build failure persisted after proposed remediation actions.",
                observed_gate_change="FAIL",
                confidence_adjustment_delta=0.0,
                confidence_adjustment_reason="failure_persisted",
                recurrence_impact_category="increased",
                recurrence_impact_delta=1.0,
                predictive_calibration_delta=0.0,
                predictive_calibration_reason="metrics_only_no_model_mutation",
                certification_impact="negative",
                supporting_evidence_refs=["43_fix_recommendations.json", "build_pipeline_execution.json"],
            )
        else:
            if (pf / "43_fix_recommendations.json").exists() or (pf / "fix_recommendations.json").exists():
                _feedback_safe(
                    stage_id="post-build",
                    stage_name="post-build",
                    linked_envelope_hash=_latest_envelope_hash(pf),
                    action_id="post_remediation_outcome_change",
                    action_proposed=True,
                    action_taken=True,
                    action_executor="system",
                    observed_result_code="BUILD_OUTCOME_CHANGED_AFTER_REMEDIATION",
                    observed_result_summary="Build reached PASS after remediation recommendations were recorded.",
                    observed_gate_change="PASS",
                    confidence_adjustment_delta=0.01,
                    confidence_adjustment_reason="successful_outcome_after_remediation",
                    recurrence_impact_category="reduced",
                    recurrence_impact_delta=-1.0,
                    predictive_calibration_delta=0.01,
                    predictive_calibration_reason="CALIBRATION_METRICS_RECORDED",
                    certification_impact="positive",
                    supporting_evidence_refs=["43_fix_recommendations.json", "59_decision_envelope_summary.md"],
                )

        ended_at = _iso_now()
        pipeline_payload = {
            "status": overall_status,
            "generated_at": ended_at,
            "trigger": trigger,
            "pipeline_execution_order": [
                "run_graph_validation",
                "generate_graph_plan",
                "execute_buildcore_plan",
                "run_devfabric_diagnostics",
            ],
            "project_root": str(project_root.resolve()),
            "pf": str(pf),
            "started_at": started_at,
            "ended_at": ended_at,
            "graph_validation": graph_validation,
            "graph_plan": graph_plan,
            "buildcore_execution": buildcore_outcome.details,
            "devfabric_diagnostics": diagnostics,
        }
        _write_json(pf / "build_pipeline_execution.json", pipeline_payload)
        _write_text(
            pf / "pipeline_summary.md",
            "\n".join(
                [
                    "# DevFabEco Build Pipeline Summary",
                    "",
                    f"- trigger: {trigger}",
                    f"- status: {overall_status}",
                    "- pipeline_execution_order: run_graph_validation -> generate_graph_plan -> execute_buildcore_plan -> run_devfabric_diagnostics",
                    f"- graph_refresh_required: {graph_validation.get('graph_refresh_required', False)}",
                    f"- buildcore_exit_code: {buildcore_outcome.exit_code}",
                    f"- diagnostics_status: {diagnostics.get('status', 'PASS')}",
                    f"- diagnostics_plugin_count: {diagnostics.get('plugin_count', 0)}",
                    "",
                ]
            ),
        )
        analyze_failure(
            project_root=project_root,
            pf=pf,
            command_name=trigger,
            stage_hint="UNKNOWN_FAILURE",
            failure_reason=failure_message,
            exit_code=int(buildcore_outcome.exit_code) if buildcore_outcome is not None else 0,
            source_layer_hint="Orchestrator",
            stderr_text=traceback_text,
            buildcore_reached=buildcore_outcome is not None,
            failed_before_validation_gate=False,
            failed_after_validation_gate=buildcore_outcome is not None,
        )
        return {
            "status": overall_status,
            "exit_code": 0 if overall_status == "PASS" else int(buildcore_outcome.exit_code or 1),
            "pipeline_execution_order": pipeline_payload["pipeline_execution_order"],
            "artifacts": [
                "build_pipeline_execution.json",
                "graph_validation_report.json",
                "graph_plan_report.json",
                "buildcore_execution_report.json",
                "devfabric_diagnostics_report.json",
                "pipeline_summary.md",
            ],
        }

    except Exception as exc:  # pragma: no cover - defensive failure contract
        failure_step = failure_step or "orchestrator_exception"
        failure_message = str(exc)
        traceback_text = traceback.format_exc()
        envelope.write_stage(
            stage_name="execution",
            gate_decision="INCOMPLETE",
            reason_codes=["STAGE_EXCEPTION"],
            evidence_refs=["build_pipeline_execution.json"],
            missing_inputs=["execution_completion"],
            normalized_findings=[
                make_finding(
                    source_component="DevFabric",
                    source_artifact="build_pipeline_execution.json",
                    severity="error",
                    reason_code="STAGE_EXCEPTION",
                    confidence_score=1.0,
                    blocking=True,
                    evidence_refs=["failure_trace.json"],
                    stage_name="execution",
                )
            ],
        )
        diagnostics = run_devfabric_diagnostics(
            project_root=project_root,
            pf=pf,
            stage="build",
            profile=str(profile or "debug"),
            target=str(target or "build"),
        )
        envelope.write_stage(
            stage_name="post-build",
            gate_decision="FAIL",
            reason_codes=["DIAGNOSTICS_FAIL"],
            evidence_refs=["devfabric_diagnostics_report.json"],
            missing_inputs=[],
        )
        _feedback_safe(
            stage_id="execution",
            stage_name="execution",
            linked_envelope_hash=_latest_envelope_hash(pf),
            action_id="execution_incomplete_exception",
            action_proposed=True,
            action_taken=False,
            action_executor="system",
            observed_result_code="ACTION_PROPOSED_FROM_ROOT_CAUSE",
            observed_result_summary="Execution exception trapped; remediation action proposed.",
            observed_gate_change="INCOMPLETE",
            confidence_adjustment_delta=0.0,
            confidence_adjustment_reason="exception_observed",
            recurrence_impact_category="increased",
            recurrence_impact_delta=1.0,
            predictive_calibration_delta=0.0,
            predictive_calibration_reason="metrics_only_no_model_mutation",
            certification_impact="negative",
            supporting_evidence_refs=["failure_trace.json", "43_fix_recommendations.json"],
        )
        envelope.finalize_missing_stages()
        buildcore_code = int(buildcore_outcome.exit_code) if buildcore_outcome is not None else 2
        _write_failure_diagnostics(
            pf=pf,
            failing_step=failure_step,
            message=failure_message,
            traceback_text=traceback_text,
            buildcore_exit_code=buildcore_code,
        )
        _write_json(
            pf / "build_pipeline_execution.json",
            {
                "status": "FAIL",
                "generated_at": _iso_now(),
                "trigger": trigger,
                "pipeline_execution_order": [
                    "run_graph_validation",
                    "generate_graph_plan",
                    "execute_buildcore_plan",
                    "run_devfabric_diagnostics",
                ],
                "project_root": str(project_root.resolve()),
                "pf": str(pf),
                "error": failure_message,
                "diagnostics": diagnostics,
            },
        )
        _write_text(
            pf / "pipeline_summary.md",
            "\n".join(
                [
                    "# DevFabEco Build Pipeline Summary",
                    "",
                    "- status: FAIL",
                    f"- failing_step: {failure_step}",
                    f"- message: {failure_message}",
                    "- diagnostics_status: executed",
                    "",
                ]
            ),
        )
        return {
            "status": "FAIL",
            "exit_code": buildcore_code,
            "pipeline_execution_order": [
                "run_graph_validation",
                "generate_graph_plan",
                "execute_buildcore_plan",
                "run_devfabric_diagnostics",
            ],
            "artifacts": [
                "build_pipeline_execution.json",
                "graph_validation_report.json",
                "graph_plan_report.json",
                "buildcore_execution_report.json",
                "devfabric_diagnostics_report.json",
                "failure_trace.json",
                "root_cause_classification.json",
                "fix_recommendations.json",
                "failure_summary.md",
                "pipeline_summary.md",
            ],
        }
