"""
certification_bootstrap_templates.py

Pure-data template factories for all certification bootstrap artifacts.
Every generated artifact contains the _bootstrap_managed marker and
placeholder_status so downstream tools and users can clearly identify
bootstrap-generated files versus real certification outputs.

Placeholder value = 0.5 (honest mid-range, not inflated) so that when
both baseline and current proofs use the same value the certify-compare
engine computes delta=0.0 and returns CERTIFIED_STABLE for the bootstrap
placeholder state.

All timestamp fields are fixed to "2000-01-01T00:00:00+00:00" so generated
artifact content is deterministic across invocations.
"""

from __future__ import annotations

GENERATOR_VERSION: str = "1.0.0"
TEMPLATE_VERSION: str = "1.0.0"

_BOOTSTRAP_MANAGED_MARKER: str = "_bootstrap_managed"
_BOOTSTRAP_PLACEHOLDER_VALUE: float = 0.5
_BOOTSTRAP_FIXED_TIMESTAMP: str = "2000-01-01T00:00:00+00:00"
_BOOTSTRAP_PLACEHOLDER_NOTE: str = (
    "Bootstrap placeholder — replace with real certification outputs after first run"
)

# Required metric keys (must match certify_compare._REQUIRED_AGG_METRICS)
_REQUIRED_AGG_METRIC_KEYS: tuple[str, ...] = (
    "average_detection_accuracy",
    "average_component_ownership_accuracy",
    "average_root_cause_accuracy",
    "average_remediation_quality",
    "average_proof_quality",
    "average_diagnostic_score",
)

# Required scenario score keys (must match certify_compare._REQUIRED_SCENARIO_SCORE_KEYS)
_REQUIRED_SCENARIO_SCORE_KEYS: tuple[str, ...] = (
    "detection_accuracy",
    "component_ownership_accuracy",
    "root_cause_accuracy",
    "remediation_quality",
    "proof_quality",
)


def _base_meta(component: str) -> dict:
    return {
        _BOOTSTRAP_MANAGED_MARKER: True,
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "template_origin": "certification_bootstrap_generator",
        "generation_mode": "bootstrap_placeholder",
        "placeholder_status": "template_not_real_certification_result",
        "component": component,
    }


def make_certification_target(*, project_name: str, component: str) -> dict:
    """Top-level certification_target.json contract.

    Required by run_target_validation_precheck() to locate the baseline root
    and scenario index. Fields match the expected contract schema.
    """
    return {
        **_base_meta(component),
        "schema_version": "1.0",
        "project_name": project_name,
        "target_type": "ngksdevfabric_diagnostic",
        "target_root": ".",
        "certification_root": "certification",
        "baseline_root": "certification/baseline_v1",
        "scenario_index_path": "certification/scenario_index.json",
        "supported_baseline_versions": ["v1", "current_run"],
        "required_artifacts": [
            "baseline_manifest",
            "baseline_matrix",
            "diagnostic_metrics",
            "scenario_index",
        ],
        "optional_artifacts": [
            "compatibility_classification",
            "compatibility_report",
        ],
        "execution_profile": "STANDARD",
        "notes": _BOOTSTRAP_PLACEHOLDER_NOTE,
    }


def make_scenario_index(*, component: str, scenario_id: str, scenario_name: str) -> dict:
    """certification/scenario_index.json — scenario registry.

    Required artifact: scenario_index. Must list all scenarios present in the
    baseline matrix so coverage ratio = 1.0.
    """
    return {
        **_base_meta(component),
        "schema_version": "1.0",
        "generated_at": _BOOTSTRAP_FIXED_TIMESTAMP,
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "expected_gate": "PASS",
                "required": True,
                "description": (
                    "Bootstrap baseline scenario — replace with real scenario definitions"
                ),
            }
        ],
        "notes": _BOOTSTRAP_PLACEHOLDER_NOTE,
    }


def make_baseline_manifest(*, component: str, project_name: str) -> dict:
    """certification/baseline_v1/baseline_manifest.json — baseline identity.

    Required artifact: baseline_manifest. Must have non-empty baseline_version
    in supported_baseline_versions (v1 satisfies defaults).
    """
    return {
        **_base_meta(component),
        "baseline_version": "v1",
        "creation_timestamp": _BOOTSTRAP_FIXED_TIMESTAMP,
        "schema_version": "1.0",
        "project_name": project_name,
        "scenario_count": 1,
        "notes": [
            "Bootstrap baseline — placeholder values.",
            "Replace with real baseline after first successful certification run.",
        ],
    }


