from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric import assignment_policy
from ngksdevfabric.ngk_fabric import team_ownership_mapping


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _ownership_entry(*, component: str, confidence_score: float, scenario_id: str = "s1") -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "metric": "diagnostic_score",
        "severity_score": 0.17,
        "priority_rank": 1,
        "likely_component": component,
        "confidence_score": confidence_score,
        "confidence_level": "HIGH_CONFIDENCE" if confidence_score >= 0.75 else "MEDIUM_CONFIDENCE",
        "evidence_artifacts": [
            "hotspots/10_scenario_regression_ranking.json",
            "hotspots/11_metric_regression_ranking.json",
            "hotspots/13_remediation_guidance.json",
            "baseline_matrix.json",
        ],
        "evidence_sources": {
            "cross_artifact_confirmation": 1.0,
        },
    }


def _policy_entry(pf: Path) -> dict[str, object]:
    payload = json.loads((pf / "hotspots" / "19_assignment_policy.json").read_text(encoding="utf-8"))
    entries = payload.get("entries", []) if isinstance(payload.get("entries", []), list) else []
    assert entries
    top = entries[0]
    assert isinstance(top, dict)
    return top


def test_configured_component_uses_primary_assignee(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_json(
        project_root / "ownership" / "team_map.json",
        {
            "diagnostic_scoring_pipeline": {
                "team": "diagnostics_engineering",
                "primary_assignee": "alice",
                "fallback_assignee": "bob",
                "escalation_owner": "diagnostics_lead",
            }
        },
    )
    pf = tmp_path / "proof" / "configured"

    mapped = team_ownership_mapping.apply_team_ownership_mapping(
        project_root=project_root,
        pf=pf,
        classification="REGRESSED",
        ownership_confidence={"entries": [_ownership_entry(component="diagnostic_scoring_pipeline", confidence_score=0.90)]},
    )
    assignment_policy.generate_assignment_safety_operator_actions(
        pf=pf,
        classification="REGRESSED",
        ownership_confidence=mapped,
    )

    entry = _policy_entry(pf)
    assert str(entry.get("team", "")) == "diagnostics_engineering"
    assert str(entry.get("resolved_assignee", "")) == "alice"


def test_fallback_component_uses_fallback_assignee(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_json(
        project_root / "ownership" / "team_map.json",
        {
            "dependency_graph_resolver": {
                "team": "core_infrastructure",
                "primary_assignee": "",
                "fallback_assignee": "dana",
                "escalation_owner": "platform_lead",
            }
        },
    )
    pf = tmp_path / "proof" / "fallback"

    mapped = team_ownership_mapping.apply_team_ownership_mapping(
        project_root=project_root,
        pf=pf,
        classification="REGRESSED",
        ownership_confidence={"entries": [_ownership_entry(component="dependency_graph_resolver", confidence_score=0.90)]},
    )
    assignment_policy.generate_assignment_safety_operator_actions(
        pf=pf,
        classification="REGRESSED",
        ownership_confidence=mapped,
    )

    entry = _policy_entry(pf)
    assert str(entry.get("resolved_assignee", "")) == "dana"
    assert str(entry.get("assignee_resolution_source", "")) == "fallback_assignee"


def test_unknown_component_uses_inference_fallback(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_json(project_root / "ownership" / "team_map.json", {})
    pf = tmp_path / "proof" / "unknown"

    mapped = team_ownership_mapping.apply_team_ownership_mapping(
        project_root=project_root,
        pf=pf,
        classification="REGRESSED",
        ownership_confidence={"entries": [_ownership_entry(component="unknown_component_x", confidence_score=0.90)]},
    )
    assignment_policy.generate_assignment_safety_operator_actions(
        pf=pf,
        classification="REGRESSED",
        ownership_confidence=mapped,
    )

    entry = _policy_entry(pf)
    assert str(entry.get("mapping_source", "")) == "inferred"
    assert str(entry.get("resolved_assignee", "")).startswith("owner_unknown_component_x")


def test_escalation_required_uses_escalation_owner(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_json(
        project_root / "ownership" / "team_map.json",
        {
            "component_ownership_model": {
                "team": "reliability_operations",
                "primary_assignee": "erin",
                "fallback_assignee": "frank",
                "escalation_owner": "ops_lead",
            }
        },
    )
    pf = tmp_path / "proof" / "escalation"

    mapped = team_ownership_mapping.apply_team_ownership_mapping(
        project_root=project_root,
        pf=pf,
        classification="REGRESSED",
        ownership_confidence={"entries": [_ownership_entry(component="component_ownership_model", confidence_score=0.60)]},
    )
    assignment_policy.generate_assignment_safety_operator_actions(
        pf=pf,
        classification="REGRESSED",
        ownership_confidence=mapped,
    )

    entry = _policy_entry(pf)
    assert str(entry.get("action_policy", "")) == "HUMAN_REVIEW_REQUIRED"
    assert str(entry.get("resolved_assignee", "")) == "ops_lead"
    assert str(entry.get("assignee_resolution_source", "")) == "escalation_owner_human_review"

    assert (pf / "ownership" / "80_component_team_mapping.json").is_file()
    assert (pf / "ownership" / "81_assignee_resolution_results.json").is_file()
    assert (pf / "ownership" / "82_assignment_confidence_adjustments.json").is_file()
    assert (pf / "ownership" / "83_team_assignment_summary.md").is_file()
