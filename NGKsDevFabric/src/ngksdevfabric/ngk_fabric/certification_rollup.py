from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certification_target import SubtargetSpec, TargetValidationResult
from .certify_compare import ComparisonPolicy, run_certification_comparison
from .certify_gate import GateEnforcementPolicy
from .execution_profiles import load_execution_profile
from .history_engine import record_regression_history
from .history_trends import analyze_historical_trends
from .resolution_tracking import analyze_regression_resolution


@dataclass(frozen=True)
class RollupPolicy:
    optional_subtarget_incompatibility_blocks_gate: bool = False


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", str(src_dir))


def _classify_from_decision(decision: str) -> str:
    if decision == "CERTIFIED_IMPROVEMENT":
        return "IMPROVED"
    if decision == "CERTIFIED_STABLE":
        return "STABLE"
    if decision == "CERTIFIED_REGRESSION":
        return "REGRESSED"
    return "INCONCLUSIVE"


def _rollup_compatibility(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    required_rows = [row for row in rows if bool(row.get("required", False))]
    optional_rows = [row for row in rows if not bool(row.get("required", False))]

    if any(str(row.get("compatibility_state", "")) == "INCOMPATIBLE" for row in required_rows):
        reasons.append("required_subtarget_incompatible")
        return "INCOMPATIBLE", reasons

    if any(str(row.get("compatibility_state", "")) == "INCOMPATIBLE" for row in optional_rows):
        reasons.append("optional_subtarget_incompatible")
        return "COMPATIBLE_WITH_WARNINGS", reasons

    if any(str(row.get("compatibility_state", "")) == "COMPATIBLE_WITH_WARNINGS" for row in rows):
        reasons.append("subtarget_compatibility_warning_present")
        return "COMPATIBLE_WITH_WARNINGS", reasons

    reasons.append("all_subtargets_compatible")
    return "COMPATIBLE", reasons


def _rollup_decision(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    required_rows = [row for row in rows if bool(row.get("required", False))]
    required_decisions = [str(row.get("certification_decision", "CERTIFICATION_INCONCLUSIVE")) for row in required_rows]

    if any(decision == "CERTIFIED_REGRESSION" for decision in required_decisions):
        reasons.append("required_subtarget_regression")
        return "CERTIFIED_REGRESSION", reasons

    if any(decision == "CERTIFICATION_INCONCLUSIVE" for decision in required_decisions):
        reasons.append("required_subtarget_inconclusive")
        return "CERTIFICATION_INCONCLUSIVE", reasons

    if any(decision == "CERTIFIED_IMPROVEMENT" for decision in required_decisions):
        reasons.append("required_subtarget_improvement_no_required_regression")
        return "CERTIFIED_IMPROVEMENT", reasons

    reasons.append("required_subtargets_stable")
    return "CERTIFIED_STABLE", reasons


def _rollup_gate(rows: list[dict[str, Any]], policy: RollupPolicy) -> tuple[str, str]:
    required_rows = [row for row in rows if bool(row.get("required", False))]
    if any(str(row.get("gate", "FAIL")).upper() != "PASS" for row in required_rows):
        return "FAIL", "required_subtarget_failed_gate"

    optional_rows = [row for row in rows if not bool(row.get("required", False))]
    if policy.optional_subtarget_incompatibility_blocks_gate and any(
        str(row.get("compatibility_state", "")) == "INCOMPATIBLE" for row in optional_rows
    ):
        return "FAIL", "optional_subtarget_incompatible_policy_block"

    if any(str(row.get("gate", "PASS")).upper() != "PASS" for row in optional_rows):
        return "PASS", "optional_subtarget_failed_non_blocking"

    return "PASS", "all_required_subtargets_passed"


def _normalize_subtarget_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: (int(item.get("order", 999999)), str(item.get("subtarget_id", ""))))


def run_subtarget_rollup_comparison(
    *,
    repo_root: Path,
    project_root: Path,
    pf: Path,
    target_result: TargetValidationResult,
    comparison_policy: ComparisonPolicy | None = None,
    rollup_policy: RollupPolicy | None = None,
) -> dict[str, Any]:
    comparison_policy = comparison_policy or ComparisonPolicy()
    rollup_policy = rollup_policy or RollupPolicy()

    profile_state = load_execution_profile(project_root=project_root)
    rollup_dir = pf / "rollup"
    subtarget_root = pf / "subtargets"

    subtarget_rows: list[dict[str, Any]] = []
    for index, subtarget in enumerate(target_result.subtargets, start=1):
        sub_pf = subtarget_root / f"{index:02d}_{subtarget.subtarget_id}"

        if subtarget.ready:
            sub_result = run_certification_comparison(
                repo_root=repo_root,
                baseline_path=subtarget.baseline_root,
                current_path=subtarget.target_root,
                pf=sub_pf,
                policy=comparison_policy,
                supported_baseline_versions=subtarget.supported_baseline_versions,
                profile_project_root=project_root,
                history_enabled=False,
            )
            row = {
                "order": index,
                "subtarget_id": subtarget.subtarget_id,
                "required": subtarget.required,
                "ready": True,
                "target_root": str(subtarget.target_root),
                "baseline_root": str(subtarget.baseline_root),
                "pf": str(sub_pf.resolve()),
                "compatibility_state": str(sub_result.get("compatibility_state", "INCOMPATIBLE")),
                "certification_decision": str(sub_result.get("certification_decision", "CERTIFICATION_INCONCLUSIVE")),
                "classification": str(sub_result.get("classification", "INCONCLUSIVE")),
                "gate": str(sub_result.get("gate", "FAIL")),
                "hotspot_count": len(sub_result.get("hotspot_artifacts", [])),
                "remediation_count": len(sub_result.get("remediation_artifacts", [])),
                "triage_count": len(sub_result.get("triage_artifacts", [])),
                "delivery_count": len(sub_result.get("delivery_artifacts", [])),
                "top_hotspot_scenario": str(sub_result.get("top_hotspot_scenario", "none")),
                "warnings": list(subtarget.warnings),
                "errors": list(subtarget.errors),
            }
        else:
            compat_state = "INCOMPATIBLE" if subtarget.required else "COMPATIBLE_WITH_WARNINGS"
            gate = "FAIL" if subtarget.required else "PASS"
            row = {
                "order": index,
                "subtarget_id": subtarget.subtarget_id,
                "required": subtarget.required,
                "ready": False,
                "target_root": str(subtarget.target_root),
                "baseline_root": str(subtarget.baseline_root),
                "pf": str(sub_pf.resolve()),
                "compatibility_state": compat_state,
                "certification_decision": "CERTIFICATION_INCONCLUSIVE",
                "classification": "INCONCLUSIVE",
                "gate": gate,
                "hotspot_count": 0,
                "remediation_count": 0,
                "triage_count": 0,
                "delivery_count": 0,
                "top_hotspot_scenario": "none",
                "warnings": list(subtarget.warnings),
                "errors": list(subtarget.errors),
            }

        subtarget_rows.append(row)

    subtarget_rows = _normalize_subtarget_rows(subtarget_rows)

    compatibility_state, compatibility_reasons = _rollup_compatibility(subtarget_rows)
    certification_decision, decision_reasons = _rollup_decision(subtarget_rows)
    rollup_gate, rollup_gate_reason = _rollup_gate(subtarget_rows, rollup_policy)
    classification = _classify_from_decision(certification_decision)

    total_hotspots = sum(int(row.get("hotspot_count", 0) or 0) for row in subtarget_rows)
    total_remediation = sum(int(row.get("remediation_count", 0) or 0) for row in subtarget_rows)
    total_triage = sum(int(row.get("triage_count", 0) or 0) for row in subtarget_rows)
    total_delivery = sum(int(row.get("delivery_count", 0) or 0) for row in subtarget_rows)

    history_source_roots = [
        Path(str(row.get("pf", "")))
        for row in subtarget_rows
        if bool(row.get("ready", False)) and str(row.get("pf", "")).strip()
    ]
    history_payload = record_regression_history(
        history_root=project_root / "devfabeco_history",
        pf=pf,
        run_id=pf.name,
        project_name=target_result.project_name,
        execution_profile=profile_state.profile_name,
        certification_decision=certification_decision,
        gate_result=rollup_gate,
        subtarget_count=len(subtarget_rows),
        fingerprint_source_roots=history_source_roots,
    )
    trend_payload = analyze_historical_trends(
        history_root=project_root / "devfabeco_history",
        pf=pf,
    )
    resolution_payload = analyze_regression_resolution(
        history_root=project_root / "devfabeco_history",
        pf=pf,
    )

    rollup_inputs = {
        "timestamp": _iso_now(),
        "project_root": str(project_root.resolve()),
        "profile": profile_state.to_dict(),
        "rollup_rules": {
            "compatibility": {
                "required_incompatible": "INCOMPATIBLE",
                "optional_incompatible": "COMPATIBLE_WITH_WARNINGS",
                "warning_present": "COMPATIBLE_WITH_WARNINGS",
                "otherwise": "COMPATIBLE",
            },
            "decision": {
                "required_regression": "CERTIFIED_REGRESSION",
                "required_inconclusive": "CERTIFICATION_INCONCLUSIVE",
                "required_improvement": "CERTIFIED_IMPROVEMENT",
                "otherwise": "CERTIFIED_STABLE",
            },
            "gate": {
                "required_fail": "FAIL",
                "optional_fail_policy": "non_blocking" if not rollup_policy.optional_subtarget_incompatibility_blocks_gate else "blocking",
                "otherwise": "PASS",
            },
        },
    }

    subtarget_index = {
        "rows": [
            {
                "order": row["order"],
                "subtarget_id": row["subtarget_id"],
                "required": row["required"],
                "ready": row["ready"],
                "pf": row["pf"],
            }
            for row in subtarget_rows
        ]
    }

    compatibility_payload = {
        "compatibility_state": compatibility_state,
        "reasons": compatibility_reasons,
    }
    decision_payload = {
        "certification_decision": certification_decision,
        "classification": classification,
        "reasons": decision_reasons,
    }
    gate_payload = {
        "gate": rollup_gate,
        "reason": rollup_gate_reason,
    }

    hotspots_payload = {
        "enabled": profile_state.is_enabled("hotspot_analysis"),
        "total_hotspots": total_hotspots,
        "subtargets_with_hotspots": [row["subtarget_id"] for row in subtarget_rows if int(row.get("hotspot_count", 0) or 0) > 0],
    }
    remediation_payload = {
        "enabled": profile_state.is_enabled("remediation_guidance"),
        "total_remediation_items": total_remediation,
    }
    triage_payload = {
        "enabled": profile_state.is_enabled("triage_tickets"),
        "total_triage_items": total_triage,
        "total_delivery_items": total_delivery if profile_state.is_enabled("delivery_payload_adapters") else 0,
    }

    _write_json(rollup_dir / "00_rollup_inputs.json", rollup_inputs)
    _write_json(rollup_dir / "01_subtarget_index.json", subtarget_index)
    _write_json(rollup_dir / "02_subtarget_results.json", {"rows": subtarget_rows})
    _write_json(rollup_dir / "03_rollup_compatibility.json", compatibility_payload)
    _write_json(rollup_dir / "04_rollup_decision.json", decision_payload)
    _write_json(rollup_dir / "05_rollup_gate.json", gate_payload)
    _write_json(rollup_dir / "06_rollup_hotspots.json", hotspots_payload)
    _write_json(rollup_dir / "07_rollup_remediation.json", remediation_payload)
    _write_json(rollup_dir / "08_rollup_triage_summary.json", triage_payload)

    summary_lines = [
        "# Subtarget Certification Roll-Up Summary",
        "",
        f"- classification: {classification}",
        f"- certification_decision: {certification_decision}",
        f"- compatibility_state: {compatibility_state}",
        f"- gate: {rollup_gate}",
        f"- gate_reason: {rollup_gate_reason}",
        f"- subtarget_count: {len(subtarget_rows)}",
        f"- required_subtarget_count: {sum(1 for row in subtarget_rows if bool(row.get('required', False)))}",
        f"- optional_subtarget_count: {sum(1 for row in subtarget_rows if not bool(row.get('required', False)))}",
        f"- total_hotspots: {hotspots_payload['total_hotspots']}",
        f"- total_remediation_items: {remediation_payload['total_remediation_items']}",
        f"- total_triage_items: {triage_payload['total_triage_items']}",
        f"- total_delivery_items: {triage_payload['total_delivery_items']}",
        "",
        "## Subtargets",
    ]
    for row in subtarget_rows:
        summary_lines.append(
            f"- {row['subtarget_id']} required={str(bool(row.get('required', False))).lower()} ready={str(bool(row.get('ready', False))).lower()} decision={row['certification_decision']} gate={row['gate']}"
        )
    _write_text(rollup_dir / "09_rollup_summary.md", "\n".join(summary_lines) + "\n")

    classification_json = {
        "overall_classification": classification,
        "certification_decision": certification_decision,
        "gate": rollup_gate,
        "gate_reason": rollup_gate_reason,
        "recommended_next_action": "inspect_subtarget_rollup_artifacts" if rollup_gate == "FAIL" else "proceed_with_rollup_certification",
        "compatibility_state": compatibility_state,
        "rollup_artifacts": [
            "rollup/00_rollup_inputs.json",
            "rollup/01_subtarget_index.json",
            "rollup/02_subtarget_results.json",
            "rollup/03_rollup_compatibility.json",
            "rollup/04_rollup_decision.json",
            "rollup/05_rollup_gate.json",
            "rollup/06_rollup_hotspots.json",
            "rollup/07_rollup_remediation.json",
            "rollup/08_rollup_triage_summary.json",
            "rollup/09_rollup_summary.md",
        ],
        "execution_profile": profile_state.profile_name,
        "execution_profile_artifact_scaling": profile_state.artifact_scaling,
        "history_run_id": str(history_payload.get("history_run_id", "")),
        "history_artifacts": history_payload.get("artifacts", []),
        "history_trend_artifacts": trend_payload.get("artifacts", []),
        "resolution_artifacts": resolution_payload.get("artifacts", []),
        "resolution_summary": resolution_payload.get("summary", {}),
        "subtarget_count": len(subtarget_rows),
        "required_subtarget_count": sum(1 for row in subtarget_rows if bool(row.get("required", False))),
        "optional_subtarget_count": sum(1 for row in subtarget_rows if not bool(row.get("required", False))),
    }

    _write_json(
        pf / "00_run_manifest.json",
        {
            "run_id": pf.name,
            "timestamp": _iso_now(),
            "mode": "certification_rollup_compare",
            "repo_root": str(repo_root.resolve()),
            "project_root": str(project_root.resolve()),
            "subtarget_count": len(subtarget_rows),
        },
    )
    _write_json(pf / "06_classification.json", classification_json)
    _write_text(
        pf / "07_certification_report.md",
        "\n".join(
            [
                "# Certification Roll-Up Report",
                "",
                f"- overall_classification: {classification}",
                f"- certification_decision: {certification_decision}",
                f"- compatibility_state: {compatibility_state}",
                f"- gate: {rollup_gate}",
                f"- gate_reason: {rollup_gate_reason}",
                f"- execution_profile: {profile_state.profile_name}",
                f"- history_run_id: {history_payload.get('history_run_id', '')}",
                f"- recurrence_matches: {len(history_payload.get('recurrence_matches', []))}",
                f"- trend_classification: {trend_payload.get('trend_analysis', {}).get('trend_classification', '')}",
                f"- resolved_regressions: {resolution_payload.get('summary', {}).get('resolved_count', 0)}",
                f"- unresolved_regressions: {resolution_payload.get('summary', {}).get('unresolved_count', 0)}",
                f"- subtarget_count: {len(subtarget_rows)}",
                "",
                "See rollup/09_rollup_summary.md for per-subtarget details.",
                "",
            ]
        ),
    )
    _write_json(
        pf / "08_component_report.json",
        {
            "component": "ngksdevfabric_certification_rollup",
            "status": rollup_gate,
            "classification": classification,
            "certification_decision": certification_decision,
            "compatibility_state": compatibility_state,
            "gate": rollup_gate,
            "gate_reason": rollup_gate_reason,
            "subtarget_count": len(subtarget_rows),
            "timestamp": _iso_now(),
        },
    )
    _write_text(
        pf / "18_summary.md",
        "\n".join(
            [
                "# Certification Roll-Up Summary",
                "",
                f"- overall_classification: {classification}",
                f"- certification_decision: {certification_decision}",
                f"- compatibility_state: {compatibility_state}",
                f"- gate: {rollup_gate}",
                f"- history_run_id: {history_payload.get('history_run_id', '')}",
                f"- trend_classification: {trend_payload.get('trend_analysis', {}).get('trend_classification', '')}",
                f"- resolved_regressions: {resolution_payload.get('summary', {}).get('resolved_count', 0)}",
                f"- unresolved_regressions: {resolution_payload.get('summary', {}).get('unresolved_count', 0)}",
                f"- subtarget_count: {len(subtarget_rows)}",
                "",
            ]
        ),
    )

    zip_path = pf.with_suffix(".zip")
    _zip_dir(pf, zip_path)

    top_hotspot = "none"
    for row in subtarget_rows:
        candidate = str(row.get("top_hotspot_scenario", "none"))
        if candidate and candidate != "none":
            top_hotspot = candidate
            break

    return {
        "classification": classification,
        "certification_decision": certification_decision,
        "strongest_improvement": {"metric": "rollup_not_applicable", "delta": 0.0},
        "worst_regression": {"metric": "rollup_not_applicable", "delta": 0.0},
        "top_hotspot_scenario": top_hotspot,
        "gate": rollup_gate,
        "gate_reason": rollup_gate_reason,
        "recommended_next_action": "inspect_subtarget_rollup_artifacts" if rollup_gate == "FAIL" else "proceed_with_rollup_certification",
        "compatibility_state": compatibility_state,
        "pf": str(pf.resolve()),
        "zip": str(zip_path.resolve()),
    }


def run_subtarget_rollup_gate(
    *,
    repo_root: Path,
    project_root: Path,
    pf: Path,
    target_result: TargetValidationResult,
    comparison_policy: ComparisonPolicy | None = None,
    enforcement_policy: GateEnforcementPolicy | None = None,
    rollup_policy: RollupPolicy | None = None,
) -> dict[str, Any]:
    enforcement_policy = enforcement_policy or GateEnforcementPolicy()

    compare_result = run_subtarget_rollup_comparison(
        repo_root=repo_root,
        project_root=project_root,
        pf=pf,
        target_result=target_result,
        comparison_policy=comparison_policy,
        rollup_policy=rollup_policy,
    )

    decision = str(compare_result.get("certification_decision", "CERTIFICATION_INCONCLUSIVE"))
    compatibility_state = str(compare_result.get("compatibility_state", "INCOMPATIBLE"))
    decision_gate = str(compare_result.get("gate", "FAIL"))
    gate_map = enforcement_policy.resolved_gate_map()
    exit_map = enforcement_policy.resolved_exit_map()

    mapped_gate = str(gate_map.get(decision, "FAIL"))
    exit_code = int(exit_map.get(decision, 1))
    enforcement_reason = "decision_gate_matches_policy"
    if decision_gate != mapped_gate:
        enforcement_reason = "decision_gate_overridden_by_enforcement_policy"
    if compatibility_state == "INCOMPATIBLE":
        mapped_gate = "FAIL"
        exit_code = 1
        enforcement_reason = "compatibility_incompatible_fail_closed"

    next_action = str(compare_result.get("recommended_next_action", "review_rollup_artifacts"))

    _write_json(
        pf / "09_gate_result.json",
        {
            "timestamp": _iso_now(),
            "certification_decision": decision,
            "compatibility_state": compatibility_state,
            "compare_gate": decision_gate,
            "enforced_gate": mapped_gate,
            "exit_code": exit_code,
            "enforcement_reason": enforcement_reason,
            "recommended_next_action": next_action,
            "strict_mode": bool(enforcement_policy.strict_mode),
        },
    )
    _write_json(
        pf / "10_exit_policy.json",
        {
            "decision_to_exit_code": enforcement_policy.resolved_exit_map(),
            "decision_to_gate": enforcement_policy.resolved_gate_map(),
            "strict_mode": bool(enforcement_policy.strict_mode),
            "inconclusive_handling": "nonzero_exit",
            "regression_handling": "nonzero_exit",
        },
    )
    _write_json(
        pf / "11_ci_contract.json",
        {
            "command": "python -m ngksdevfabric certify-gate --project <target>",
            "required_inputs": ["--project"],
            "outputs": {
                "gate_result": str((pf / "09_gate_result.json").resolve()),
                "exit_policy": str((pf / "10_exit_policy.json").resolve()),
                "ci_contract": str((pf / "11_ci_contract.json").resolve()),
                "gate_summary": str((pf / "12_gate_summary.md").resolve()),
                "rollup_summary": str((pf / "rollup" / "09_rollup_summary.md").resolve()),
            },
        },
    )
    _write_text(
        pf / "12_gate_summary.md",
        "\n".join(
            [
                "# Certification Gate Summary",
                "",
                f"- certification_decision: {decision}",
                f"- compatibility_state: {compatibility_state}",
                f"- compare_gate: {decision_gate}",
                f"- enforced_gate: {mapped_gate}",
                f"- exit_code: {exit_code}",
                f"- enforcement_reason: {enforcement_reason}",
                f"- recommended_next_action: {next_action}",
                "",
            ]
        ),
    )

    return {
        "decision": decision,
        "compatibility_state": compatibility_state,
        "compare_gate": decision_gate,
        "enforced_gate": mapped_gate,
        "exit_code": exit_code,
        "enforcement_reason": enforcement_reason,
        "recommended_next_action": next_action,
        "pf": str(pf.resolve()),
        "zip": str(Path(str(compare_result.get("zip", ""))).resolve()),
    }
