from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .predictive_resolution_refinement import apply_resolution_refinement

_SEVERITY_WEIGHTS: dict[str, float] = {
    "TRACE": 0.10,
    "LOW": 0.30,
    "MEDIUM": 0.60,
    "HIGH": 1.00,
}


@dataclass(frozen=True)
class PredictionRiskModel:
    health_penalty_weight: float = 0.30
    recent_density_weight: float = 0.20
    recurring_frequency_weight: float = 0.20
    recurrence_history_weight: float = 0.15
    severity_weight: float = 0.15
    overall_max_weight: float = 0.60
    overall_avg_weight: float = 0.40


_RISK_MODEL = PredictionRiskModel()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _risk_class(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.50:
        return "HIGH"
    if score >= 0.25:
        return "MEDIUM"
    return "LOW"


def _resolve_change_manifest(project_root: Path, manifest_path: Path | None) -> dict[str, Any]:
    if manifest_path is None:
        return {}
    candidate = manifest_path.resolve() if manifest_path.is_absolute() else (project_root / manifest_path).resolve()
    loaded = _read_json(candidate)
    return loaded if loaded else {}


def _select_trend_root(project_root: Path, explicit_trend_root: Path | None) -> Path | None:
    if explicit_trend_root is not None:
        root = explicit_trend_root.resolve() if explicit_trend_root.is_absolute() else (project_root / explicit_trend_root).resolve()
        return root

    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None

    candidates: list[Path] = []
    for child in runs_root.iterdir():
        history_dir = child / "history"
        if not history_dir.is_dir():
            continue
        expected = [
            history_dir / "50_component_health_scores.json",
            history_dir / "51_component_regression_ranking.json",
            history_dir / "52_regression_trend_analysis.json",
            history_dir / "53_recurring_regression_patterns.json",
        ]
        if all(path.is_file() for path in expected):
            candidates.append(history_dir)

    if not candidates:
        return None

    return sorted(candidates, key=lambda p: p.parent.name)[-1]


def _select_resolution_root(project_root: Path, trend_root: Path | None) -> Path | None:
    if trend_root is not None:
        paired = (trend_root.parent / "resolution").resolve()
        required = [
            paired / "70_regression_lifecycle_states.json",
            paired / "71_component_resolution_metrics.json",
            paired / "72_resolved_regressions.json",
            paired / "73_unresolved_regressions.json",
        ]
        if paired.is_dir() and all(path.is_file() for path in required):
            return paired

    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None

    candidates: list[Path] = []
    for child in runs_root.iterdir():
        resolution_dir = child / "resolution"
        if not resolution_dir.is_dir():
            continue
        required = [
            resolution_dir / "70_regression_lifecycle_states.json",
            resolution_dir / "71_component_resolution_metrics.json",
            resolution_dir / "72_resolved_regressions.json",
            resolution_dir / "73_unresolved_regressions.json",
        ]
        if all(path.is_file() for path in required):
            candidates.append(resolution_dir)

    if not candidates:
        return None

    return sorted(candidates, key=lambda p: p.parent.name)[-1]


def _load_inputs(history_root: Path, trend_root: Path | None) -> dict[str, Any]:
    regression_store = _read_json(history_root / "regressions" / "regression_fingerprints.json")
    component_store = _read_json(history_root / "components" / "component_regression_stats.json")

    loaded: dict[str, Any] = {
        "fingerprint_rows": regression_store.get("rows", []) if isinstance(regression_store.get("rows", []), list) else [],
        "component_stats": component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {},
        "health_rows": [],
        "trend_payload": {},
        "recurring_rows": [],
        "run_count": 0,
    }

    runs_dir = history_root / "runs"
    if runs_dir.is_dir():
        loaded["run_count"] = len([path for path in runs_dir.glob("run_*.json") if path.is_file()])

    if trend_root is None:
        return loaded

    health_store = _read_json(trend_root / "50_component_health_scores.json")
    trend_store = _read_json(trend_root / "52_regression_trend_analysis.json")
    recurring_store = _read_json(trend_root / "53_recurring_regression_patterns.json")

    loaded["health_rows"] = health_store.get("rows", []) if isinstance(health_store.get("rows", []), list) else []
    loaded["trend_payload"] = trend_store
    loaded["recurring_rows"] = recurring_store.get("rows", []) if isinstance(recurring_store.get("rows", []), list) else []
    loaded["run_count"] = max(loaded["run_count"], _safe_int(trend_store.get("run_count", loaded["run_count"])))

    return loaded


def analyze_premerge_regression_risk(
    *,
    project_root: Path,
    pf: Path,
    change_manifest_path: Path | None = None,
    touched_components: list[str] | None = None,
    trend_root: Path | None = None,
) -> dict[str, Any]:
    history_root = (project_root / "devfabeco_history").resolve()
    if not history_root.is_dir():
        raise ValueError(f"history_root_missing:{history_root}")

    manifest = _resolve_change_manifest(project_root, change_manifest_path)
    manifest_components = manifest.get("touched_components", []) if isinstance(manifest.get("touched_components", []), list) else []
    explicit_components = touched_components or []

    normalized_components = sorted(
        {
            str(name).strip()
            for name in [*manifest_components, *explicit_components]
            if str(name).strip()
        }
    )
    if not normalized_components:
        raise ValueError("touched_components_required: provide --change-manifest or --component")

    selected_trend_root = _select_trend_root(project_root, trend_root)
    selected_resolution_root = _select_resolution_root(project_root, selected_trend_root)
    loaded = _load_inputs(history_root, selected_trend_root)

    health_rows = loaded.get("health_rows", []) if isinstance(loaded.get("health_rows", []), list) else []
    health_by_component = {
        str(row.get("component", "")): row
        for row in health_rows
        if isinstance(row, dict) and str(row.get("component", "")).strip()
    }

    fingerprint_rows = loaded.get("fingerprint_rows", []) if isinstance(loaded.get("fingerprint_rows", []), list) else []
    component_stats = loaded.get("component_stats", {}) if isinstance(loaded.get("component_stats", {}), dict) else {}
    recurring_rows = loaded.get("recurring_rows", []) if isinstance(loaded.get("recurring_rows", []), list) else []
    run_count = max(1, _safe_int(loaded.get("run_count", 0)))

    recurring_by_component: dict[str, list[dict[str, Any]]] = {}
    for row in recurring_rows:
        if not isinstance(row, dict):
            continue
        component = str(row.get("component", "")).strip()
        if not component:
            continue
        recurring_by_component.setdefault(component, []).append(row)

    fingerprints_by_component: dict[str, list[dict[str, Any]]] = {}
    for row in fingerprint_rows:
        if not isinstance(row, dict):
            continue
        component = str(row.get("component", "")).strip()
        if not component:
            continue
        fingerprints_by_component.setdefault(component, []).append(row)

    all_occurrences = [_safe_int(row.get("occurrences", 0)) for row in fingerprint_rows if isinstance(row, dict)]
    max_occurrence = max(1, max(all_occurrences) if all_occurrences else 1)

    component_rows: list[dict[str, Any]] = []
    metric_scores: dict[str, float] = {}
    scenario_scores: dict[str, float] = {}

    for component in normalized_components:
        health = health_by_component.get(component, {}) if isinstance(health_by_component.get(component, {}), dict) else {}
        stats = component_stats.get(component, {}) if isinstance(component_stats.get(component, {}), dict) else {}
        fp_rows = fingerprints_by_component.get(component, [])
        recurring = recurring_by_component.get(component, [])

        health_score = _safe_float(health.get("health_score", 1.0))
        health_penalty = _clamp(1.0 - health_score, 0.0, 1.0)

        recent_regressions = _safe_int(health.get("recent_regressions", 0))
        recent_density = _clamp(recent_regressions / max(1, min(5, run_count)), 0.0, 1.0)

        recurring_total = sum(_safe_int(row.get("occurrences", 0)) for row in recurring)
        recurring_frequency = _clamp(recurring_total / max_occurrence, 0.0, 1.0)

        total_occurrences = _safe_int(stats.get("total_regression_occurrences", 0))
        unique_fingerprints = _safe_int(stats.get("unique_fingerprints", 0))
        recurrence_history = _clamp(total_occurrences / max(1, run_count), 0.0, 1.0)
        if unique_fingerprints > 0 and total_occurrences > 0:
            recurrence_history = _clamp(recurrence_history * _clamp(unique_fingerprints / total_occurrences, 0.0, 1.0), 0.0, 1.0)

        severity_weighted = 0.0
        severity_occurrences = 0
        for row in fp_rows:
            occurrences = _safe_int(row.get("occurrences", 0))
            sev = str(row.get("severity_bucket", "TRACE")).upper()
            severity_weighted += _SEVERITY_WEIGHTS.get(sev, _SEVERITY_WEIGHTS["TRACE"]) * occurrences
            severity_occurrences += occurrences

            metric = str(row.get("metric", "")).strip()
            scenario_id = str(row.get("scenario_id", "")).strip()
            weight = _SEVERITY_WEIGHTS.get(sev, _SEVERITY_WEIGHTS["TRACE"]) * max(1, occurrences)
            if metric:
                metric_scores[metric] = metric_scores.get(metric, 0.0) + weight
            if scenario_id:
                scenario_scores[scenario_id] = scenario_scores.get(scenario_id, 0.0) + weight

        severity_factor = _clamp(severity_weighted / max(1, severity_occurrences), 0.0, 1.0)

        risk_score = _clamp(
            _RISK_MODEL.health_penalty_weight * health_penalty
            + _RISK_MODEL.recent_density_weight * recent_density
            + _RISK_MODEL.recurring_frequency_weight * recurring_frequency
            + _RISK_MODEL.recurrence_history_weight * recurrence_history
            + _RISK_MODEL.severity_weight * severity_factor,
            0.0,
            1.0,
        )

        component_rows.append(
            {
                "component": component,
                "risk_score": round(risk_score, 4),
                "risk_class": _risk_class(risk_score),
                "signals": {
                    "health_score": round(health_score, 4),
                    "health_penalty": round(health_penalty, 4),
                    "recent_regressions": recent_regressions,
                    "recent_density": round(recent_density, 4),
                    "recurring_frequency": round(recurring_frequency, 4),
                    "component_recurrence_history": round(recurrence_history, 4),
                    "severity_factor": round(severity_factor, 4),
                },
                "evidence": {
                    "total_regression_occurrences": total_occurrences,
                    "unique_fingerprints": unique_fingerprints,
                    "recurring_pattern_rows": len(recurring),
                    "fingerprint_rows": len(fp_rows),
                },
            }
        )

    component_rows = sorted(component_rows, key=lambda row: (-_safe_float(row.get("risk_score", 0.0)), str(row.get("component", ""))))

    max_component_score = _safe_float(component_rows[0].get("risk_score", 0.0)) if component_rows else 0.0
    avg_component_score = sum(_safe_float(row.get("risk_score", 0.0)) for row in component_rows) / max(1, len(component_rows))
    overall_risk_score = _clamp(
        (_RISK_MODEL.overall_max_weight * max_component_score) + (_RISK_MODEL.overall_avg_weight * avg_component_score),
        0.0,
        1.0,
    )
    overall_risk_class = _risk_class(overall_risk_score)

    likely_metrics = [
        {"metric": metric, "risk_signal": round(score, 4)}
        for metric, score in sorted(metric_scores.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    recommended_scenarios = [
        {"scenario_id": sid, "priority_signal": round(score, 4)}
        for sid, score in sorted(scenario_scores.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    recurrence_evidence = []
    for row in sorted(
        [r for r in recurring_rows if isinstance(r, dict) and str(r.get("component", "")) in normalized_components],
        key=lambda item: (-_safe_int(item.get("occurrences", 0)), str(item.get("component", "")), str(item.get("fingerprint", ""))),
    )[:20]:
        recurrence_evidence.append(
            {
                "component": str(row.get("component", "")),
                "fingerprint": str(row.get("fingerprint", "")),
                "metric": str(row.get("metric", "")),
                "scenario_id": str(row.get("scenario_id", "")),
                "occurrences": _safe_int(row.get("occurrences", 0)),
                "severity_bucket": str(row.get("severity_bucket", "")),
                "last_seen_run": str(row.get("last_seen_run", "")),
            }
        )

    highest_risk_component = component_rows[0].get("component", "") if component_rows else ""

    explanation_lines = [
        f"change_id={str(manifest.get('change_id', 'manual_input') or 'manual_input')}",
        f"overall_risk_score={round(overall_risk_score, 4)}",
        f"overall_risk_class={overall_risk_class}",
        f"highest_risk_component={highest_risk_component}",
        "risk_model_weights="
        + ",".join(
            [
                f"health_penalty:{_RISK_MODEL.health_penalty_weight}",
                f"recent_density:{_RISK_MODEL.recent_density_weight}",
                f"recurring_frequency:{_RISK_MODEL.recurring_frequency_weight}",
                f"recurrence_history:{_RISK_MODEL.recurrence_history_weight}",
                f"severity:{_RISK_MODEL.severity_weight}",
            ]
        ),
    ]

    prediction_payload = {
        "change_id": str(manifest.get("change_id", "manual_input") or "manual_input"),
        "project_name": str(manifest.get("project_name", project_root.name) or project_root.name),
        "overall_risk_score": round(overall_risk_score, 4),
        "overall_risk_class": overall_risk_class,
        "highest_risk_component": highest_risk_component,
        "likely_metrics_at_risk": [row["metric"] for row in likely_metrics],
        "recommended_validation_scenarios": [row["scenario_id"] for row in recommended_scenarios],
        "touched_components": normalized_components,
        "touched_files": manifest.get("touched_files", []) if isinstance(manifest.get("touched_files", []), list) else [],
        "recurrence_evidence_count": len(recurrence_evidence),
        "explanation_summary": "; ".join(explanation_lines),
    }

    refinement_payload = apply_resolution_refinement(
        pf=pf,
        resolution_root=selected_resolution_root,
        touched_components=normalized_components,
        component_rows=component_rows,
        base_overall_risk_score=overall_risk_score,
    )

    prediction_payload["resolution_adjusted_risk_score"] = refinement_payload.get("resolution_adjusted_risk_score", round(overall_risk_score, 4))
    prediction_payload["resolution_context"] = refinement_payload.get("resolution_context", {})
    prediction_payload["historical_fix_success_rate"] = refinement_payload.get("historical_fix_success_rate", 0.0)
    prediction_payload["persistent_regression_warning"] = refinement_payload.get("persistent_regression_warning", False)

    predictive_dir = pf / "predictive"
    _write_json(
        predictive_dir / "60_prediction_inputs.json",
        {
            "history_root": str(history_root),
            "trend_root": str(selected_trend_root) if selected_trend_root is not None else "",
            "resolution_root": str(selected_resolution_root) if selected_resolution_root is not None else "",
            "change_manifest": manifest,
            "touched_components": normalized_components,
            "risk_model": {
                "health_penalty_weight": _RISK_MODEL.health_penalty_weight,
                "recent_density_weight": _RISK_MODEL.recent_density_weight,
                "recurring_frequency_weight": _RISK_MODEL.recurring_frequency_weight,
                "recurrence_history_weight": _RISK_MODEL.recurrence_history_weight,
                "severity_weight": _RISK_MODEL.severity_weight,
                "overall_max_weight": _RISK_MODEL.overall_max_weight,
                "overall_avg_weight": _RISK_MODEL.overall_avg_weight,
                "risk_class_thresholds": {
                    "LOW": [0.00, 0.24],
                    "MEDIUM": [0.25, 0.49],
                    "HIGH": [0.50, 0.74],
                    "CRITICAL": [0.75, 1.00],
                },
            },
        },
    )
    _write_json(predictive_dir / "61_component_risk_scores.json", {"rows": component_rows})
    _write_json(predictive_dir / "62_metric_risk_predictions.json", {"rows": likely_metrics})
    _write_json(predictive_dir / "63_recommended_validation_targets.json", {"rows": recommended_scenarios})
    _write_json(
        predictive_dir / "64_prediction_classification.json",
        {
            "prediction": prediction_payload,
            "recurrence_evidence": recurrence_evidence,
        },
    )

    summary_lines = [
        "# Pre-Merge Regression Risk Prediction Summary",
        "",
        f"- change_id: {prediction_payload['change_id']}",
        f"- project_name: {prediction_payload['project_name']}",
        f"- overall_risk_score: {prediction_payload['overall_risk_score']}",
        f"- resolution_adjusted_risk_score: {prediction_payload['resolution_adjusted_risk_score']}",
        f"- overall_risk_class: {prediction_payload['overall_risk_class']}",
        f"- highest_risk_component: {prediction_payload['highest_risk_component']}",
        f"- historical_fix_success_rate: {prediction_payload['historical_fix_success_rate']}",
        f"- persistent_regression_warning: {str(bool(prediction_payload['persistent_regression_warning'])).lower()}",
        "",
        "## Likely Metrics At Risk",
    ]
    if likely_metrics:
        for row in likely_metrics:
            summary_lines.append(f"- {row['metric']} signal={row['risk_signal']}")
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Recommended Validation Scenarios"])
    if recommended_scenarios:
        for row in recommended_scenarios:
            summary_lines.append(f"- {row['scenario_id']} signal={row['priority_signal']}")
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Recurrence Evidence"])
    if recurrence_evidence:
        for row in recurrence_evidence[:10]:
            summary_lines.append(
                f"- component={row['component']} fingerprint={row['fingerprint']} occurrences={row['occurrences']} metric={row['metric']} scenario={row['scenario_id']}"
            )
    else:
        summary_lines.append("- none")

    _write_text(predictive_dir / "65_prediction_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "prediction": prediction_payload,
        "component_rows": component_rows,
        "metric_rows": likely_metrics,
        "scenario_rows": recommended_scenarios,
        "recurrence_evidence": recurrence_evidence,
        "history_root": str(history_root),
        "trend_root": str(selected_trend_root) if selected_trend_root is not None else "",
        "resolution_root": str(selected_resolution_root) if selected_resolution_root is not None else "",
        "resolution_refinement": refinement_payload,
        "artifacts": [
            "predictive/60_prediction_inputs.json",
            "predictive/61_component_risk_scores.json",
            "predictive/62_metric_risk_predictions.json",
            "predictive/63_recommended_validation_targets.json",
            "predictive/64_prediction_classification.json",
            "predictive/65_prediction_summary.md",
            "predictive/66_resolution_adjusted_risk.json",
            "predictive/67_resolution_context.json",
            "predictive/68_resolution_risk_adjustments.json",
            "predictive/69_predictive_refinement_summary.md",
        ],
    }
