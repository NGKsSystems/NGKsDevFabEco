from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PLAN_THRESHOLDS = {
    "MINIMAL_MAX": 0.20,
    "STANDARD_MAX": 0.45,
    "HEIGHTENED_MAX": 0.70,
    "REQUIRED_SCORE": 0.65,
}

_WATCH_PRESSURE = {
    "NORMAL": 0.00,
    "WATCH": 0.20,
    "HOT": 0.45,
    "CRITICAL": 0.70,
}

_RISK_CLASS_PRESSURE = {
    "LOW": 0.10,
    "MEDIUM": 0.35,
    "HIGH": 0.65,
    "CRITICAL": 0.90,
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ensure_history_root(history_root: Path) -> None:
    history_root.mkdir(parents=True, exist_ok=True)
    regressions_dir = history_root / "regressions"
    components_dir = history_root / "components"
    runs_dir = history_root / "runs"
    regressions_dir.mkdir(parents=True, exist_ok=True)
    components_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    regression_store = regressions_dir / "regression_fingerprints.json"
    if not regression_store.is_file():
        _write_json(regression_store, {"rows": []})

    component_store = components_dir / "component_regression_stats.json"
    if not component_store.is_file():
        _write_json(component_store, {"components": {}})


def _bootstrap_intelligence_artifacts(*, evidence_root: Path, touched_components: list[str]) -> None:
    intelligence_dir = evidence_root / "intelligence"
    resolution_dir = evidence_root / "resolution"
    history_dir = evidence_root / "history"

    normalized = sorted({str(name).strip() for name in touched_components if str(name).strip()})
    watch_rows = [
        {
            "component": component,
            "watch_class": "NORMAL",
            "watch_score": 0.0,
            "reason": "bootstrap_missing_intelligence",
        }
        for component in normalized
    ]
    scenario_rows = [
        {
            "scenario_id": f"bootstrap::{component}::baseline_smoke",
            "severity_weighted_score": 0.0,
            "source": "bootstrap_missing_intelligence",
        }
        for component in normalized
    ]

    _write_json(intelligence_dir / "110_component_watchlist.json", {"rows": watch_rows})
    _write_json(intelligence_dir / "111_regression_pattern_memory.json", {"rows": []})
    _write_json(intelligence_dir / "112_scenario_detection_value.json", {"rows": scenario_rows})
    _write_json(intelligence_dir / "113_remediation_effectiveness.json", {"rows": []})

    # Keep planner inputs deterministic when no prior intelligence run exists.
    _write_json(resolution_dir / "71_component_resolution_metrics.json", {"rows": []})
    _write_json(history_dir / "53_recurring_regression_patterns.json", {"rows": []})


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


def _resolve_change_manifest(project_root: Path, change_manifest_path: Path | None) -> dict[str, Any]:
    if change_manifest_path is None:
        return {}
    candidate = change_manifest_path.resolve() if change_manifest_path.is_absolute() else (project_root / change_manifest_path).resolve()
    return _read_json(candidate)


def _select_latest_run_with_intelligence(project_root: Path) -> Path | None:
    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None

    candidates: list[Path] = []
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        required = [
            child / "intelligence" / "110_component_watchlist.json",
            child / "intelligence" / "111_regression_pattern_memory.json",
            child / "intelligence" / "112_scenario_detection_value.json",
            child / "intelligence" / "113_remediation_effectiveness.json",
        ]
        if all(path.is_file() for path in required):
            candidates.append(child.resolve())

    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _select_latest_predictive_run(project_root: Path) -> Path | None:
    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None

    candidates: list[Path] = []
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        required = [
            child / "predictive" / "61_component_risk_scores.json",
            child / "predictive" / "64_prediction_classification.json",
        ]
        if all(path.is_file() for path in required):
            candidates.append(child.resolve())

    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _plan_class(score: float) -> str:
    if score <= _PLAN_THRESHOLDS["MINIMAL_MAX"]:
        return "MINIMAL"
    if score <= _PLAN_THRESHOLDS["STANDARD_MAX"]:
        return "STANDARD"
    if score <= _PLAN_THRESHOLDS["HEIGHTENED_MAX"]:
        return "HEIGHTENED"
    return "CRITICAL"


def _watch_index(watch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("component", "")).strip(): row
        for row in watch_rows
        if isinstance(row, dict) and str(row.get("component", "")).strip()
    }


def _predictive_component_index(predictive_component_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("component", "")).strip(): row
        for row in predictive_component_rows
        if isinstance(row, dict) and str(row.get("component", "")).strip()
    }


