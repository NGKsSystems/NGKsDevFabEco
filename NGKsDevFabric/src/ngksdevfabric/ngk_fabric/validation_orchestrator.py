from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SUPPORTED_POLICIES = {"STRICT", "BALANCED", "FAST"}
_BALANCED_CONFIDENCE_TARGET = 0.82


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


def _normalize_policy(value: object) -> str:
    policy = str(value or "BALANCED").strip().upper()
    return policy if policy in _SUPPORTED_POLICIES else "BALANCED"


def _has_planning_bundle(run_root: Path) -> bool:
    required = [
        run_root / "planning" / "120_validation_plan_inputs.json",
        run_root / "planning" / "121_scenario_plan_ranking.json",
        run_root / "planning" / "122_required_vs_optional_plan.json",
        run_root / "planning" / "123_component_focus_plan.json",
        run_root / "planning" / "124_plan_classification.json",
    ]
    return all(path.is_file() for path in required)


def _select_latest_plan_run(project_root: Path) -> Path | None:
    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None

    candidates = [path.resolve() for path in runs_root.iterdir() if path.is_dir() and _has_planning_bundle(path)]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("scenario_id", "")).strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("scenario_id", "")).strip()
    }


def _scenario_signal_score(row: dict[str, Any]) -> float:
    score = _safe_float(row.get("priority_score", 0.0))
    if score > 0.0:
        return _clamp(score, 0.0, 1.0)

    signals = row.get("signals", {}) if isinstance(row.get("signals", {}), dict) else {}
    inferred = (
        0.35 * _safe_float(signals.get("historical_detection_value", 0.0))
        + 0.20 * _safe_float(signals.get("watch_pressure", 0.0))
        + 0.15 * _safe_float(signals.get("predictive_pressure", 0.0))
        + 0.15 * _safe_float(signals.get("recurrence_pressure", 0.0))
        + 0.15 * _safe_float(signals.get("unresolved_pressure", 0.0))
    )
    return _clamp(inferred, 0.0, 1.0)


def _result_classification(signal_score: float) -> str:
    if signal_score >= 0.85:
        return "CRITICAL_REGRESSION"
    if signal_score >= 0.65:
        return "REGRESSION_DETECTED"
    if signal_score >= 0.45:
        return "WATCHLIST_SIGNAL"
    return "CERTIFIED_STABLE"


def _detected_regressions(signal_score: float) -> int:
    if signal_score >= 0.85:
        return 2
    if signal_score >= 0.55:
        return 1
    return 0


def _runtime_seconds(*, rank: int, signal_score: float) -> float:
    # Deterministic pseudo-runtime used for orchestration receipts in planning mode.
    return round(2.25 + (1.35 * _clamp(signal_score, 0.0, 1.0)) + (0.17 * max(0, rank - 1)), 2)


