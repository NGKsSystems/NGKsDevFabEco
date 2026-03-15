from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_RUN_FILE_RE = re.compile(r"^run_(\d{6})\.json$")
_SEVERITY_WEIGHTS = {
    "TRACE": 0.10,
    "LOW": 0.30,
    "MEDIUM": 0.60,
    "HIGH": 1.00,
}


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


def _health_class(score: float) -> str:
    if score >= 0.80:
        return "HEALTHY"
    if score >= 0.60:
        return "WATCH"
    if score >= 0.40:
        return "DEGRADED"
    return "CRITICAL"


def _run_rows(runs_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return rows

    for child in runs_dir.iterdir():
        if not child.is_file():
            continue
        match = _RUN_FILE_RE.match(child.name)
        if not match:
            continue
        data = _read_json(child)
        rows.append(
            {
                "history_run_id": str(data.get("history_run_id", child.stem)),
                "run_num": _safe_int(match.group(1)),
                "regression_count": _safe_int(data.get("regression_count", 0)),
                "certification_decision": str(data.get("certification_decision", "")),
                "gate_result": str(data.get("gate_result", "")),
            }
        )

    return sorted(rows, key=lambda row: int(row.get("run_num", 0)))


def analyze_historical_trends(*, history_root: Path, pf: Path) -> dict[str, Any]:
    runs = _run_rows(history_root / "runs")
    regression_store = _read_json(history_root / "regressions" / "regression_fingerprints.json")
    component_store = _read_json(history_root / "components" / "component_regression_stats.json")

    fingerprint_rows = regression_store.get("rows", []) if isinstance(regression_store.get("rows", []), list) else []
    component_rows = (
        component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {}
    )

    recent_window = min(5, max(1, len(runs)))
    recent_run_ids = {str(row.get("history_run_id", "")) for row in runs[-recent_window:]}
    total_runs = len(runs)

    comp_accum: dict[str, dict[str, Any]] = {}
    recurring_patterns: list[dict[str, Any]] = []

    for row in fingerprint_rows:
        if not isinstance(row, dict):
            continue
        component = str(row.get("component", "")).strip() or "unknown_component"
        occurrences = _safe_int(row.get("occurrences", 0))
        severity_bucket = str(row.get("severity_bucket", "TRACE")).upper()
        severity_weight = _SEVERITY_WEIGHTS.get(severity_bucket, _SEVERITY_WEIGHTS["TRACE"])
        last_seen = str(row.get("last_seen_run", ""))
        recurrence = max(0, occurrences - 1)

        acc = comp_accum.setdefault(
            component,
            {
                "component": component,
                "regression_count": 0,
                "severity_weighted_sum": 0.0,
                "recurrence_count": 0,
                "recent_regressions": 0,
                "severity_buckets": {"TRACE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0},
            },
        )
        acc["regression_count"] = _safe_int(acc.get("regression_count", 0)) + occurrences
        acc["severity_weighted_sum"] = _safe_float(acc.get("severity_weighted_sum", 0.0)) + (severity_weight * occurrences)
        acc["recurrence_count"] = _safe_int(acc.get("recurrence_count", 0)) + recurrence
        if last_seen in recent_run_ids:
            acc["recent_regressions"] = _safe_int(acc.get("recent_regressions", 0)) + 1

        buckets = acc.get("severity_buckets", {}) if isinstance(acc.get("severity_buckets", {}), dict) else {}
        buckets[severity_bucket] = _safe_int(buckets.get(severity_bucket, 0)) + occurrences
        acc["severity_buckets"] = buckets

        if occurrences > 1:
            recurring_patterns.append(
                {
                    "fingerprint": str(row.get("fingerprint", "")),
                    "component": component,
                    "scenario_id": str(row.get("scenario_id", "")),
                    "metric": str(row.get("metric", "")),
                    "severity_bucket": severity_bucket,
                    "occurrences": occurrences,
                    "last_seen_run": last_seen,
                }
            )

    for component, stats in component_rows.items():
        if component not in comp_accum:
            comp_accum[component] = {
                "component": component,
                "regression_count": _safe_int(stats.get("total_regression_occurrences", 0)),
                "severity_weighted_sum": 0.0,
                "recurrence_count": 0,
                "recent_regressions": 0,
                "severity_buckets": {"TRACE": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0},
            }

    health_rows: list[dict[str, Any]] = []
    frequency_divisor = max(3, total_runs)
    recent_divisor = max(1, recent_window)

    for component in sorted(comp_accum.keys()):
        acc = comp_accum[component]
        regression_count = _safe_int(acc.get("regression_count", 0))
        recurrence_count = _safe_int(acc.get("recurrence_count", 0))
        recent_regressions = _safe_int(acc.get("recent_regressions", 0))
        severity_weighted_sum = _safe_float(acc.get("severity_weighted_sum", 0.0))

        severity_distribution = _clamp(severity_weighted_sum / max(1, regression_count), 0.0, 1.0)
        frequency_factor = _clamp(regression_count / frequency_divisor, 0.0, 1.0)
        recurrence_rate = _clamp(recurrence_count / max(1, regression_count), 0.0, 1.0)
        recent_density = _clamp(recent_regressions / recent_divisor, 0.0, 1.0)

        health_score = _clamp(
            1.0 - (0.40 * frequency_factor + 0.25 * severity_distribution + 0.20 * recurrence_rate + 0.15 * recent_density),
            0.0,
            1.0,
        )

        health_rows.append(
            {
                "component": component,
                "health_score": round(health_score, 4),
                "health_class": _health_class(health_score),
                "regression_count": regression_count,
                "recent_regressions": recent_regressions,
                "recurrence_rate": round(recurrence_rate, 4),
                "severity_distribution": round(severity_distribution, 4),
            }
        )

    ranking_rows = sorted(
        health_rows,
        key=lambda row: (
            str(row.get("health_class", "")) != "CRITICAL",
            str(row.get("health_class", "")) != "DEGRADED",
            str(row.get("health_class", "")) != "WATCH",
            -_safe_int(row.get("regression_count", 0)),
            _safe_float(row.get("health_score", 0.0)),
            str(row.get("component", "")),
        ),
    )
    for idx, row in enumerate(ranking_rows, start=1):
        row["rank"] = idx

    recurring_patterns = sorted(
        recurring_patterns,
        key=lambda row: (
            -_safe_int(row.get("occurrences", 0)),
            str(row.get("component", "")),
            str(row.get("fingerprint", "")),
        ),
    )

    trend_classification = "INSUFFICIENT_HISTORY"
    trend_reason = "single_run_history"
    if len(runs) >= 2:
        prev_counts = [_safe_int(row.get("regression_count", 0)) for row in runs[:-1]]
        latest = _safe_int(runs[-1].get("regression_count", 0))
        baseline = sum(prev_counts) / max(1, len(prev_counts))
        delta = latest - baseline
        if delta >= 0.5:
            trend_classification = "RISING"
            trend_reason = "latest_regression_count_above_baseline"
        elif delta <= -0.5:
            trend_classification = "IMPROVING"
            trend_reason = "latest_regression_count_below_baseline"
        else:
            trend_classification = "STABLE"
            trend_reason = "latest_regression_count_near_baseline"

    trend_payload = {
        "run_count": len(runs),
        "trend_classification": trend_classification,
        "trend_reason": trend_reason,
        "latest_run_id": str(runs[-1].get("history_run_id", "")) if runs else "",
        "recurring_pattern_count": len(recurring_patterns),
        "component_count": len(health_rows),
    }

    history_out = pf / "history"
    _write_json(
        history_out / "50_component_health_scores.json",
        {
            "health_model": {
                "frequency_weight": 0.40,
                "severity_weight": 0.25,
                "recurrence_weight": 0.20,
                "recent_density_weight": 0.15,
                "recent_window_runs": recent_window,
            },
            "rows": health_rows,
        },
    )
    _write_json(history_out / "51_component_regression_ranking.json", {"rows": ranking_rows})
    _write_json(history_out / "52_regression_trend_analysis.json", trend_payload)
    _write_json(history_out / "53_recurring_regression_patterns.json", {"rows": recurring_patterns})

    lines = [
        "# Historical Trend Summary",
        "",
        f"- run_count: {len(runs)}",
        f"- trend_classification: {trend_classification}",
        f"- trend_reason: {trend_reason}",
        f"- component_count: {len(health_rows)}",
        f"- recurring_pattern_count: {len(recurring_patterns)}",
        "",
        "## Lowest Health Components",
    ]
    if ranking_rows:
        for row in ranking_rows[:10]:
            lines.append(
                f"- rank {row.get('rank', 0)} component={row.get('component', '')} health_score={row.get('health_score', 0.0)} class={row.get('health_class', '')} regressions={row.get('regression_count', 0)}"
            )
    else:
        lines.append("- no component history available")

    _write_text(history_out / "54_history_trend_summary.md", "\n".join(lines) + "\n")

    return {
        "trend_analysis": trend_payload,
        "component_health_rows": health_rows,
        "component_ranking_rows": ranking_rows,
        "recurring_patterns": recurring_patterns,
        "artifacts": [
            "history/50_component_health_scores.json",
            "history/51_component_regression_ranking.json",
            "history/52_regression_trend_analysis.json",
            "history/53_recurring_regression_patterns.json",
            "history/54_history_trend_summary.md",
        ],
    }