def plan_premerge_validation(
    *,
    project_root: Path,
    pf: Path,
    change_manifest_path: Path | None = None,
    touched_components: list[str] | None = None,
    evidence_run_root: Path | None = None,
) -> dict[str, Any]:
    planning_dir = pf / "planning"
    history_root = (project_root / "devfabeco_history").resolve()
    _ensure_history_root(history_root)

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

    selected_evidence_run = evidence_run_root.resolve() if evidence_run_root else _select_latest_run_with_intelligence(project_root)
    if selected_evidence_run is None:
        selected_evidence_run = pf.resolve()
        _bootstrap_intelligence_artifacts(
            evidence_root=selected_evidence_run,
            touched_components=normalized_components,
        )

    selected_predictive_run = _select_latest_predictive_run(project_root)

    watch_payload = _read_json(selected_evidence_run / "intelligence" / "110_component_watchlist.json")
    pattern_payload = _read_json(selected_evidence_run / "intelligence" / "111_regression_pattern_memory.json")
    scenario_payload = _read_json(selected_evidence_run / "intelligence" / "112_scenario_detection_value.json")

    resolution_payload = _read_json(selected_evidence_run / "resolution" / "71_component_resolution_metrics.json")
    recurring_payload = _read_json(selected_evidence_run / "history" / "53_recurring_regression_patterns.json")

    predictive_component_payload = _read_json(selected_predictive_run / "predictive" / "61_component_risk_scores.json") if selected_predictive_run else {}
    predictive_classification_payload = _read_json(selected_predictive_run / "predictive" / "64_prediction_classification.json") if selected_predictive_run else {}

    fingerprint_store = _read_json(history_root / "regressions" / "regression_fingerprints.json")
    component_store = _read_json(history_root / "components" / "component_regression_stats.json")

    watch_rows = [row for row in watch_payload.get("rows", []) if isinstance(row, dict)]
    scenario_rows = [row for row in scenario_payload.get("rows", []) if isinstance(row, dict)]
    resolution_rows = [row for row in resolution_payload.get("rows", []) if isinstance(row, dict)]
    recurring_rows = [row for row in recurring_payload.get("rows", []) if isinstance(row, dict)]
    predictive_component_rows = [row for row in predictive_component_payload.get("rows", []) if isinstance(row, dict)]

    fingerprint_rows = [row for row in fingerprint_store.get("rows", []) if isinstance(row, dict)]
    component_stats = component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {}

    watch_by_component = _watch_index(watch_rows)
    predictive_by_component = _predictive_component_index(predictive_component_rows)
    resolution_by_component = {
        str(row.get("component", "")).strip(): row
        for row in resolution_rows
        if str(row.get("component", "")).strip()
    }

    recurring_count_by_component: dict[str, int] = {}
    for row in recurring_rows:
        component = str(row.get("component", "")).strip()
        if not component:
            continue
        recurring_count_by_component[component] = recurring_count_by_component.get(component, 0) + _safe_int(row.get("occurrences", 0))

    scenario_component_map: dict[str, set[str]] = {}
    for row in fingerprint_rows:
        scenario_id = str(row.get("scenario_id", "")).strip()
        component = str(row.get("component", "")).strip()
        if not scenario_id or not component:
            continue
        scenario_component_map.setdefault(scenario_id, set()).add(component)

    scenario_base_max = max(1.0, max((_safe_float(row.get("severity_weighted_score", 0.0)) for row in scenario_rows), default=1.0))

    plan_rows: list[dict[str, Any]] = []
    for row in scenario_rows:
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            continue

        linked_components = scenario_component_map.get(scenario_id, set())
        touched_linked = sorted([component for component in linked_components if component in normalized_components])
        relevance = 1.0 if touched_linked else 0.25

        scenario_detection_value = _clamp(_safe_float(row.get("severity_weighted_score", 0.0)) / scenario_base_max, 0.0, 1.0)

        watch_pressure = 0.0
        unresolved_pressure = 0.0
        predictive_pressure = 0.0
        recurrence_pressure = 0.0

        components_for_pressure = touched_linked if touched_linked else normalized_components
        for component in components_for_pressure:
            watch_class = str((watch_by_component.get(component, {}) if isinstance(watch_by_component.get(component, {}), dict) else {}).get("watch_class", "NORMAL")).upper()
            watch_pressure = max(watch_pressure, _WATCH_PRESSURE.get(watch_class, 0.0))

            unresolved_ratio = _safe_float((resolution_by_component.get(component, {}) if isinstance(resolution_by_component.get(component, {}), dict) else {}).get("unresolved_ratio", 0.0))
            unresolved_pressure = max(unresolved_pressure, _clamp(unresolved_ratio, 0.0, 1.0))

            predictive_score = _safe_float((predictive_by_component.get(component, {}) if isinstance(predictive_by_component.get(component, {}), dict) else {}).get("risk_score", 0.0))
            predictive_pressure = max(predictive_pressure, _clamp(predictive_score, 0.0, 1.0))

            component_recurrence = _safe_int(recurring_count_by_component.get(component, 0))
            component_total = _safe_int((component_stats.get(component, {}) if isinstance(component_stats.get(component, {}), dict) else {}).get("total_regression_occurrences", 0))
            recurrence_ratio = _clamp(component_recurrence / max(1, component_total), 0.0, 1.0)
            recurrence_pressure = max(recurrence_pressure, recurrence_ratio)

        score = _clamp(
            (0.35 * scenario_detection_value)
            + (0.20 * watch_pressure)
            + (0.15 * predictive_pressure)
            + (0.15 * recurrence_pressure)
            + (0.15 * unresolved_pressure),
            0.0,
            1.0,
        ) * relevance

        plan_rows.append(
            {
                "scenario_id": scenario_id,
                "priority_score": round(score, 4),
                "required": False,
                "linked_components": sorted(linked_components),
                "touched_components_linked": touched_linked,
                "signals": {
                    "historical_detection_value": round(scenario_detection_value, 4),
                    "watch_pressure": round(watch_pressure, 4),
                    "predictive_pressure": round(predictive_pressure, 4),
                    "recurrence_pressure": round(recurrence_pressure, 4),
                    "unresolved_pressure": round(unresolved_pressure, 4),
                    "relevance": round(relevance, 4),
                },
                "selection_reason": "touched_component_coverage" if touched_linked else "historical_default_coverage",
            }
        )

    plan_rows = sorted(plan_rows, key=lambda item: (-_safe_float(item.get("priority_score", 0.0)), str(item.get("scenario_id", ""))))
    for idx, row in enumerate(plan_rows, start=1):
        row["priority_rank"] = idx

    # Required scenarios are those above threshold and top scenario when plan is elevated.
    for row in plan_rows:
        row["required"] = bool(_safe_float(row.get("priority_score", 0.0)) >= _PLAN_THRESHOLDS["REQUIRED_SCORE"])

    max_watch_pressure = max(
        [_WATCH_PRESSURE.get(str((watch_by_component.get(component, {}) if isinstance(watch_by_component.get(component, {}), dict) else {}).get("watch_class", "NORMAL")).upper(), 0.0) for component in normalized_components]
        + [0.0]
    )
    max_predictive_risk = max(
        [_clamp(_safe_float((predictive_by_component.get(component, {}) if isinstance(predictive_by_component.get(component, {}), dict) else {}).get("risk_score", 0.0)), 0.0, 1.0) for component in normalized_components]
        + [0.0]
    )
    max_unresolved = max(
        [_clamp(_safe_float((resolution_by_component.get(component, {}) if isinstance(resolution_by_component.get(component, {}), dict) else {}).get("unresolved_ratio", 0.0)), 0.0, 1.0) for component in normalized_components]
        + [0.0]
    )
    recurrence_pressure_global = max(
        [
            _clamp(
                _safe_int(recurring_count_by_component.get(component, 0))
                / max(1, _safe_int((component_stats.get(component, {}) if isinstance(component_stats.get(component, {}), dict) else {}).get("total_regression_occurrences", 0))),
                0.0,
                1.0,
            )
            for component in normalized_components
        ]
        + [0.0]
    )

    predictive_class = str((predictive_classification_payload.get("prediction", {}) if isinstance(predictive_classification_payload.get("prediction", {}), dict) else {}).get("overall_risk_class", "LOW")).upper()
    predictive_class_pressure = _RISK_CLASS_PRESSURE.get(predictive_class, 0.10)

    aggregate_plan_score = _clamp(
        (0.35 * max_watch_pressure)
        + (0.30 * max_predictive_risk)
        + (0.20 * max_unresolved)
        + (0.15 * recurrence_pressure_global)
        + (0.10 * predictive_class_pressure),
        0.0,
        1.0,
    )
    plan_class = _plan_class(aggregate_plan_score)

    if plan_class in {"HEIGHTENED", "CRITICAL"} and plan_rows:
        plan_rows[0]["required"] = True

    required_rows = [row for row in plan_rows if bool(row.get("required", False))]
    optional_rows = [row for row in plan_rows if not bool(row.get("required", False))]

    component_focus_rows: list[dict[str, Any]] = []
    for component in normalized_components:
        watch_row = watch_by_component.get(component, {}) if isinstance(watch_by_component.get(component, {}), dict) else {}
        resolution_row = resolution_by_component.get(component, {}) if isinstance(resolution_by_component.get(component, {}), dict) else {}
        predictive_row = predictive_by_component.get(component, {}) if isinstance(predictive_by_component.get(component, {}), dict) else {}

        focus_score = _clamp(
            0.45 * _WATCH_PRESSURE.get(str(watch_row.get("watch_class", "NORMAL")).upper(), 0.0)
            + 0.30 * _clamp(_safe_float(predictive_row.get("risk_score", 0.0)), 0.0, 1.0)
            + 0.25 * _clamp(_safe_float(resolution_row.get("unresolved_ratio", 0.0)), 0.0, 1.0),
            0.0,
            1.0,
        )

        component_focus_rows.append(
            {
                "component": component,
                "watch_class": str(watch_row.get("watch_class", "NORMAL")),
                "predictive_risk_score": round(_safe_float(predictive_row.get("risk_score", 0.0)), 4),
                "unresolved_ratio": round(_safe_float(resolution_row.get("unresolved_ratio", 0.0)), 4),
                "focus_score": round(focus_score, 4),
                "recommended_focus": "expanded_scenario_coverage" if focus_score >= 0.50 else "standard_component_checks",
            }
        )

    component_focus_rows = sorted(
        component_focus_rows,
        key=lambda row: (-_safe_float(row.get("focus_score", 0.0)), str(row.get("component", ""))),
    )
    for idx, row in enumerate(component_focus_rows, start=1):
        row["priority_rank"] = idx

    _write_json(
        planning_dir / "120_validation_plan_inputs.json",
        {
            "project_root": str(project_root.resolve()),
            "history_root": str(history_root.resolve()),
            "evidence_run_root": str(selected_evidence_run.resolve()),
            "predictive_run_root": str(selected_predictive_run.resolve()) if selected_predictive_run else "",
            "change_manifest": manifest,
            "touched_components": normalized_components,
            "thresholds": {
                "plan_thresholds": _PLAN_THRESHOLDS,
                "watch_pressure": _WATCH_PRESSURE,
                "risk_class_pressure": _RISK_CLASS_PRESSURE,
            },
        },
    )
    _write_json(planning_dir / "121_scenario_plan_ranking.json", {"rows": plan_rows})
    _write_json(
        planning_dir / "122_required_vs_optional_plan.json",
        {
            "required": required_rows,
            "optional": optional_rows,
        },
    )
    _write_json(planning_dir / "123_component_focus_plan.json", {"rows": component_focus_rows})
    _write_json(
        planning_dir / "124_plan_classification.json",
        {
            "plan_class": plan_class,
            "aggregate_plan_score": round(aggregate_plan_score, 4),
            "drivers": {
                "max_watch_pressure": round(max_watch_pressure, 4),
                "max_predictive_risk": round(max_predictive_risk, 4),
                "max_unresolved_ratio": round(max_unresolved, 4),
                "recurrence_pressure": round(recurrence_pressure_global, 4),
                "predictive_class": predictive_class,
                "predictive_class_pressure": round(predictive_class_pressure, 4),
            },
            "required_scenario_count": len(required_rows),
            "optional_scenario_count": len(optional_rows),
        },
    )

    summary_lines = [
        "# Pre-Merge Validation Plan Summary",
        "",
        f"- plan_class: {plan_class}",
        f"- aggregate_plan_score: {round(aggregate_plan_score, 4)}",
        f"- touched_component_count: {len(normalized_components)}",
        f"- required_scenario_count: {len(required_rows)}",
        f"- optional_scenario_count: {len(optional_rows)}",
        "",
        "## Top Required Scenarios",
    ]
    if required_rows:
        for row in required_rows[:10]:
            summary_lines.append(
                "- scenario_id="
                + str(row.get("scenario_id", ""))
                + " score="
                + str(row.get("priority_score", 0.0))
                + " reason="
                + str(row.get("selection_reason", ""))
            )
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Component Focus"])
    if component_focus_rows:
        for row in component_focus_rows[:10]:
            summary_lines.append(
                "- component="
                + str(row.get("component", ""))
                + " focus_score="
                + str(row.get("focus_score", 0.0))
                + " watch_class="
                + str(row.get("watch_class", "NORMAL"))
            )
    else:
        summary_lines.append("- none")

    _write_text(planning_dir / "125_validation_plan_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "plan": {
            "plan_class": plan_class,
            "aggregate_plan_score": round(aggregate_plan_score, 4),
            "required_scenario_count": len(required_rows),
            "optional_scenario_count": len(optional_rows),
            "touched_components": normalized_components,
        },
        "artifacts": [
            "planning/120_validation_plan_inputs.json",
            "planning/121_scenario_plan_ranking.json",
            "planning/122_required_vs_optional_plan.json",
            "planning/123_component_focus_plan.json",
            "planning/124_plan_classification.json",
            "planning/125_validation_plan_summary.md",
        ],
    }
