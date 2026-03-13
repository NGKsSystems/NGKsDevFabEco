from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certify_compare import ComparisonPolicy, run_certification_comparison


@dataclass(frozen=True)
class GateEnforcementPolicy:
    strict_mode: bool = True
    decision_to_exit_code: dict[str, int] | None = None
    decision_to_gate: dict[str, str] | None = None

    def resolved_exit_map(self) -> dict[str, int]:
        default = {
            "CERTIFIED_IMPROVEMENT": 0,
            "CERTIFIED_STABLE": 0,
            "CERTIFIED_REGRESSION": 1,
            "CERTIFICATION_INCONCLUSIVE": 1,
        }
        if self.decision_to_exit_code:
            default.update(self.decision_to_exit_code)
        return default

    def resolved_gate_map(self) -> dict[str, str]:
        default = {
            "CERTIFIED_IMPROVEMENT": "PASS",
            "CERTIFIED_STABLE": "PASS",
            "CERTIFIED_REGRESSION": "FAIL",
            "CERTIFICATION_INCONCLUSIVE": "FAIL",
        }
        if self.decision_to_gate:
            default.update(self.decision_to_gate)
        return default


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_certification_gate(
    *,
    repo_root: Path,
    baseline_path: Path,
    current_path: Path,
    pf: Path,
    comparison_policy: ComparisonPolicy | None = None,
    enforcement_policy: GateEnforcementPolicy | None = None,
) -> dict[str, Any]:
    enforcement_policy = enforcement_policy or GateEnforcementPolicy()

    compare_result = run_certification_comparison(
        repo_root=repo_root,
        baseline_path=baseline_path,
        current_path=current_path,
        pf=pf,
        policy=comparison_policy,
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

    next_action = str(compare_result.get("recommended_next_action", "review_gate_artifacts"))

    gate_result = {
        "timestamp": _iso_now(),
        "certification_decision": decision,
        "compatibility_state": compatibility_state,
        "compare_gate": decision_gate,
        "enforced_gate": mapped_gate,
        "exit_code": exit_code,
        "enforcement_reason": enforcement_reason,
        "recommended_next_action": next_action,
        "strict_mode": bool(enforcement_policy.strict_mode),
    }
    _write_json(pf / "09_gate_result.json", gate_result)

    exit_policy = {
        "decision_to_exit_code": exit_map,
        "decision_to_gate": gate_map,
        "strict_mode": bool(enforcement_policy.strict_mode),
        "inconclusive_handling": "nonzero_exit",
        "regression_handling": "nonzero_exit",
    }
    _write_json(pf / "10_exit_policy.json", exit_policy)

    ci_contract = {
        "command": "python -m ngksdevfabric certify-gate --project <target> --baseline <baseline_path>",
        "required_inputs": [
            "--project",
            "--baseline",
        ],
        "outputs": {
            "gate_result": str((pf / "09_gate_result.json").resolve()),
            "exit_policy": str((pf / "10_exit_policy.json").resolve()),
            "ci_contract": str((pf / "11_ci_contract.json").resolve()),
            "gate_summary": str((pf / "12_gate_summary.md").resolve()),
            "classification": str((pf / "06_classification.json").resolve()),
            "decision_evaluation": str((pf / "10_decision_evaluation.json").resolve()),
        },
        "success_behavior": "exit_code=0 when decision is CERTIFIED_IMPROVEMENT or CERTIFIED_STABLE",
        "failure_behavior": "exit_code!=0 when decision is CERTIFIED_REGRESSION or CERTIFICATION_INCONCLUSIVE",
    }
    _write_json(pf / "11_ci_contract.json", ci_contract)

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
