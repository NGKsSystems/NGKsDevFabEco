from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certification_compatibility import run_compatibility_preflight

_REQUIRED_AGG_METRICS = [
    "average_detection_accuracy",
    "average_component_ownership_accuracy",
    "average_root_cause_accuracy",
    "average_remediation_quality",
    "average_proof_quality",
    "average_diagnostic_score",
]

_REQUIRED_SCENARIO_SCORE_KEYS = [
    "detection_accuracy",
    "component_ownership_accuracy",
    "root_cause_accuracy",
    "remediation_quality",
    "proof_quality",
]

_SCENARIO_DIR_RE = re.compile(r"^(\d{8}_\d{6})_(.+)$")

_DECISION_GATE_POLICY: dict[str, dict[str, str]] = {
    "CERTIFIED_IMPROVEMENT": {
        "gate": "PASS",
        "reason": "improvement_verified_no_severe_regression",
        "recommended_next_action": "promote_or_continue_monitoring",
    },
    "CERTIFIED_STABLE": {
        "gate": "PASS",
        "reason": "within_tolerance_no_severe_regression",
        "recommended_next_action": "continue_periodic_validation",
    },
    "CERTIFIED_REGRESSION": {
        "gate": "FAIL",
        "reason": "meaningful_regression_detected",
        "recommended_next_action": "block_release_and_fix_regression",
    },
    "CERTIFICATION_INCONCLUSIVE": {
        "gate": "FAIL",
        "reason": "insufficient_or_incompatible_inputs",
        "recommended_next_action": "repair_inputs_and_rerun",
    },
}


@dataclass(frozen=True)
class ComparisonPolicy:
    diagnostic_score_tolerance: float = 0.02
    diagnostic_score_improvement_threshold: float = 0.03
    severe_core_drop_threshold: float = 0.15


@dataclass(frozen=True)
class DecisionPolicy:
    minimum_diagnostic_score_delta_for_improvement: float = 0.03
    stable_tolerance_band: float = 0.02
    maximum_tolerated_root_cause_drop: float = 0.10
    maximum_tolerated_component_ownership_drop: float = 0.10
    critical_categories: tuple[str, ...] = (
        "average_root_cause_accuracy",
        "average_component_ownership_accuracy",
    )
    critical_scenario_ids: tuple[str, ...] = ("baseline_pass",)
    severe_scenario_diagnostic_drop: float = 0.15
    medium_scenario_diagnostic_drop: float = 0.05
    required_scenario_coverage_ratio: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_diagnostic_score_delta_for_improvement": self.minimum_diagnostic_score_delta_for_improvement,
            "stable_tolerance_band": self.stable_tolerance_band,
            "maximum_tolerated_root_cause_drop": self.maximum_tolerated_root_cause_drop,
            "maximum_tolerated_component_ownership_drop": self.maximum_tolerated_component_ownership_drop,
            "critical_categories": list(self.critical_categories),
            "critical_scenario_ids": list(self.critical_scenario_ids),
            "severe_scenario_diagnostic_drop": self.severe_scenario_diagnostic_drop,
            "medium_scenario_diagnostic_drop": self.medium_scenario_diagnostic_drop,
            "required_scenario_coverage_ratio": self.required_scenario_coverage_ratio,
        }


@dataclass(frozen=True)
class BaselineBundle:
    root: Path
    baseline_matrix_path: Path
    diagnostic_metrics_path: Path
    baseline_manifest_path: Path


@dataclass(frozen=True)
class CurrentBundle:
    root: Path
    source_mode: str
    baseline_matrix_path: Path | None
    diagnostic_metrics_path: Path | None
    baseline_manifest_path: Path | None
    scenario_proof_root: Path | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"invalid_json:{path}:{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid_json_object:{path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _zip_dir(bundle_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", str(bundle_dir))


def _resolve_baseline_bundle(baseline_path: Path) -> BaselineBundle:
    p = baseline_path.resolve()
    candidates = [
        {
            "root": p,
            "matrix": p / "baseline_matrix.json",
            "metrics": p / "diagnostic_metrics.json",
            "manifest": p / "baseline_manifest.json",
        },
        {
            "root": p / "baseline_v1",
            "matrix": p / "baseline_v1" / "baseline_matrix.json",
            "metrics": p / "baseline_v1" / "diagnostic_metrics.json",
            "manifest": p / "baseline_v1" / "baseline_manifest.json",
        },
        {
            "root": p,
            "matrix": p / "05_baseline_matrix.json",
            "metrics": p / "06_diagnostic_metrics.json",
            "manifest": p / "08_baseline_manifest.json",
        },
    ]

    for candidate in candidates:
        if all(Path(candidate[key]).is_file() for key in ("matrix", "metrics", "manifest")):
            return BaselineBundle(
                root=Path(candidate["root"]),
                baseline_matrix_path=Path(candidate["matrix"]),
                diagnostic_metrics_path=Path(candidate["metrics"]),
                baseline_manifest_path=Path(candidate["manifest"]),
            )

    raise ValueError(
        "baseline_bundle_not_found: expected baseline_matrix.json, diagnostic_metrics.json, baseline_manifest.json"
    )


