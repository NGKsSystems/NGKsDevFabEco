from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResolutionRefinementModel:
    low_resolution_penalty_weight: float = 0.10
    unresolved_density_penalty_weight: float = 0.10
    recurrence_resolution_penalty_weight: float = 0.07
    persisting_penalty_weight: float = 0.08
    high_resolution_credit_weight: float = 0.06
    quick_resolution_credit_weight: float = 0.04
    max_negative_adjustment: float = -0.12
    max_positive_adjustment: float = 0.20
    mean_time_to_resolution_scale: float = 5.0


_REFINEMENT_MODEL = ResolutionRefinementModel()


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


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _collect_persisting_by_component(lifecycle_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in lifecycle_rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("state", "")).upper() != "PERSISTING":
            continue
        component = str(row.get("component", "")).strip() or "unknown_component"
        counts[component] = counts.get(component, 0) + 1
    return counts


def apply_resolution_refinement(
    *,
    pf: Path,
    resolution_root: Path | None,
    touched_components: list[str],
    component_rows: list[dict[str, Any]],
    base_overall_risk_score: float,
) -> dict[str, Any]:
    predictive_dir = pf / "predictive"

    metrics_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    resolved_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    if resolution_root is not None:
        metrics_store = _read_json(resolution_root / "71_component_resolution_metrics.json")
        lifecycle_store = _read_json(resolution_root / "70_regression_lifecycle_states.json")
        resolved_store = _read_json(resolution_root / "72_resolved_regressions.json")
        unresolved_store = _read_json(resolution_root / "73_unresolved_regressions.json")

        metrics_rows = metrics_store.get("rows", []) if isinstance(metrics_store.get("rows", []), list) else []
        lifecycle_rows = lifecycle_store.get("rows", []) if isinstance(lifecycle_store.get("rows", []), list) else []
        resolved_rows = resolved_store.get("rows", []) if isinstance(resolved_store.get("rows", []), list) else []
        unresolved_rows = unresolved_store.get("rows", []) if isinstance(unresolved_store.get("rows", []), list) else []

    metrics_by_component = {
        str(row.get("component", "")).strip(): row
        for row in metrics_rows
        if isinstance(row, dict) and str(row.get("component", "")).strip()
    }
    persisting_by_component = _collect_persisting_by_component([row for row in lifecycle_rows if isinstance(row, dict)])

    component_base_scores = {
        str(row.get("component", "")).strip(): _safe_float(row.get("risk_score", 0.0))
        for row in component_rows
        if isinstance(row, dict)
    }

    adjustments: list[dict[str, Any]] = []
    refined_component_scores: dict[str, float] = {}

    for component in sorted({*touched_components, *component_base_scores.keys()}):
        if not component:
            continue
        base_score = _safe_float(component_base_scores.get(component, 0.0))
        metrics = metrics_by_component.get(component, {}) if isinstance(metrics_by_component.get(component, {}), dict) else {}

        resolution_rate = _clamp(_safe_float(metrics.get("resolution_rate", 0.0)), 0.0, 1.0)
        mean_time_to_resolution = max(0.0, _safe_float(metrics.get("mean_time_to_resolution", 0.0)))
        recurrence_rate = _clamp(_safe_float(metrics.get("recurrence_rate", 0.0)), 0.0, 1.0)

        resolved_count = max(0, _safe_int(metrics.get("resolved_regressions", 0)))
        unresolved_count = max(0, _safe_int(metrics.get("unresolved_regressions", 0)))
        unresolved_density = _clamp(unresolved_count / max(1, resolved_count + unresolved_count), 0.0, 1.0)

        mttr_norm = _clamp(mean_time_to_resolution / max(0.01, _REFINEMENT_MODEL.mean_time_to_resolution_scale), 0.0, 1.0)
        quick_resolution_factor = _clamp(1.0 - mttr_norm, 0.0, 1.0)
        recurrence_vs_resolution_ratio = _clamp(recurrence_rate / max(0.05, resolution_rate), 0.0, 4.0)
        recurrence_vs_resolution_norm = _clamp(recurrence_vs_resolution_ratio / 4.0, 0.0, 1.0)

        persisting_count = max(0, _safe_int(persisting_by_component.get(component, 0)))
        persisting_penalty = _REFINEMENT_MODEL.persisting_penalty_weight if persisting_count > 0 else 0.0

        low_resolution_penalty = _REFINEMENT_MODEL.low_resolution_penalty_weight * _clamp(1.0 - resolution_rate, 0.0, 1.0)
        unresolved_density_penalty = _REFINEMENT_MODEL.unresolved_density_penalty_weight * unresolved_density
        recurrence_resolution_penalty = _REFINEMENT_MODEL.recurrence_resolution_penalty_weight * recurrence_vs_resolution_norm

        high_resolution_credit = _REFINEMENT_MODEL.high_resolution_credit_weight * resolution_rate
        quick_resolution_credit = _REFINEMENT_MODEL.quick_resolution_credit_weight * quick_resolution_factor

        raw_adjustment = (
            low_resolution_penalty
            + unresolved_density_penalty
            + recurrence_resolution_penalty
            + persisting_penalty
            - high_resolution_credit
            - quick_resolution_credit
        )
        adjustment = _clamp(
            raw_adjustment,
            _REFINEMENT_MODEL.max_negative_adjustment,
            _REFINEMENT_MODEL.max_positive_adjustment,
        )

        refined_score = _clamp(base_score + adjustment, 0.0, 1.0)
        refined_component_scores[component] = refined_score

        adjustments.append(
            {
                "component": component,
                "base_risk_score": round(base_score, 4),
                "adjustment": round(adjustment, 4),
                "refined_risk_score": round(refined_score, 4),
                "signals": {
                    "resolution_rate": round(resolution_rate, 4),
                    "mean_time_to_resolution": round(mean_time_to_resolution, 4),
                    "recurrence_rate": round(recurrence_rate, 4),
                    "recurrence_vs_resolution_ratio": round(recurrence_vs_resolution_ratio, 4),
                    "unresolved_density": round(unresolved_density, 4),
                    "persisting_regression_count": persisting_count,
                },
                "components": {
                    "low_resolution_penalty": round(low_resolution_penalty, 4),
                    "unresolved_density_penalty": round(unresolved_density_penalty, 4),
                    "recurrence_resolution_penalty": round(recurrence_resolution_penalty, 4),
                    "persisting_penalty": round(persisting_penalty, 4),
                    "high_resolution_credit": round(high_resolution_credit, 4),
                    "quick_resolution_credit": round(quick_resolution_credit, 4),
                },
            }
        )

    touched_refined = [refined_component_scores.get(component, 0.0) for component in touched_components if component in refined_component_scores]
    if not touched_refined:
        touched_refined = [base_overall_risk_score]

    resolution_adjusted_risk_score = _clamp(sum(touched_refined) / max(1, len(touched_refined)), 0.0, 1.0)
    resolution_adjusted_risk_class = _risk_class(resolution_adjusted_risk_score)

    historical_fix_success_rate = _clamp(
        sum(_clamp(_safe_float(metrics_by_component.get(component, {}).get("resolution_rate", 0.0)), 0.0, 1.0) for component in touched_components)
        / max(1, len(touched_components)),
        0.0,
        1.0,
    )

    persistent_regression_warning = any(_safe_int(persisting_by_component.get(component, 0)) > 0 for component in touched_components)

    context = {
        "resolution_root": str(resolution_root) if resolution_root is not None else "",
        "metrics_row_count": len(metrics_rows),
        "lifecycle_row_count": len(lifecycle_rows),
        "resolved_row_count": len(resolved_rows),
        "unresolved_row_count": len(unresolved_rows),
    }

    _write_json(
        predictive_dir / "66_resolution_adjusted_risk.json",
        {
            "base_overall_risk_score": round(_clamp(base_overall_risk_score, 0.0, 1.0), 4),
            "resolution_adjusted_risk_score": round(resolution_adjusted_risk_score, 4),
            "resolution_adjusted_risk_class": resolution_adjusted_risk_class,
            "historical_fix_success_rate": round(historical_fix_success_rate, 4),
            "persistent_regression_warning": persistent_regression_warning,
        },
    )
    _write_json(
        predictive_dir / "67_resolution_context.json",
        {
            "context": context,
            "resolution_refinement_model": {
                "low_resolution_penalty_weight": _REFINEMENT_MODEL.low_resolution_penalty_weight,
                "unresolved_density_penalty_weight": _REFINEMENT_MODEL.unresolved_density_penalty_weight,
                "recurrence_resolution_penalty_weight": _REFINEMENT_MODEL.recurrence_resolution_penalty_weight,
                "persisting_penalty_weight": _REFINEMENT_MODEL.persisting_penalty_weight,
                "high_resolution_credit_weight": _REFINEMENT_MODEL.high_resolution_credit_weight,
                "quick_resolution_credit_weight": _REFINEMENT_MODEL.quick_resolution_credit_weight,
                "max_negative_adjustment": _REFINEMENT_MODEL.max_negative_adjustment,
                "max_positive_adjustment": _REFINEMENT_MODEL.max_positive_adjustment,
                "mean_time_to_resolution_scale": _REFINEMENT_MODEL.mean_time_to_resolution_scale,
            },
        },
    )
    _write_json(
        predictive_dir / "68_resolution_risk_adjustments.json",
        {
            "rows": sorted(adjustments, key=lambda row: (-_safe_float(row.get("refined_risk_score", 0.0)), str(row.get("component", "")))),
        },
    )

    lines = [
        "# Predictive Resolution Refinement Summary",
        "",
        f"- base_overall_risk_score: {round(_clamp(base_overall_risk_score, 0.0, 1.0), 4)}",
        f"- resolution_adjusted_risk_score: {round(resolution_adjusted_risk_score, 4)}",
        f"- resolution_adjusted_risk_class: {resolution_adjusted_risk_class}",
        f"- historical_fix_success_rate: {round(historical_fix_success_rate, 4)}",
        f"- persistent_regression_warning: {str(persistent_regression_warning).lower()}",
        "",
        "## Resolution Adjustments",
    ]
    if adjustments:
        for row in sorted(adjustments, key=lambda item: (-_safe_float(item.get("adjustment", 0.0)), str(item.get("component", "")))):
            lines.append(
                f"- component={row.get('component', '')} base={row.get('base_risk_score', 0.0)} adjustment={row.get('adjustment', 0.0)} refined={row.get('refined_risk_score', 0.0)}"
            )
    else:
        lines.append("- no resolution metrics available; refinement defaults to base score")

    _write_text(predictive_dir / "69_predictive_refinement_summary.md", "\n".join(lines) + "\n")

    return {
        "resolution_adjusted_risk_score": round(resolution_adjusted_risk_score, 4),
        "resolution_adjusted_risk_class": resolution_adjusted_risk_class,
        "resolution_context": context,
        "historical_fix_success_rate": round(historical_fix_success_rate, 4),
        "persistent_regression_warning": persistent_regression_warning,
        "component_adjustments": adjustments,
        "artifacts": [
            "predictive/66_resolution_adjusted_risk.json",
            "predictive/67_resolution_context.json",
            "predictive/68_resolution_risk_adjustments.json",
            "predictive/69_predictive_refinement_summary.md",
        ],
    }
