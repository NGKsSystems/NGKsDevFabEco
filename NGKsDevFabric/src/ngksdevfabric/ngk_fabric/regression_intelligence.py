from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SEVERITY_WEIGHTS = {
    "TRACE": 0.10,
    "LOW": 0.30,
    "MEDIUM": 0.60,
    "HIGH": 1.00,
}

_WATCH_THRESHOLDS = {
    "CRITICAL_RECURRENCE_RATE": 0.50,
    "CRITICAL_UNRESOLVED_RATIO": 0.50,
    "CRITICAL_MEAN_SEVERITY": 0.75,
    "HOT_RECURRENCE_RATE": 0.40,
    "HOT_UNRESOLVED_RATIO": 0.35,
    "WATCH_RECURRENCE_RATE": 0.20,
    "WATCH_UNRESOLVED_RATIO": 0.20,
    "CRITICAL_RECENT_REGRESSIONS": 3,
    "HOT_RECENT_REGRESSIONS": 2,
    "WATCH_RECENT_REGRESSIONS": 1,
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


def _watch_class(*, recurrence_rate: float, unresolved_ratio: float, mean_severity: float, recent_regressions: int) -> str:
    if (
        (unresolved_ratio >= _WATCH_THRESHOLDS["CRITICAL_UNRESOLVED_RATIO"] and recurrence_rate >= _WATCH_THRESHOLDS["CRITICAL_RECURRENCE_RATE"])
        or (mean_severity >= _WATCH_THRESHOLDS["CRITICAL_MEAN_SEVERITY"] and recurrence_rate >= _WATCH_THRESHOLDS["HOT_RECURRENCE_RATE"])
        or (unresolved_ratio >= _WATCH_THRESHOLDS["CRITICAL_UNRESOLVED_RATIO"] and recent_regressions >= _WATCH_THRESHOLDS["CRITICAL_RECENT_REGRESSIONS"])
    ):
        return "CRITICAL"
    if (
        recurrence_rate >= _WATCH_THRESHOLDS["HOT_RECURRENCE_RATE"]
        or unresolved_ratio >= _WATCH_THRESHOLDS["HOT_UNRESOLVED_RATIO"]
        or recent_regressions >= _WATCH_THRESHOLDS["HOT_RECENT_REGRESSIONS"]
    ):
        return "HOT"
    if (
        recurrence_rate >= _WATCH_THRESHOLDS["WATCH_RECURRENCE_RATE"]
        or unresolved_ratio >= _WATCH_THRESHOLDS["WATCH_UNRESOLVED_RATIO"]
        or recent_regressions >= _WATCH_THRESHOLDS["WATCH_RECENT_REGRESSIONS"]
    ):
        return "WATCH"
    return "NORMAL"


def _recommended_action(watch_class: str) -> str:
    if watch_class == "CRITICAL":
        return "block risky merges and enforce expanded validation scenarios"
    if watch_class == "HOT":
        return "increase pre-merge validation coverage"
    if watch_class == "WATCH":
        return "monitor trends and add targeted scenario checks"
    return "continue standard monitoring"


def analyze_regression_intelligence(*, history_root: Path, pf: Path) -> dict[str, Any]:
    intelligence_dir = pf / "intelligence"

    regression_store = _read_json(history_root / "regressions" / "regression_fingerprints.json")
    component_store = _read_json(history_root / "components" / "component_regression_stats.json")

    trend_health = _read_json(pf / "history" / "50_component_health_scores.json")
    trend_recurring = _read_json(pf / "history" / "53_recurring_regression_patterns.json")
    resolution_metrics = _read_json(pf / "resolution" / "71_component_resolution_metrics.json")
    lifecycle_states = _read_json(pf / "resolution" / "70_regression_lifecycle_states.json")
    remediation_guidance = _read_json(pf / "hotspots" / "13_remediation_guidance.json")

    fingerprint_rows = [row for row in regression_store.get("rows", []) if isinstance(row, dict)]
    component_rows_store = component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {}
    health_rows = [row for row in trend_health.get("rows", []) if isinstance(row, dict)]
    recurring_rows = [row for row in trend_recurring.get("rows", []) if isinstance(row, dict)]
    resolution_rows = [row for row in resolution_metrics.get("rows", []) if isinstance(row, dict)]
    lifecycle_rows = [row for row in lifecycle_states.get("rows", []) if isinstance(row, dict)]
    remediation_rows = [row for row in remediation_guidance.get("entries", []) if isinstance(row, dict)]

    health_index = {
        str(row.get("component", "")).strip(): row
        for row in health_rows
        if str(row.get("component", "")).strip()
    }
    resolution_index = {
        str(row.get("component", "")).strip(): row
        for row in resolution_rows
        if str(row.get("component", "")).strip()
    }

    persistence_by_component: dict[str, int] = {}
    for row in lifecycle_rows:
        if str(row.get("state", "")).upper() != "PERSISTING":
            continue
        component = str(row.get("component", "")).strip() or "unknown_component"
        persistence_by_component[component] = persistence_by_component.get(component, 0) + 1

    fp_by_component: dict[str, list[dict[str, Any]]] = {}
    for row in fingerprint_rows:
        component = str(row.get("component", "")).strip() or "unknown_component"
        fp_by_component.setdefault(component, []).append(row)

    all_components = sorted(
        {
            *[name for name in component_rows_store.keys() if str(name).strip()],
            *[str(row.get("component", "")).strip() for row in fingerprint_rows if str(row.get("component", "")).strip()],
            *[str(row.get("component", "")).strip() for row in resolution_rows if str(row.get("component", "")).strip()],
            *[str(row.get("component", "")).strip() for row in health_rows if str(row.get("component", "")).strip()],
        }
    )

    watch_rows: list[dict[str, Any]] = []
    for component in all_components:
        stats = component_rows_store.get(component, {}) if isinstance(component_rows_store.get(component, {}), dict) else {}
        health = health_index.get(component, {}) if isinstance(health_index.get(component, {}), dict) else {}
        resolution = resolution_index.get(component, {}) if isinstance(resolution_index.get(component, {}), dict) else {}
        rows = fp_by_component.get(component, [])

        regression_count = max(
            _safe_int(stats.get("total_regression_occurrences", 0)),
            sum(_safe_int(row.get("occurrences", 0)) for row in rows),
        )
        recurrence_count = sum(max(0, _safe_int(row.get("occurrences", 0)) - 1) for row in rows)
        recurrence_rate = _clamp(recurrence_count / max(1, regression_count), 0.0, 1.0)
        persistence_count = _safe_int(persistence_by_component.get(component, 0))

        severity_weighted = 0.0
        severity_occurrences = 0
        for row in rows:
            occ = max(0, _safe_int(row.get("occurrences", 0)))
            sev = str(row.get("severity_bucket", "TRACE")).upper()
            severity_weighted += _SEVERITY_WEIGHTS.get(sev, _SEVERITY_WEIGHTS["TRACE"]) * occ
            severity_occurrences += occ
        mean_severity = _clamp(severity_weighted / max(1, severity_occurrences), 0.0, 1.0)

        mean_time_to_resolution = _safe_float(resolution.get("mean_time_to_resolution", 0.0))
        resolved_count = _safe_int(resolution.get("resolved_regressions", 0))
        unresolved_count = _safe_int(resolution.get("unresolved_regressions", 0))
        unresolved_ratio = _clamp(unresolved_count / max(1, resolved_count + unresolved_count), 0.0, 1.0)
        recent_regressions = _safe_int(health.get("recent_regressions", 0))

        watch_class = _watch_class(
            recurrence_rate=recurrence_rate,
            unresolved_ratio=unresolved_ratio,
            mean_severity=mean_severity,
            recent_regressions=recent_regressions,
        )

        watch_rows.append(
            {
                "component": component,
                "watch_class": watch_class,
                "regression_count": regression_count,
                "recent_regressions": recent_regressions,
                "recurrence_count": recurrence_count,
                "recurrence_rate": round(recurrence_rate, 4),
                "persistence_count": persistence_count,
                "mean_severity": round(mean_severity, 4),
                "mean_time_to_resolution": round(mean_time_to_resolution, 4),
                "unresolved_ratio": round(unresolved_ratio, 4),
                "recommended_action": _recommended_action(watch_class),
            }
        )

    def _watch_rank(value: str) -> int:
        return {"CRITICAL": 0, "HOT": 1, "WATCH": 2, "NORMAL": 3}.get(value, 4)

    watch_rows = sorted(
        watch_rows,
        key=lambda row: (
            _watch_rank(str(row.get("watch_class", "NORMAL"))),
            -_safe_int(row.get("regression_count", 0)),
            -_safe_float(row.get("mean_severity", 0.0)),
            str(row.get("component", "")),
        ),
    )

    top_repeated = sorted(
        [
            {
                "fingerprint": str(row.get("fingerprint", "")),
                "component": str(row.get("component", "")),
                "scenario_id": str(row.get("scenario_id", "")),
                "metric": str(row.get("metric", "")),
                "occurrences": _safe_int(row.get("occurrences", 0)),
            }
            for row in fingerprint_rows
        ],
        key=lambda item: (-_safe_int(item.get("occurrences", 0)), str(item.get("fingerprint", ""))),
    )

    persisting_index = {
        str(row.get("fingerprint", "")).strip(): row
        for row in lifecycle_rows
        if str(row.get("state", "")).upper() == "PERSISTING" and str(row.get("fingerprint", "")).strip()
    }
    longest_persisting = sorted(
        [
            {
                "fingerprint": str(row.get("fingerprint", "")),
                "component": str(row.get("component", "")),
                "scenario_id": str(row.get("scenario_id", "")),
                "metric": str(row.get("metric", "")),
                "streak_before_current": _safe_int(row.get("streak_before_current", 0)),
            }
            for row in persisting_index.values()
        ],
        key=lambda item: (-_safe_int(item.get("streak_before_current", 0)), str(item.get("fingerprint", ""))),
    )

    most_severe_recurring = sorted(
        [
            {
                "fingerprint": str(row.get("fingerprint", "")),
                "component": str(row.get("component", "")),
                "scenario_id": str(row.get("scenario_id", "")),
                "metric": str(row.get("metric", "")),
                "severity_bucket": str(row.get("severity_bucket", "TRACE")),
                "occurrences": _safe_int(row.get("occurrences", 0)),
                "severity_score": round(
                    _SEVERITY_WEIGHTS.get(str(row.get("severity_bucket", "TRACE")).upper(), _SEVERITY_WEIGHTS["TRACE"])
                    * max(1, _safe_int(row.get("occurrences", 0))),
                    4,
                ),
            }
            for row in fingerprint_rows
            if _safe_int(row.get("occurrences", 0)) > 1
        ],
        key=lambda item: (-_safe_float(item.get("severity_score", 0.0)), str(item.get("fingerprint", ""))),
    )

    scenario_rows_index: dict[str, dict[str, Any]] = {}
    for row in fingerprint_rows:
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            continue
        sev = _SEVERITY_WEIGHTS.get(str(row.get("severity_bucket", "TRACE")).upper(), _SEVERITY_WEIGHTS["TRACE"])
        occurrences = max(1, _safe_int(row.get("occurrences", 0)))
        entry = scenario_rows_index.setdefault(
            scenario_id,
            {
                "scenario_id": scenario_id,
                "detection_count": 0,
                "meaningful_regression_count": 0,
                "severity_weighted_score": 0.0,
                "recurring_detection_count": 0,
            },
        )
        entry["detection_count"] += occurrences
        entry["severity_weighted_score"] += sev * occurrences
        if sev >= _SEVERITY_WEIGHTS["MEDIUM"]:
            entry["meaningful_regression_count"] += occurrences
        if occurrences > 1:
            entry["recurring_detection_count"] += 1

    scenario_rows: list[dict[str, Any]] = []
    for entry in scenario_rows_index.values():
        detection_count = _safe_int(entry.get("detection_count", 0))
        recurring_detection_count = _safe_int(entry.get("recurring_detection_count", 0))
        effectiveness = _clamp(recurring_detection_count / max(1, detection_count), 0.0, 1.0)
        entry["severity_weighted_score"] = round(_safe_float(entry.get("severity_weighted_score", 0.0)), 4)
        entry["repeated_detection_effectiveness"] = round(effectiveness, 4)
        scenario_rows.append(entry)
    scenario_rows = sorted(
        scenario_rows,
        key=lambda row: (
            -_safe_float(row.get("severity_weighted_score", 0.0)),
            -_safe_int(row.get("meaningful_regression_count", 0)),
            str(row.get("scenario_id", "")),
        ),
    )

    remediation_component_index: dict[str, list[dict[str, Any]]] = {}
    for row in remediation_rows:
        component = str(row.get("likely_component", "")).strip()
        if not component:
            continue
        remediation_component_index.setdefault(component, []).append(row)

    remediation_rows_out: list[dict[str, Any]] = []
    for component in all_components:
        resolution = resolution_index.get(component, {}) if isinstance(resolution_index.get(component, {}), dict) else {}
        resolved_count = _safe_int(resolution.get("resolved_regressions", 0))
        unresolved_count = _safe_int(resolution.get("unresolved_regressions", 0))
        total = max(1, resolved_count + unresolved_count)
        resolution_rate = _clamp(resolved_count / total, 0.0, 1.0)
        unresolved_ratio = _clamp(unresolved_count / total, 0.0, 1.0)
        mean_ttr = _safe_float(resolution.get("mean_time_to_resolution", 0.0))

        effectiveness_class = "MODERATE"
        if resolution_rate >= 0.75 and mean_ttr <= 2.0 and unresolved_ratio < 0.25:
            effectiveness_class = "STRONG"
        elif resolution_rate < 0.40 or unresolved_ratio > 0.60:
            effectiveness_class = "WEAK"

        remediation_rows_out.append(
            {
                "component": component,
                "remediation_count": len(remediation_component_index.get(component, [])),
                "resolution_rate": round(resolution_rate, 4),
                "unresolved_ratio": round(unresolved_ratio, 4),
                "mean_time_to_resolution": round(mean_ttr, 4),
                "effectiveness_class": effectiveness_class,
                "correlation_note": "derived_from_component_resolution_metrics",
            }
        )
    remediation_rows_out = sorted(
        remediation_rows_out,
        key=lambda row: (
            str(row.get("effectiveness_class", "MODERATE")) != "WEAK",
            str(row.get("effectiveness_class", "MODERATE")) != "MODERATE",
            str(row.get("effectiveness_class", "MODERATE")) != "STRONG",
            str(row.get("component", "")),
        ),
    )

    insufficient_history = len(fingerprint_rows) < 3 or len(watch_rows) < 2

    _write_json(
        intelligence_dir / "110_component_watchlist.json",
        {
            "watch_thresholds": _WATCH_THRESHOLDS,
            "insufficient_history": insufficient_history,
            "rows": watch_rows,
        },
    )
    _write_json(
        intelligence_dir / "111_regression_pattern_memory.json",
        {
            "top_repeated_fingerprints": top_repeated[:25],
            "longest_persisting_fingerprints": longest_persisting[:25],
            "most_severe_recurring_fingerprints": most_severe_recurring[:25],
        },
    )
    _write_json(
        intelligence_dir / "112_scenario_detection_value.json",
        {
            "rows": scenario_rows,
        },
    )
    _write_json(
        intelligence_dir / "113_remediation_effectiveness.json",
        {
            "rows": remediation_rows_out,
        },
    )

    summary_lines = [
        "# Regression Intelligence Summary",
        "",
        f"- component_count: {len(watch_rows)}",
        f"- fingerprint_count: {len(fingerprint_rows)}",
        f"- scenario_count: {len(scenario_rows)}",
        f"- insufficient_history: {str(insufficient_history).lower()}",
        f"- critical_components: {sum(1 for row in watch_rows if str(row.get('watch_class', '')) == 'CRITICAL')}",
        f"- hot_components: {sum(1 for row in watch_rows if str(row.get('watch_class', '')) == 'HOT')}",
        "",
        "## Top Chronic Components",
    ]
    if watch_rows:
        for row in watch_rows[:10]:
            summary_lines.append(
                "- component="
                + str(row.get("component", ""))
                + " watch_class="
                + str(row.get("watch_class", ""))
                + " regression_count="
                + str(row.get("regression_count", 0))
                + " recurrence_rate="
                + str(row.get("recurrence_rate", 0.0))
                + " unresolved_ratio="
                + str(row.get("unresolved_ratio", 0.0))
            )
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Top Recurring Fingerprints"])
    if top_repeated:
        for row in top_repeated[:10]:
            summary_lines.append(
                "- fingerprint="
                + str(row.get("fingerprint", ""))
                + " occurrences="
                + str(row.get("occurrences", 0))
                + " component="
                + str(row.get("component", ""))
            )
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Highest-Value Scenarios"])
    if scenario_rows:
        for row in scenario_rows[:10]:
            summary_lines.append(
                "- scenario_id="
                + str(row.get("scenario_id", ""))
                + " severity_weighted_score="
                + str(row.get("severity_weighted_score", 0.0))
                + " meaningful_regression_count="
                + str(row.get("meaningful_regression_count", 0))
            )
    else:
        summary_lines.append("- none")

    summary_lines.extend(["", "## Remediation Effectiveness"])
    if remediation_rows_out:
        for row in remediation_rows_out[:10]:
            summary_lines.append(
                "- component="
                + str(row.get("component", ""))
                + " effectiveness_class="
                + str(row.get("effectiveness_class", ""))
                + " resolution_rate="
                + str(row.get("resolution_rate", 0.0))
                + " mean_time_to_resolution="
                + str(row.get("mean_time_to_resolution", 0.0))
            )
    else:
        summary_lines.append("- none")

    _write_text(intelligence_dir / "114_intelligence_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "summary": {
            "component_count": len(watch_rows),
            "fingerprint_count": len(fingerprint_rows),
            "scenario_count": len(scenario_rows),
            "insufficient_history": insufficient_history,
        },
        "artifacts": [
            "intelligence/110_component_watchlist.json",
            "intelligence/111_regression_pattern_memory.json",
            "intelligence/112_scenario_detection_value.json",
            "intelligence/113_remediation_effectiveness.json",
            "intelligence/114_intelligence_summary.md",
        ],
    }
