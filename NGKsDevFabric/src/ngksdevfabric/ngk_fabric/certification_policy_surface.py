from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CertificationPolicyDecision:
    allow: bool
    rule_id: str
    reason_code: str
    action: str


_RULE_ALLOW = CertificationPolicyDecision(allow=True, rule_id="CERT_POL_ALLOW", reason_code="", action="ALLOW")


CERTIFICATION_POLICY_RULES: dict[str, dict[str, Any]] = {
    "target_not_ready_block": {
        "rule_id": "CERT_POL_001",
        "condition": "target_capability_state == CERTIFICATION_NOT_READY",
        "reason_code": "target_not_ready_blocked",
        "action": "BLOCK",
    },
    "structural_placeholder_block": {
        "rule_id": "CERT_POL_002",
        "condition": "certification_state == BOOTSTRAP_PLACEHOLDER_ONLY",
        "reason_code": "structural_placeholder_only_blocked",
        "action": "BLOCK",
    },
    "structural_drift_block": {
        "rule_id": "CERT_POL_003",
        "condition": "certification_state == PARTIAL_CERTIFICATION_DRIFT",
        "reason_code": "structural_certification_drift_blocked",
        "action": "BLOCK",
    },
    "replay_validation_block": {
        "rule_id": "CERT_POL_004",
        "condition": "replay_validation_status != PASS",
        "reason_code": "replay_validation_failed",
        "action": "BLOCK",
    },
    "compatibility_fail_closed": {
        "rule_id": "CERT_POL_005",
        "condition": "compatibility_state == INCOMPATIBLE",
        "reason_code": "compatibility_incompatible_fail_closed",
        "action": "FAIL_CLOSED",
    },
}


def evaluate_target_capability_state(state: str) -> CertificationPolicyDecision:
    if str(state) == "CERTIFICATION_NOT_READY":
        rule = CERTIFICATION_POLICY_RULES["target_not_ready_block"]
        return CertificationPolicyDecision(
            allow=False,
            rule_id=str(rule["rule_id"]),
            reason_code=str(rule["reason_code"]),
            action=str(rule["action"]),
        )
    return _RULE_ALLOW


def evaluate_structural_certification_state(state: str) -> CertificationPolicyDecision:
    state_value = str(state)
    if state_value == "BOOTSTRAP_PLACEHOLDER_ONLY":
        rule = CERTIFICATION_POLICY_RULES["structural_placeholder_block"]
        return CertificationPolicyDecision(
            allow=False,
            rule_id=str(rule["rule_id"]),
            reason_code=str(rule["reason_code"]),
            action=str(rule["action"]),
        )
    if state_value == "PARTIAL_CERTIFICATION_DRIFT":
        rule = CERTIFICATION_POLICY_RULES["structural_drift_block"]
        return CertificationPolicyDecision(
            allow=False,
            rule_id=str(rule["rule_id"]),
            reason_code=str(rule["reason_code"]),
            action=str(rule["action"]),
        )
    return _RULE_ALLOW


def evaluate_replay_validation_status(status: str) -> CertificationPolicyDecision:
    if str(status).upper() != "PASS":
        rule = CERTIFICATION_POLICY_RULES["replay_validation_block"]
        return CertificationPolicyDecision(
            allow=False,
            rule_id=str(rule["rule_id"]),
            reason_code=str(rule["reason_code"]),
            action=str(rule["action"]),
        )
    return _RULE_ALLOW


def certification_policy_descriptor() -> dict[str, Any]:
    return {
        "policy_surface": "certification_structural_enforcement",
        "schema": "certification_policy_schema.json",
        "rules": CERTIFICATION_POLICY_RULES,
    }