def _resolve_current_bundle(current_path: Path) -> CurrentBundle:
    p = current_path.resolve()
    direct = [
        {
            "matrix": p / "baseline_matrix.json",
            "metrics": p / "diagnostic_metrics.json",
            "manifest": p / "baseline_manifest.json",
        },
        {
            "matrix": p / "05_baseline_matrix.json",
            "metrics": p / "06_diagnostic_metrics.json",
            "manifest": p / "08_baseline_manifest.json",
        },
    ]
    for candidate in direct:
        if all(Path(candidate[key]).is_file() for key in ("matrix", "metrics", "manifest")):
            return CurrentBundle(
                root=p,
                source_mode="aggregate_files",
                baseline_matrix_path=Path(candidate["matrix"]),
                diagnostic_metrics_path=Path(candidate["metrics"]),
                baseline_manifest_path=Path(candidate["manifest"]),
                scenario_proof_root=None,
            )

    proof_root = p / "certification" / "_proof"
    if proof_root.is_dir():
        return CurrentBundle(
            root=p,
            source_mode="scenario_proofs",
            baseline_matrix_path=None,
            diagnostic_metrics_path=None,
            baseline_manifest_path=None,
            scenario_proof_root=proof_root,
        )

    raise ValueError(
        "current_bundle_not_found: expected aggregate files or certification/_proof scenario packets"
    )