def make_baseline_matrix(*, component: str, scenario_id: str, scenario_name: str) -> dict:
    """certification/baseline_v1/baseline_matrix.json — per-scenario baseline scores.

    Required artifact: baseline_matrix. Scores must contain all keys from
    _REQUIRED_SCENARIO_SCORE_KEYS. diagnostic_score is computed as an
    aggregate; using 0.5 for all → certify-compare delta with bootstrap current = 0.0.
    """
    return {
        **_base_meta(component),
        "baseline_version": "v1",
        "generated_at": _BOOTSTRAP_FIXED_TIMESTAMP,
        "scenario_count": 1,
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "expected_gate": "PASS",
                "actual_gate": "PASS",
                "diagnostic_score": _BOOTSTRAP_PLACEHOLDER_VALUE,
                "scores": {k: _BOOTSTRAP_PLACEHOLDER_VALUE for k in _REQUIRED_SCENARIO_SCORE_KEYS},
                "notes": "bootstrap_placeholder_replace_with_real_results",
            }
        ],
        "notes": _BOOTSTRAP_PLACEHOLDER_NOTE,
    }


def make_diagnostic_metrics(*, component: str) -> dict:
    """certification/baseline_v1/diagnostic_metrics.json — aggregate baseline metrics.

    Required artifact: diagnostic_metrics. All six keys in _REQUIRED_AGG_METRICS
    must be present and numeric. Using 0.5 for all → delta with bootstrap current = 0.0.
    """
    payload: dict = {
        **_base_meta(component),
        "baseline_version": "v1",
        "generated_at": _BOOTSTRAP_FIXED_TIMESTAMP,
        "scenario_count": 1,
        "notes": (
            "Bootstrap placeholder values — replace with real metrics after "
            "first certification run."
        ),
    }
    for key in _REQUIRED_AGG_METRIC_KEYS:
        payload[key] = _BOOTSTRAP_PLACEHOLDER_VALUE
    return payload


def make_scenario_manifest(
    *, scenario_id: str, scenario_name: str, component: str
) -> dict:
    """00_scenario_manifest.json inside a scenario proof dir.

    Required by _build_current_from_scenario_proofs. Must contain scenario_id.
    """
    return {
        **_base_meta(component),
        "schema_version": "1.0",
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "expected_gate": "PASS",
        "created_at": _BOOTSTRAP_FIXED_TIMESTAMP,
        "notes": (
            "Bootstrap scenario proof — placeholder, replace with real "
            "scenario run outputs."
        ),
    }


def make_actual_outcome(*, scenario_id: str) -> dict:
    """05_actual_outcome.json inside a scenario proof dir.

    Required by _build_current_from_scenario_proofs. actual_result=PASS is a
    structural placeholder, not a real run result.
    """
    return {
        _BOOTSTRAP_MANAGED_MARKER: True,
        "generator_version": GENERATOR_VERSION,
        "placeholder_status": "template_not_real_certification_result",
        "scenario_id": scenario_id,
        "actual_result": "PASS",
        "outcome_timestamp": _BOOTSTRAP_FIXED_TIMESTAMP,
        "notes": (
            "Bootstrap placeholder — actual_result=PASS is a structure placeholder,"
            " not a real run result."
        ),
    }


def make_diagnostic_scorecard(*, scenario_id: str) -> dict:
    """06_diagnostic_scorecard.json inside a scenario proof dir.

    Required by _build_current_from_scenario_proofs. total/max_total give
    diagnostic_score = total/max_total = 5.0/10.0 = 0.5, matching the
    baseline diagnostic_score so delta = 0.0.
    """
    _v = _BOOTSTRAP_PLACEHOLDER_VALUE
    return {
        _BOOTSTRAP_MANAGED_MARKER: True,
        "generator_version": GENERATOR_VERSION,
        "placeholder_status": "template_not_real_certification_result",
        "scenario_id": scenario_id,
        **{k: {"score": _v} for k in _REQUIRED_SCENARIO_SCORE_KEYS},
        "total": _v * 10.0,
        "max_total": 10.0,
        "notes": "Bootstrap placeholder scores — replace with real scenario scorecard outputs.",
    }