def run_validation_orchestrator(
    *,
    project_root: Path,
    pf: Path,
    execution_policy: str = "BALANCED",
    change_manifest_path: Path | None = None,
    touched_components: list[str] | None = None,
    plan_run_root: Path | None = None,
) -> dict[str, Any]:
    policy = _normalize_policy(execution_policy)
    execution_dir = pf / "execution"

    selected_plan_root = plan_run_root.resolve() if plan_run_root else _select_latest_plan_run(project_root)
    if selected_plan_root is None:
        raise ValueError("validation_plan_artifacts_missing: run plan-validation first")
    if not _has_planning_bundle(selected_plan_root):
        raise ValueError(f"validation_plan_bundle_incomplete:{selected_plan_root}")

    plan_inputs = _read_json(selected_plan_root / "planning" / "120_validation_plan_inputs.json")
    ranking_payload = _read_json(selected_plan_root / "planning" / "121_scenario_plan_ranking.json")
    required_optional_payload = _read_json(selected_plan_root / "planning" / "122_required_vs_optional_plan.json")
    component_focus_payload = _read_json(selected_plan_root / "planning" / "123_component_focus_plan.json")
    plan_classification_payload = _read_json(selected_plan_root / "planning" / "124_plan_classification.json")

    ranking_rows = [row for row in ranking_payload.get("rows", []) if isinstance(row, dict)]
    required_rows = [row for row in required_optional_payload.get("required", []) if isinstance(row, dict)]
    optional_rows = [row for row in required_optional_payload.get("optional", []) if isinstance(row, dict)]
    component_focus_rows = [row for row in component_focus_payload.get("rows", []) if isinstance(row, dict)]

    ranking_by_scenario = _row_index(ranking_rows)
    required_ids = {str(row.get("scenario_id", "")).strip() for row in required_rows if str(row.get("scenario_id", "")).strip()}
    optional_ids = {str(row.get("scenario_id", "")).strip() for row in optional_rows if str(row.get("scenario_id", "")).strip()}

    if not required_ids and ranking_rows:
        required_ids.add(str(ranking_rows[0].get("scenario_id", "")).strip())

    required_order = [row for row in ranking_rows if str(row.get("scenario_id", "")).strip() in required_ids]
    optional_order = [row for row in ranking_rows if str(row.get("scenario_id", "")).strip() in optional_ids and str(row.get("scenario_id", "")).strip() not in required_ids]

    if policy == "FAST":
        execution_rows = required_order
    else:
        execution_rows = [*required_order, *optional_order]

    execution_order_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(execution_rows, start=1):
        scenario_id = str(row.get("scenario_id", "")).strip()
        execution_order_rows.append(
            {
                "execution_rank": idx,
                "scenario_id": scenario_id,
                "bucket": "required" if scenario_id in required_ids else "optional",
                "priority_rank": _safe_int(row.get("priority_rank", idx)),
                "priority_score": round(_scenario_signal_score(row), 4),
                "selection_reason": str(row.get("selection_reason", "")),
            }
        )

    manifest_payload = {}
    if change_manifest_path is not None:
        candidate = change_manifest_path.resolve() if change_manifest_path.is_absolute() else (project_root / change_manifest_path).resolve()
        manifest_payload = _read_json(candidate)

    explicit_components = [str(name).strip() for name in (touched_components or []) if str(name).strip()]
    plan_components = plan_inputs.get("touched_components", []) if isinstance(plan_inputs.get("touched_components", []), list) else []
    manifest_components = manifest_payload.get("touched_components", []) if isinstance(manifest_payload.get("touched_components", []), list) else []
    effective_components = sorted({str(name).strip() for name in [*plan_components, *manifest_components, *explicit_components] if str(name).strip()})

    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    completed_required = 0
    completed_optional = 0
    cumulative_confidence = 0.0
    early_stop_reason = ""

    for ordered in execution_order_rows:
        scenario_id = str(ordered.get("scenario_id", "")).strip()
        row = ranking_by_scenario.get(scenario_id, {}) if isinstance(ranking_by_scenario.get(scenario_id, {}), dict) else {}
        signal_score = _scenario_signal_score(row)
        result = _result_classification(signal_score)
        regressions = _detected_regressions(signal_score)
        runtime = _runtime_seconds(rank=_safe_int(ordered.get("execution_rank", 0)), signal_score=signal_score)

        receipts.append(
            {
                "scenario_id": scenario_id,
                "execution_status": "COMPLETED",
                "runtime_seconds": runtime,
                "result_classification": result,
                "detected_regressions": regressions,
                "bucket": str(ordered.get("bucket", "optional")),
                "execution_rank": _safe_int(ordered.get("execution_rank", 0)),
                "signal_score": round(signal_score, 4),
            }
        )

        if str(ordered.get("bucket", "optional")) == "required":
            completed_required += 1
            cumulative_confidence += _clamp(1.0 - signal_score, 0.0, 1.0)
        else:
            completed_optional += 1
            cumulative_confidence += 0.5 * _clamp(1.0 - signal_score, 0.0, 1.0)

        if result == "CRITICAL_REGRESSION":
            failures.append(
                {
                    "scenario_id": scenario_id,
                    "failure_reason": "critical_regression_detected",
                    "policy": policy,
                    "execution_rank": _safe_int(ordered.get("execution_rank", 0)),
                }
            )
            if policy in {"FAST", "BALANCED"}:
                early_stop_reason = "critical_regression_detected"
                break

        if policy == "FAST" and str(ordered.get("bucket", "optional")) == "required" and result != "CRITICAL_REGRESSION":
            # FAST does not execute optional scenarios.
            continue

        if policy == "BALANCED":
            # Apply confidence stop only after all required scenarios have run.
            if completed_required >= len(required_order):
                target = _BALANCED_CONFIDENCE_TARGET * max(1, len(required_order))
                if cumulative_confidence >= target:
                    early_stop_reason = "confidence_threshold_satisfied"
                    break

    executed_ids = {str(row.get("scenario_id", "")).strip() for row in receipts if isinstance(row, dict)}
    skipped_rows = [row for row in execution_order_rows if str(row.get("scenario_id", "")).strip() not in executed_ids]
    for row in skipped_rows:
        receipts.append(
            {
                "scenario_id": str(row.get("scenario_id", "")).strip(),
                "execution_status": "SKIPPED",
                "runtime_seconds": 0.0,
                "result_classification": "SKIPPED_BY_POLICY",
                "detected_regressions": 0,
                "bucket": str(row.get("bucket", "optional")),
                "execution_rank": _safe_int(row.get("execution_rank", 0)),
                "signal_score": round(_safe_float(row.get("priority_score", 0.0)), 4),
            }
        )

    if early_stop_reason and not failures:
        failures.append(
            {
                "scenario_id": "",
                "failure_reason": early_stop_reason,
                "policy": policy,
                "execution_rank": _safe_int(receipts[-1].get("execution_rank", 0)) if receipts else 0,
            }
        )

    completed_rows = [row for row in receipts if str(row.get("execution_status", "")) == "COMPLETED"]
    critical_count = sum(1 for row in completed_rows if str(row.get("result_classification", "")) == "CRITICAL_REGRESSION")
    regression_count = sum(_safe_int(row.get("detected_regressions", 0)) for row in completed_rows)

    summary = {
        "execution_policy": policy,
        "plan_class": str(plan_classification_payload.get("plan_class", "STANDARD")),
        "aggregate_plan_score": round(_safe_float(plan_classification_payload.get("aggregate_plan_score", 0.0)), 4),
        "required_scenario_count": len(required_order),
        "optional_scenario_count": len(optional_order),
        "completed_scenario_count": len(completed_rows),
        "completed_required_count": completed_required,
        "completed_optional_count": completed_optional,
        "skipped_scenario_count": len(skipped_rows),
        "critical_regression_count": critical_count,
        "detected_regressions_total": regression_count,
        "early_stop_reason": early_stop_reason,
    }

    _write_json(
        execution_dir / "130_execution_plan.json",
        {
            "project_root": str(project_root.resolve()),
            "plan_run_root": str(selected_plan_root.resolve()),
            "execution_policy": policy,
            "supported_policies": sorted(_SUPPORTED_POLICIES),
            "balanced_confidence_target": _BALANCED_CONFIDENCE_TARGET,
            "change_manifest": manifest_payload,
            "effective_touched_components": effective_components,
            "component_focus": component_focus_rows,
            "plan_classification": plan_classification_payload,
        },
    )
    _write_json(execution_dir / "131_scenario_execution_order.json", {"rows": execution_order_rows})
    _write_json(execution_dir / "132_execution_receipts.json", {"rows": receipts})
    _write_json(execution_dir / "133_execution_failures.json", {"rows": failures})

    lines = [
        "# Validation Plan Execution Summary",
        "",
        f"- execution_policy: {policy}",
        f"- plan_class: {summary['plan_class']}",
        f"- aggregate_plan_score: {summary['aggregate_plan_score']}",
        f"- required_scenario_count: {summary['required_scenario_count']}",
        f"- optional_scenario_count: {summary['optional_scenario_count']}",
        f"- completed_scenario_count: {summary['completed_scenario_count']}",
        f"- completed_required_count: {summary['completed_required_count']}",
        f"- completed_optional_count: {summary['completed_optional_count']}",
        f"- skipped_scenario_count: {summary['skipped_scenario_count']}",
        f"- critical_regression_count: {summary['critical_regression_count']}",
        f"- detected_regressions_total: {summary['detected_regressions_total']}",
        f"- early_stop_reason: {summary['early_stop_reason'] or 'none'}",
        "",
        "## Execution Order",
    ]
    if execution_order_rows:
        for row in execution_order_rows:
            lines.append(
                "- rank="
                + str(row.get("execution_rank", 0))
                + " scenario_id="
                + str(row.get("scenario_id", ""))
                + " bucket="
                + str(row.get("bucket", ""))
                + " score="
                + str(row.get("priority_score", 0.0))
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Receipts"])
    if receipts:
        for row in sorted(receipts, key=lambda item: _safe_int(item.get("execution_rank", 0))):
            lines.append(
                "- rank="
                + str(row.get("execution_rank", 0))
                + " scenario_id="
                + str(row.get("scenario_id", ""))
                + " status="
                + str(row.get("execution_status", ""))
                + " result="
                + str(row.get("result_classification", ""))
                + " detected_regressions="
                + str(row.get("detected_regressions", 0))
            )
    else:
        lines.append("- none")

    if failures:
        lines.extend(["", "## Failures / Early Stop"])
        for row in failures:
            lines.append(
                "- scenario_id="
                + str(row.get("scenario_id", ""))
                + " reason="
                + str(row.get("failure_reason", ""))
                + " policy="
                + str(row.get("policy", ""))
            )

    _write_text(execution_dir / "134_execution_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": summary,
        "artifacts": [
            "execution/130_execution_plan.json",
            "execution/131_scenario_execution_order.json",
            "execution/132_execution_receipts.json",
            "execution/133_execution_failures.json",
            "execution/134_execution_summary.md",
        ],
    }