def _validate_baseline_shape(matrix: dict[str, Any], metrics: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(matrix.get("scenarios"), list):
        errors.append("baseline_matrix.scenarios_missing")
    for metric_key in _REQUIRED_AGG_METRICS:
        if metric_key not in metrics:
            errors.append(f"diagnostic_metrics.missing:{metric_key}")
    if not str(manifest.get("baseline_version", "")).strip():
        errors.append("baseline_manifest.baseline_version_missing")
    return errors


def _scenario_timestamp_key(path: Path) -> tuple[str, str]:
    match = _SCENARIO_DIR_RE.match(path.name)
    if not match:
        return ("", path.name)
    return (match.group(1), match.group(2))


def _score_value(score_obj: object) -> float:
    if isinstance(score_obj, dict):
        raw = score_obj.get("score", 0)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(score_obj)
    except (TypeError, ValueError):
        return 0.0


def _build_current_from_scenario_proofs(proof_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    errors: list[str] = []
    latest_by_scenario: dict[str, tuple[Path, str]] = {}

    for scenario_dir in sorted(proof_root.iterdir(), key=lambda p: p.name):
        if not scenario_dir.is_dir():
            continue
        manifest_path = scenario_dir / "00_scenario_manifest.json"
        scorecard_path = scenario_dir / "06_diagnostic_scorecard.json"
        actual_outcome_path = scenario_dir / "05_actual_outcome.json"
        if not (manifest_path.is_file() and scorecard_path.is_file() and actual_outcome_path.is_file()):
            continue
        try:
            manifest = _read_json(manifest_path)
            scenario_id = str(manifest.get("scenario_id", "")).strip()
            if not scenario_id:
                continue
        except ValueError:
            continue
        stamp, _ = _scenario_timestamp_key(scenario_dir)
        prev = latest_by_scenario.get(scenario_id)
        if prev is None or stamp > prev[1]:
            latest_by_scenario[scenario_id] = (scenario_dir, stamp)

    if not latest_by_scenario:
        raise ValueError("current_scenarios_missing: no scenario proof packets with required files found")

    scenarios: list[dict[str, Any]] = []
    totals = {
        "average_detection_accuracy": 0.0,
        "average_component_ownership_accuracy": 0.0,
        "average_root_cause_accuracy": 0.0,
        "average_remediation_quality": 0.0,
        "average_proof_quality": 0.0,
        "average_diagnostic_score": 0.0,
    }

    for scenario_id in sorted(latest_by_scenario.keys()):
        scenario_dir, _stamp = latest_by_scenario[scenario_id]
        manifest = _read_json(scenario_dir / "00_scenario_manifest.json")
        scorecard = _read_json(scenario_dir / "06_diagnostic_scorecard.json")
        actual_outcome = _read_json(scenario_dir / "05_actual_outcome.json")

        scenario_scores: dict[str, float] = {}
        for key in _REQUIRED_SCENARIO_SCORE_KEYS:
            scenario_scores[key] = _score_value(scorecard.get(key, {}))

        max_total = float(scorecard.get("max_total", 10) or 10)
        total = float(scorecard.get("total", 0) or 0)
        diagnostic_score = (total / max_total) if max_total > 0 else 0.0

        totals["average_detection_accuracy"] += scenario_scores["detection_accuracy"]
        totals["average_component_ownership_accuracy"] += scenario_scores["component_ownership_accuracy"]
        totals["average_root_cause_accuracy"] += scenario_scores["root_cause_accuracy"]
        totals["average_remediation_quality"] += scenario_scores["remediation_quality"]
        totals["average_proof_quality"] += scenario_scores["proof_quality"]
        totals["average_diagnostic_score"] += diagnostic_score

        scenario_row = {
            "scenario_id": scenario_id,
            "scenario_name": str(manifest.get("scenario_name", scenario_id)),
            "expected_gate": str(manifest.get("expected_gate", "")).upper(),
            "actual_gate": str(actual_outcome.get("actual_result", "")).upper(),
            "diagnostic_score": round(diagnostic_score, 4),
            "scores": {
                "detection_accuracy": scenario_scores["detection_accuracy"],
                "component_ownership_accuracy": scenario_scores["component_ownership_accuracy"],
                "root_cause_accuracy": scenario_scores["root_cause_accuracy"],
                "remediation_quality": scenario_scores["remediation_quality"],
                "proof_quality": scenario_scores["proof_quality"],
            },
            "proof_folder": str(scenario_dir.resolve()),
        }
        scenarios.append(scenario_row)

    count = float(len(scenarios))
    metrics = {
        "baseline_version": "current_run",
        "generated_at": _iso_now(),
        "scenario_count": int(count),
        "average_detection_accuracy": round(totals["average_detection_accuracy"] / count, 4),
        "average_component_ownership_accuracy": round(totals["average_component_ownership_accuracy"] / count, 4),
        "average_root_cause_accuracy": round(totals["average_root_cause_accuracy"] / count, 4),
        "average_remediation_quality": round(totals["average_remediation_quality"] / count, 4),
        "average_proof_quality": round(totals["average_proof_quality"] / count, 4),
        "average_diagnostic_score": round(totals["average_diagnostic_score"] / count, 4),
    }
    matrix = {
        "baseline_version": "current_run",
        "generated_at": _iso_now(),
        "scenarios": scenarios,
    }
    manifest = {
        "baseline_version": "current_run",
        "creation_timestamp": _iso_now(),
        "scenario_count": int(count),
        "notes": ["Generated from certification scenario proof packets"],
    }
    return matrix, metrics, manifest, errors


def _to_scenario_map(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in matrix.get("scenarios", []):
        if not isinstance(item, dict):
            continue
        scenario_id = str(item.get("scenario_id", "")).strip()
        if not scenario_id:
            continue
        out[scenario_id] = item
    return out


def _scenario_metric_value(row: dict[str, Any], score_key: str) -> float:
    scores = row.get("scores", {}) if isinstance(row.get("scores"), dict) else {}
    value = scores.get(score_key, 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_float(data: dict[str, Any], key: str) -> float:
    try:
        return float(data.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _classify(aggregate_diff: dict[str, Any], policy: ComparisonPolicy, validation_errors: list[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if validation_errors:
        reasons.extend(validation_errors)
        return "INCONCLUSIVE", reasons

    diag_delta = float(aggregate_diff.get("average_diagnostic_score", {}).get("delta", 0.0))
    own_delta = float(aggregate_diff.get("average_component_ownership_accuracy", {}).get("delta", 0.0))
    root_delta = float(aggregate_diff.get("average_root_cause_accuracy", {}).get("delta", 0.0))

    severe_drop = own_delta <= -policy.severe_core_drop_threshold or root_delta <= -policy.severe_core_drop_threshold

    if severe_drop:
        reasons.append("severe_drop_in_core_categories")
        return "REGRESSED", reasons

    if diag_delta >= policy.diagnostic_score_improvement_threshold:
        reasons.append("diagnostic_score_improved_beyond_threshold")
        return "IMPROVED", reasons

    if diag_delta <= -policy.diagnostic_score_improvement_threshold:
        reasons.append("diagnostic_score_regressed_beyond_threshold")
        return "REGRESSED", reasons

    if abs(diag_delta) <= policy.diagnostic_score_tolerance:
        reasons.append("diagnostic_score_within_tolerance")
        return "UNCHANGED", reasons

    reasons.append("minor_change_below_improvement_threshold")
    return "UNCHANGED", reasons


def _evaluate_decision(
    *,
    aggregate_diff: dict[str, Any],
    scenario_diff_rows: list[dict[str, Any]],
    validation_errors: list[str],
    coverage_ratio: float,
    policy: DecisionPolicy,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons: list[str] = []

    diag_delta = float(aggregate_diff.get("average_diagnostic_score", {}).get("delta", 0.0))
    root_delta = float(aggregate_diff.get("average_root_cause_accuracy", {}).get("delta", 0.0))
    owner_delta = float(aggregate_diff.get("average_component_ownership_accuracy", {}).get("delta", 0.0))

    hotspots: list[dict[str, Any]] = []
    severe_regression_count = 0
    medium_regression_count = 0
    improvement_count = 0

    critical_ids = set(policy.critical_scenario_ids)
    for row in scenario_diff_rows:
        if row.get("status") == "missing":
            continue
        scenario_id = str(row.get("scenario_id", ""))
        delta_diag = float(row.get("delta_diagnostic_score", 0.0))
        delta_root = float(row.get("delta_root_cause_accuracy", 0.0))
        delta_owner = float(row.get("delta_ownership_accuracy", 0.0))
        delta_rem = float(row.get("delta_remediation_quality", 0.0))
        delta_proof = float(row.get("delta_proof_quality", 0.0))

        severity = "low"
        severity_reasons: list[str] = []
        if scenario_id in critical_ids and (delta_root < 0 or delta_owner < 0):
            severity = "high"
            severity_reasons.append("critical_scenario_core_metric_drop")
        elif (
            delta_diag <= -policy.severe_scenario_diagnostic_drop
            or delta_root < -policy.maximum_tolerated_root_cause_drop
            or delta_owner < -policy.maximum_tolerated_component_ownership_drop
        ):
            severity = "high"
            severity_reasons.append("severe_metric_drop")
        elif delta_diag <= -policy.medium_scenario_diagnostic_drop or delta_rem < 0 or delta_proof < 0:
            severity = "medium"
            severity_reasons.append("medium_metric_drop")

        if delta_diag > policy.stable_tolerance_band:
            improvement_count += 1
        if severity == "high" and delta_diag < 0:
            severe_regression_count += 1
        elif severity == "medium" and delta_diag < 0:
            medium_regression_count += 1

        if delta_diag < 0 or delta_root < 0 or delta_owner < 0:
            hotspots.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_name": row.get("scenario_name", scenario_id),
                    "severity": severity,
                    "severity_reasons": severity_reasons,
                    "delta_diagnostic_score": delta_diag,
                    "delta_root_cause_accuracy": delta_root,
                    "delta_ownership_accuracy": delta_owner,
                }
            )

    def _severity_rank(value: str) -> int:
        return {"high": 0, "medium": 1, "low": 2}.get(value, 3)

    hotspots = sorted(
        hotspots,
        key=lambda item: (_severity_rank(str(item.get("severity", "low"))), float(item.get("delta_diagnostic_score", 0.0))),
    )

    if validation_errors:
        reasons.extend(validation_errors)
        decision = "CERTIFICATION_INCONCLUSIVE"
    elif coverage_ratio < policy.required_scenario_coverage_ratio:
        reasons.append("insufficient_scenario_coverage")
        decision = "CERTIFICATION_INCONCLUSIVE"
    elif root_delta < -policy.maximum_tolerated_root_cause_drop or owner_delta < -policy.maximum_tolerated_component_ownership_drop:
        reasons.append("critical_category_drop_exceeded_tolerance")
        decision = "CERTIFIED_REGRESSION"
    elif severe_regression_count > 0:
        reasons.append("severe_scenario_regression_detected")
        decision = "CERTIFIED_REGRESSION"
    elif diag_delta >= policy.minimum_diagnostic_score_delta_for_improvement and severe_regression_count == 0:
        reasons.append("meaningful_aggregate_improvement_without_severe_regressions")
        decision = "CERTIFIED_IMPROVEMENT"
    elif abs(diag_delta) <= policy.stable_tolerance_band and severe_regression_count == 0:
        reasons.append("within_stable_tolerance_and_no_severe_regressions")
        decision = "CERTIFIED_STABLE"
    else:
        reasons.append("mixed_or_minor_movement")
        decision = "CERTIFIED_STABLE"

    decision_eval = {
        "decision": decision,
        "reasons": reasons,
        "coverage_ratio": round(coverage_ratio, 4),
        "aggregate_signals": {
            "average_diagnostic_score_delta": diag_delta,
            "average_root_cause_accuracy_delta": root_delta,
            "average_component_ownership_accuracy_delta": owner_delta,
        },
        "scenario_signals": {
            "severe_regression_count": severe_regression_count,
            "medium_regression_count": medium_regression_count,
            "improvement_count": improvement_count,
            "hotspot_count": len(hotspots),
        },
    }
    return decision_eval, hotspots


def _decision_gate_outcome(decision: str) -> dict[str, str]:
    return dict(
        _DECISION_GATE_POLICY.get(
            decision,
            {
                "gate": "FAIL",
                "reason": "unknown_decision_state",
                "recommended_next_action": "inspect_decision_engine_output",
            },
        )
    )


def run_certification_comparison(
    *,
    repo_root: Path,
    baseline_path: Path,
    current_path: Path,
    pf: Path,
    policy: ComparisonPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or ComparisonPolicy()
    decision_policy = DecisionPolicy()
    run_id = pf.name
    pf.mkdir(parents=True, exist_ok=True)

    validation_errors: list[str] = []

    baseline_bundle = _resolve_baseline_bundle(baseline_path)
    current_bundle = _resolve_current_bundle(current_path)

    baseline_matrix = _read_json(baseline_bundle.baseline_matrix_path)
    baseline_metrics = _read_json(baseline_bundle.diagnostic_metrics_path)
    baseline_manifest = _read_json(baseline_bundle.baseline_manifest_path)

    validation_errors.extend(_validate_baseline_shape(baseline_matrix, baseline_metrics, baseline_manifest))

    if current_bundle.source_mode == "aggregate_files":
        assert current_bundle.baseline_matrix_path is not None
        assert current_bundle.diagnostic_metrics_path is not None
        assert current_bundle.baseline_manifest_path is not None
        current_matrix = _read_json(current_bundle.baseline_matrix_path)
        current_metrics = _read_json(current_bundle.diagnostic_metrics_path)
        current_manifest = _read_json(current_bundle.baseline_manifest_path)
        validation_errors.extend(_validate_baseline_shape(current_matrix, current_metrics, current_manifest))
    else:
        assert current_bundle.scenario_proof_root is not None
        current_matrix, current_metrics, current_manifest, current_errors = _build_current_from_scenario_proofs(
            current_bundle.scenario_proof_root
        )
        validation_errors.extend(current_errors)

    compatibility_result = run_compatibility_preflight(
        repo_root=repo_root,
        pf=pf,
        baseline_bundle_root=baseline_bundle.root,
        baseline_matrix_path=baseline_bundle.baseline_matrix_path,
        baseline_metrics_path=baseline_bundle.diagnostic_metrics_path,
        baseline_manifest_path=baseline_bundle.baseline_manifest_path,
        current_bundle_root=current_bundle.root,
        current_source_mode=current_bundle.source_mode,
        current_matrix_path=current_bundle.baseline_matrix_path,
        current_metrics_path=current_bundle.diagnostic_metrics_path,
        current_manifest_path=current_bundle.baseline_manifest_path,
        current_scenario_proof_root=current_bundle.scenario_proof_root,
        baseline_matrix=baseline_matrix,
        baseline_metrics=baseline_metrics,
        baseline_manifest=baseline_manifest,
        current_matrix=current_matrix,
        current_metrics=current_metrics,
        current_manifest=current_manifest,
        required_metric_keys=_REQUIRED_AGG_METRICS,
    )

    if compatibility_result.state == "INCOMPATIBLE":
        validation_errors.append("compatibility_incompatible")
        validation_errors.extend(compatibility_result.errors)

    baseline_scenarios = _to_scenario_map(baseline_matrix)
    current_scenarios = _to_scenario_map(current_matrix)

    if not baseline_scenarios:
        validation_errors.append("baseline_scenarios_missing")
    if not current_scenarios:
        validation_errors.append("current_scenarios_missing")

    missing_in_current = sorted(set(baseline_scenarios.keys()) - set(current_scenarios.keys()))
    if missing_in_current:
        validation_errors.append(f"missing_scenarios_in_current:{','.join(missing_in_current)}")

    missing_in_baseline = sorted(set(current_scenarios.keys()) - set(baseline_scenarios.keys()))

    aggregate_diff: dict[str, Any] = {}
    for metric_key in _REQUIRED_AGG_METRICS:
        baseline_value = _safe_float(baseline_metrics, metric_key)
        current_value = _safe_float(current_metrics, metric_key)
        aggregate_diff[metric_key] = {
            "baseline": round(baseline_value, 4),
            "current": round(current_value, 4),
            "delta": round(current_value - baseline_value, 4),
        }

    scenario_diff_rows: list[dict[str, Any]] = []
    for scenario_id in sorted(set(baseline_scenarios.keys()) | set(current_scenarios.keys())):
        base = baseline_scenarios.get(scenario_id)
        curr = current_scenarios.get(scenario_id)
        if base is None or curr is None:
            scenario_diff_rows.append(
                {
                    "scenario_id": scenario_id,
                    "status": "missing",
                    "baseline_present": base is not None,
                    "current_present": curr is not None,
                }
            )
            continue

        baseline_diag = _safe_float(base, "diagnostic_score")
        current_diag = _safe_float(curr, "diagnostic_score")
        baseline_root = _scenario_metric_value(base, "root_cause_accuracy")
        current_root = _scenario_metric_value(curr, "root_cause_accuracy")
        baseline_owner = _scenario_metric_value(base, "component_ownership_accuracy")
        current_owner = _scenario_metric_value(curr, "component_ownership_accuracy")
        baseline_remediation = _scenario_metric_value(base, "remediation_quality")
        current_remediation = _scenario_metric_value(curr, "remediation_quality")
        baseline_proof = _scenario_metric_value(base, "proof_quality")
        current_proof = _scenario_metric_value(curr, "proof_quality")

        scenario_diff_rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_name": str(curr.get("scenario_name", base.get("scenario_name", scenario_id))),
                "expected_gate": str(curr.get("expected_gate", base.get("expected_gate", ""))).upper(),
                "baseline_actual_gate": str(base.get("actual_gate", "")).upper(),
                "current_actual_gate": str(curr.get("actual_gate", "")).upper(),
                "baseline_diagnostic_score": round(baseline_diag, 4),
                "current_diagnostic_score": round(current_diag, 4),
                "delta_diagnostic_score": round(current_diag - baseline_diag, 4),
                "baseline_root_cause_accuracy": round(baseline_root, 4),
                "current_root_cause_accuracy": round(current_root, 4),
                "delta_root_cause_accuracy": round(current_root - baseline_root, 4),
                "baseline_ownership_accuracy": round(baseline_owner, 4),
                "current_ownership_accuracy": round(current_owner, 4),
                "delta_ownership_accuracy": round(current_owner - baseline_owner, 4),
                "baseline_remediation_quality": round(baseline_remediation, 4),
                "current_remediation_quality": round(current_remediation, 4),
                "delta_remediation_quality": round(current_remediation - baseline_remediation, 4),
                "baseline_proof_quality": round(baseline_proof, 4),
                "current_proof_quality": round(current_proof, 4),
                "delta_proof_quality": round(current_proof - baseline_proof, 4),
            }
        )

    classification, class_reasons = _classify(aggregate_diff, policy, validation_errors)
    baseline_count = max(len(baseline_scenarios), 1)
    coverage_ratio = len(current_scenarios) / baseline_count
    decision_eval, hotspots = _evaluate_decision(
        aggregate_diff=aggregate_diff,
        scenario_diff_rows=scenario_diff_rows,
        validation_errors=validation_errors,
        coverage_ratio=coverage_ratio,
        policy=decision_policy,
    )
    certification_decision = str(decision_eval.get("decision", "CERTIFICATION_INCONCLUSIVE"))
    gate_outcome = _decision_gate_outcome(certification_decision)

    metric_rows = sorted(
        [
            {
                "metric": key,
                "baseline": value["baseline"],
                "current": value["current"],
                "delta": value["delta"],
            }
            for key, value in aggregate_diff.items()
        ],
        key=lambda row: row["delta"],
        reverse=True,
    )
    strongest_improvement = metric_rows[0] if metric_rows else {"metric": "none", "delta": 0.0}
    worst_regression = metric_rows[-1] if metric_rows else {"metric": "none", "delta": 0.0}

    run_manifest = {
        "run_id": run_id,
        "timestamp": _iso_now(),
        "mode": "certification_compare",
        "repo_root": str(repo_root.resolve()),
        "policy": {
            "diagnostic_score_tolerance": policy.diagnostic_score_tolerance,
            "diagnostic_score_improvement_threshold": policy.diagnostic_score_improvement_threshold,
            "severe_core_drop_threshold": policy.severe_core_drop_threshold,
        },
    }

    inputs_json = {
        "baseline_input": str(baseline_path.resolve()),
        "current_input": str(current_path.resolve()),
        "baseline_bundle": {
            "root": str(baseline_bundle.root.resolve()),
            "baseline_matrix": str(baseline_bundle.baseline_matrix_path.resolve()),
            "diagnostic_metrics": str(baseline_bundle.diagnostic_metrics_path.resolve()),
            "baseline_manifest": str(baseline_bundle.baseline_manifest_path.resolve()),
        },
        "current_bundle": {
            "root": str(current_bundle.root.resolve()),
            "source_mode": current_bundle.source_mode,
            "baseline_matrix": str(current_bundle.baseline_matrix_path.resolve()) if current_bundle.baseline_matrix_path else "",
            "diagnostic_metrics": str(current_bundle.diagnostic_metrics_path.resolve()) if current_bundle.diagnostic_metrics_path else "",
            "baseline_manifest": str(current_bundle.baseline_manifest_path.resolve()) if current_bundle.baseline_manifest_path else "",
            "scenario_proof_root": str(current_bundle.scenario_proof_root.resolve()) if current_bundle.scenario_proof_root else "",
        },
    }

    baseline_load = {
        "status": "ok" if not validation_errors else "validation_errors",
        "baseline_version": str(baseline_manifest.get("baseline_version", "")),
        "scenario_count": len(baseline_scenarios),
        "required_metrics_present": [k for k in _REQUIRED_AGG_METRICS if k in baseline_metrics],
    }

    current_load = {
        "status": "ok" if not validation_errors else "validation_errors",
        "source_mode": current_bundle.source_mode,
        "scenario_count": len(current_scenarios),
        "missing_scenarios_in_current": missing_in_current,
        "extra_scenarios_in_current": missing_in_baseline,
    }

    metric_diff = {
        "aggregate_diff": aggregate_diff,
        "strongest_improvement": strongest_improvement,
        "worst_regression": worst_regression,
    }

    scenario_diff = {
        "rows": scenario_diff_rows,
    }

    gate = str(gate_outcome.get("gate", "FAIL"))

    classification_json = {
        "overall_classification": classification,
        "certification_decision": certification_decision,
        "gate": gate,
        "gate_reason": str(gate_outcome.get("reason", "")),
        "recommended_next_action": str(gate_outcome.get("recommended_next_action", "")),
        "compatibility_state": compatibility_result.state,
        "compatibility_errors": compatibility_result.errors,
        "compatibility_warnings": compatibility_result.warnings,
        "compatibility_artifacts": compatibility_result.artifacts,
        "reasons": class_reasons,
        "validation_errors": validation_errors,
    }

    report_lines = [
        "# Certification Comparison Report",
        "",
        f"- Overall classification: {classification}",
        f"- Certification decision: {certification_decision}",
        f"- Gate: {gate}",
        f"- Gate reason: {gate_outcome.get('reason', '')}",
        f"- Recommended next action: {gate_outcome.get('recommended_next_action', '')}",
        f"- Compatibility state: {compatibility_result.state}",
        f"- Baseline: {baseline_bundle.root}",
        f"- Current: {current_bundle.root}",
        f"- Strongest improvement: {strongest_improvement.get('metric', 'none')} ({strongest_improvement.get('delta', 0.0)})",
        f"- Worst regression: {worst_regression.get('metric', 'none')} ({worst_regression.get('delta', 0.0)})",
        "",
        "## Aggregate Metric Diff",
        "",
        "metric | baseline | current | delta",
        "--- | --- | --- | ---",
    ]
    for row in metric_rows:
        report_lines.append(f"{row['metric']} | {row['baseline']} | {row['current']} | {row['delta']}")

    report_lines.extend(
        [
            "",
            "## Scenario Diff Matrix",
            "",
            "scenario_id | expected_gate | baseline_actual_gate | current_actual_gate | baseline_diagnostic_score | current_diagnostic_score | delta_diagnostic_score | baseline_root_cause_accuracy | current_root_cause_accuracy | delta_root_cause_accuracy | baseline_ownership_accuracy | current_ownership_accuracy | delta_ownership_accuracy",
            "--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---",
        ]
    )
    for row in scenario_diff_rows:
        if row.get("status") == "missing":
            report_lines.append(
                f"{row['scenario_id']} | missing | missing | missing | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0"
            )
            continue
        report_lines.append(
            " | ".join(
                [
                    str(row.get("scenario_id", "")),
                    str(row.get("expected_gate", "")),
                    str(row.get("baseline_actual_gate", "")),
                    str(row.get("current_actual_gate", "")),
                    str(row.get("baseline_diagnostic_score", "")),
                    str(row.get("current_diagnostic_score", "")),
                    str(row.get("delta_diagnostic_score", "")),
                    str(row.get("baseline_root_cause_accuracy", "")),
                    str(row.get("current_root_cause_accuracy", "")),
                    str(row.get("delta_root_cause_accuracy", "")),
                    str(row.get("baseline_ownership_accuracy", "")),
                    str(row.get("current_ownership_accuracy", "")),
                    str(row.get("delta_ownership_accuracy", "")),
                ]
            )
        )

    report_lines.extend(["", "## Notes", ""])
    if validation_errors:
        report_lines.append("Validation errors:")
        for err in validation_errors:
            report_lines.append(f"- {err}")
    if compatibility_result.warnings:
        report_lines.append("")
        report_lines.append("Compatibility warnings:")
        for warning in compatibility_result.warnings:
            report_lines.append(f"- {warning}")

    _write_json(pf / "00_run_manifest.json", run_manifest)
    _write_json(pf / "01_inputs.json", inputs_json)
    _write_json(pf / "02_baseline_load.json", baseline_load)
    _write_json(pf / "03_current_run_load.json", current_load)
    _write_json(pf / "04_metric_diff.json", metric_diff)
    _write_json(pf / "05_scenario_diff.json", scenario_diff)
    _write_json(pf / "06_classification.json", classification_json)
    _write_text(pf / "07_certification_report.md", "\n".join(report_lines) + "\n")
    _write_json(
        pf / "08_component_report.json",
        {
            "component": "ngksdevfabric_certify_compare",
            "status": gate,
            "classification": classification,
            "certification_decision": certification_decision,
            "compatibility_state": compatibility_result.state,
            "gate": gate,
            "gate_reason": str(gate_outcome.get("reason", "")),
            "recommended_next_action": str(gate_outcome.get("recommended_next_action", "")),
            "strongest_improvement": strongest_improvement,
            "worst_regression": worst_regression,
            "timestamp": _iso_now(),
        },
    )
    _write_json(pf / "09_decision_policy.json", decision_policy.to_dict())
    _write_json(pf / "10_decision_evaluation.json", decision_eval)
    _write_json(pf / "11_regression_hotspots.json", {"hotspots": hotspots})
    _write_text(
        pf / "12_certification_decision.md",
        "\n".join(
            [
                "# Certification Decision",
                "",
                f"- decision: {certification_decision}",
                f"- overall_classification: {classification}",
                f"- gate: {gate}",
                f"- gate_reason: {gate_outcome.get('reason', '')}",
                f"- recommended_next_action: {gate_outcome.get('recommended_next_action', '')}",
                f"- compatibility_state: {compatibility_result.state}",
                f"- strongest_improvement: {strongest_improvement.get('metric', 'none')} ({strongest_improvement.get('delta', 0.0)})",
                f"- worst_regression: {worst_regression.get('metric', 'none')} ({worst_regression.get('delta', 0.0)})",
                f"- hotspot_count: {len(hotspots)}",
                "",
                "## Decision Reasons",
                *[f"- {r}" for r in decision_eval.get("reasons", [])],
                "",
                "## Top Hotspots",
                *[
                    f"- {item.get('scenario_id', '')}: severity={item.get('severity', '')}, delta_diagnostic_score={item.get('delta_diagnostic_score', 0.0)}"
                    for item in hotspots[:5]
                ],
                "",
            ]
        ),
    )
    _write_text(
        pf / "18_summary.md",
        "\n".join(
            [
                "# Certification Compare Summary",
                "",
                f"- overall_classification: {classification}",
                f"- certification_decision: {certification_decision}",
                f"- compatibility_state: {compatibility_result.state}",
                f"- gate_reason: {gate_outcome.get('reason', '')}",
                f"- strongest_improvement: {strongest_improvement.get('metric', 'none')} ({strongest_improvement.get('delta', 0.0)})",
                f"- worst_regression: {worst_regression.get('metric', 'none')} ({worst_regression.get('delta', 0.0)})",
                f"- Final gate: {gate}",
                "",
            ]
        ),
    )

    zip_path = pf.with_suffix(".zip")
    _zip_dir(pf, zip_path)

    return {
        "classification": classification,
        "certification_decision": certification_decision,
        "strongest_improvement": strongest_improvement,
        "worst_regression": worst_regression,
        "top_hotspot_scenario": hotspots[0]["scenario_id"] if hotspots else "none",
        "gate": gate,
        "gate_reason": str(gate_outcome.get("reason", "")),
        "recommended_next_action": str(gate_outcome.get("recommended_next_action", "")),
        "compatibility_state": compatibility_result.state,
        "compatibility_errors": compatibility_result.errors,
        "compatibility_warnings": compatibility_result.warnings,
        "compatibility_artifacts": compatibility_result.artifacts,
        "pf": str(pf.resolve()),
        "zip": str(zip_path.resolve()),
        "validation_errors": validation_errors,
    }
