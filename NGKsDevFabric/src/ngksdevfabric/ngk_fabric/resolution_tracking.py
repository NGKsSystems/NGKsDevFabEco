from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_RUN_ID_RE = re.compile(r"^run_(\d{6})$")


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


def _run_num(run_id: str) -> int:
    match = _RUN_ID_RE.match(run_id.strip())
    if not match:
        return 0
    return _safe_int(match.group(1))


def _collect_proof_history_rows(runs_root: Path) -> dict[str, dict[str, Any]]:
    rows_by_run: dict[str, dict[str, Any]] = {}
    if not runs_root.is_dir():
        return rows_by_run

    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        run_record = _read_json(child / "history" / "40_run_record.json")
        history_run_id = str(run_record.get("history_run_id", "")).strip()
        if not history_run_id:
            continue

        detected_store = _read_json(child / "history" / "41_regression_fingerprints_detected.json")
        detected_rows = detected_store.get("rows", []) if isinstance(detected_store.get("rows", []), list) else []
        normalized_rows = [row for row in detected_rows if isinstance(row, dict)]

        rows_by_run[history_run_id] = {
            "history_run_id": history_run_id,
            "run_num": _run_num(history_run_id),
            "detected_rows": normalized_rows,
            "detected_set": {str(row.get("fingerprint", "")).strip() for row in normalized_rows if str(row.get("fingerprint", "")).strip()},
        }

    return rows_by_run


def _collect_presence_map(run_rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    presence: dict[str, list[int]] = {}
    for run in run_rows:
        run_num = _safe_int(run.get("run_num", 0))
        detected_set = run.get("detected_set", set()) if isinstance(run.get("detected_set", set()), set) else set()
        for fingerprint in sorted(detected_set):
            presence.setdefault(fingerprint, []).append(run_num)

    for fingerprint in list(presence.keys()):
        presence[fingerprint] = sorted(set(presence[fingerprint]))

    return presence


def _consecutive_streak_before(presence_runs: list[int], current_run_num: int) -> int:
    if not presence_runs:
        return 0
    present = set(presence_runs)
    streak = 0
    probe = current_run_num - 1
    while probe in present and probe > 0:
        streak += 1
        probe -= 1
    return streak


def _resolution_streak_lengths(presence_runs: list[int], latest_run_num: int) -> list[int]:
    if not presence_runs:
        return []

    values = sorted(set(presence_runs))
    streaks: list[tuple[int, int]] = []
    start = values[0]
    prev = values[0]
    for run_num in values[1:]:
        if run_num == prev + 1:
            prev = run_num
            continue
        streaks.append((start, prev))
        start = run_num
        prev = run_num
    streaks.append((start, prev))

    resolved_lengths: list[int] = []
    for start_num, end_num in streaks:
        # If a streak does not reach the latest run, it has been resolved.
        if end_num < latest_run_num:
            resolved_lengths.append(max(1, end_num - start_num + 1))
    return resolved_lengths


def analyze_regression_resolution(*, history_root: Path, pf: Path) -> dict[str, Any]:
    run_record = _read_json(pf / "history" / "40_run_record.json")
    current_run_id = str(run_record.get("history_run_id", "")).strip()
    if not current_run_id:
        return {
            "lifecycle_rows": [],
            "component_metrics_rows": [],
            "resolved_rows": [],
            "unresolved_rows": [],
            "artifacts": [],
            "summary": {},
        }

    runs_root = pf.parent
    proof_rows = _collect_proof_history_rows(runs_root)

    # Ensure current run is present even if it was not discovered in sibling scan.
    if current_run_id not in proof_rows:
        detected_store = _read_json(pf / "history" / "41_regression_fingerprints_detected.json")
        detected_rows = detected_store.get("rows", []) if isinstance(detected_store.get("rows", []), list) else []
        normalized_rows = [row for row in detected_rows if isinstance(row, dict)]
        proof_rows[current_run_id] = {
            "history_run_id": current_run_id,
            "run_num": _run_num(current_run_id),
            "detected_rows": normalized_rows,
            "detected_set": {str(row.get("fingerprint", "")).strip() for row in normalized_rows if str(row.get("fingerprint", "")).strip()},
        }

    ordered_runs = sorted(proof_rows.values(), key=lambda row: (_safe_int(row.get("run_num", 0)), str(row.get("history_run_id", ""))))
    current_run_num = _run_num(current_run_id)

    previous_run = None
    for row in ordered_runs:
        run_num = _safe_int(row.get("run_num", 0))
        if run_num < current_run_num:
            previous_run = row

    current_row = proof_rows.get(current_run_id, {})
    current_detected_rows = current_row.get("detected_rows", []) if isinstance(current_row.get("detected_rows", []), list) else []
    current_detected_set = current_row.get("detected_set", set()) if isinstance(current_row.get("detected_set", set()), set) else set()
    previous_detected_set: set[str] = set()
    if isinstance(previous_run, dict):
        candidate = previous_run.get("detected_set", set())
        if isinstance(candidate, set):
            previous_detected_set = candidate

    regression_store = _read_json(history_root / "regressions" / "regression_fingerprints.json")
    fingerprint_rows = regression_store.get("rows", []) if isinstance(regression_store.get("rows", []), list) else []
    fingerprint_lookup: dict[str, dict[str, Any]] = {
        str(row.get("fingerprint", "")).strip(): row
        for row in fingerprint_rows
        if isinstance(row, dict) and str(row.get("fingerprint", "")).strip()
    }

    presence = _collect_presence_map(ordered_runs)
    latest_run_num = max([_safe_int(row.get("run_num", 0)) for row in ordered_runs] + [current_run_num])

    lifecycle_rows: list[dict[str, Any]] = []

    for detected in sorted(current_detected_rows, key=lambda row: str(row.get("fingerprint", ""))):
        fingerprint = str(detected.get("fingerprint", "")).strip()
        if not fingerprint:
            continue

        previous_occurrences = _safe_int(detected.get("previous_occurrences", 0))
        state = "NEW" if previous_occurrences == 0 else "RECURRING"

        streak_before = _consecutive_streak_before(presence.get(fingerprint, []), current_run_num)
        if previous_occurrences > 0 and streak_before >= 2:
            state = "PERSISTING"

        lookup = fingerprint_lookup.get(fingerprint, {}) if isinstance(fingerprint_lookup.get(fingerprint, {}), dict) else {}
        lifecycle_rows.append(
            {
                "fingerprint": fingerprint,
                "state": state,
                "component": str(detected.get("component", lookup.get("component", "unknown_component"))),
                "scenario_id": str(detected.get("scenario_id", lookup.get("scenario_id", ""))),
                "metric": str(detected.get("metric", lookup.get("metric", ""))),
                "severity_bucket": str(detected.get("severity_bucket", lookup.get("severity_bucket", "TRACE"))),
                "previous_occurrences": previous_occurrences,
                "current_occurrences": _safe_int(detected.get("current_occurrences", previous_occurrences + 1)),
                "history_run_id": current_run_id,
                "streak_before_current": streak_before,
            }
        )

    resolved_fingerprints = sorted(previous_detected_set - current_detected_set)
    for fingerprint in resolved_fingerprints:
        lookup = fingerprint_lookup.get(fingerprint, {}) if isinstance(fingerprint_lookup.get(fingerprint, {}), dict) else {}
        lifecycle_rows.append(
            {
                "fingerprint": fingerprint,
                "state": "RESOLVED",
                "component": str(lookup.get("component", "unknown_component")),
                "scenario_id": str(lookup.get("scenario_id", "")),
                "metric": str(lookup.get("metric", "")),
                "severity_bucket": str(lookup.get("severity_bucket", "TRACE")),
                "previous_occurrences": _safe_int(lookup.get("occurrences", 0)),
                "current_occurrences": 0,
                "history_run_id": current_run_id,
                "resolved_from_run": str((previous_run or {}).get("history_run_id", "")),
            }
        )

    lifecycle_rows = sorted(
        lifecycle_rows,
        key=lambda row: (
            str(row.get("state", "")) != "PERSISTING",
            str(row.get("state", "")) != "RECURRING",
            str(row.get("state", "")) != "NEW",
            str(row.get("state", "")) != "RESOLVED",
            str(row.get("component", "")),
            str(row.get("fingerprint", "")),
        ),
    )

    resolved_rows = [row for row in lifecycle_rows if str(row.get("state", "")) == "RESOLVED"]
    unresolved_rows = [row for row in lifecycle_rows if str(row.get("state", "")) != "RESOLVED"]

    component_store = _read_json(history_root / "components" / "component_regression_stats.json")
    component_stats = component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {}

    component_metrics_rows: list[dict[str, Any]] = []
    component_names = sorted(
        {
            *[str(row.get("component", "")).strip() for row in lifecycle_rows if str(row.get("component", "")).strip()],
            *[str(name).strip() for name in component_stats.keys() if str(name).strip()],
        }
    )

    lifecycle_by_component: dict[str, list[dict[str, Any]]] = {}
    for row in lifecycle_rows:
        component = str(row.get("component", "")).strip() or "unknown_component"
        lifecycle_by_component.setdefault(component, []).append(row)

    for component in component_names:
        rows = lifecycle_by_component.get(component, [])
        resolved_count = len([row for row in rows if str(row.get("state", "")) == "RESOLVED"])
        unresolved_count = len([row for row in rows if str(row.get("state", "")) != "RESOLVED"])

        component_fp_rows = [
            row for row in fingerprint_rows if isinstance(row, dict) and str(row.get("component", "")).strip() == component
        ]
        recurring_fingerprint_count = len([row for row in component_fp_rows if _safe_int(row.get("occurrences", 0)) > 1])
        total_known_fingerprints = max(1, len(component_fp_rows))

        resolution_streaks: list[int] = []
        for fp_row in component_fp_rows:
            fingerprint = str(fp_row.get("fingerprint", "")).strip()
            if not fingerprint:
                continue
            resolution_streaks.extend(_resolution_streak_lengths(presence.get(fingerprint, []), latest_run_num))

        mean_time_to_resolution = (
            sum(resolution_streaks) / max(1, len(resolution_streaks)) if resolution_streaks else 0.0
        )

        resolution_rate = resolved_count / max(1, resolved_count + unresolved_count)
        recurrence_rate = recurring_fingerprint_count / total_known_fingerprints

        component_metrics_rows.append(
            {
                "component": component,
                "resolution_rate": round(resolution_rate, 4),
                "mean_time_to_resolution": round(mean_time_to_resolution, 4),
                "recurrence_rate": round(recurrence_rate, 4),
                "resolved_regressions": resolved_count,
                "unresolved_regressions": unresolved_count,
                "known_fingerprints": total_known_fingerprints,
                "recurring_fingerprints": recurring_fingerprint_count,
            }
        )

    component_metrics_rows = sorted(
        component_metrics_rows,
        key=lambda row: (
            -_safe_float(row.get("recurrence_rate", 0.0)),
            _safe_float(row.get("resolution_rate", 0.0)),
            str(row.get("component", "")),
        ),
    )

    summary = {
        "history_run_id": current_run_id,
        "new_count": len([row for row in lifecycle_rows if str(row.get("state", "")) == "NEW"]),
        "recurring_count": len([row for row in lifecycle_rows if str(row.get("state", "")) == "RECURRING"]),
        "persisting_count": len([row for row in lifecycle_rows if str(row.get("state", "")) == "PERSISTING"]),
        "resolved_count": len(resolved_rows),
        "unresolved_count": len(unresolved_rows),
        "component_count": len(component_metrics_rows),
    }

    resolution_dir = pf / "resolution"
    _write_json(resolution_dir / "70_regression_lifecycle_states.json", {"rows": lifecycle_rows})
    _write_json(resolution_dir / "71_component_resolution_metrics.json", {"rows": component_metrics_rows})
    _write_json(resolution_dir / "72_resolved_regressions.json", {"rows": resolved_rows})
    _write_json(resolution_dir / "73_unresolved_regressions.json", {"rows": unresolved_rows})

    summary_lines = [
        "# Closed-Loop Resolution Summary",
        "",
        f"- history_run_id: {summary['history_run_id']}",
        f"- new_count: {summary['new_count']}",
        f"- recurring_count: {summary['recurring_count']}",
        f"- persisting_count: {summary['persisting_count']}",
        f"- resolved_count: {summary['resolved_count']}",
        f"- unresolved_count: {summary['unresolved_count']}",
        "",
        "## Repeatedly Regressing Components",
    ]
    if component_metrics_rows:
        for row in component_metrics_rows[:10]:
            summary_lines.append(
                f"- component={row.get('component', '')} recurrence_rate={row.get('recurrence_rate', 0.0)} resolution_rate={row.get('resolution_rate', 0.0)} mean_time_to_resolution={row.get('mean_time_to_resolution', 0.0)}"
            )
    else:
        summary_lines.append("- no component data")

    _write_text(resolution_dir / "74_resolution_summary.md", "\n".join(summary_lines) + "\n")

    return {
        "summary": summary,
        "lifecycle_rows": lifecycle_rows,
        "component_metrics_rows": component_metrics_rows,
        "resolved_rows": resolved_rows,
        "unresolved_rows": unresolved_rows,
        "artifacts": [
            "resolution/70_regression_lifecycle_states.json",
            "resolution/71_component_resolution_metrics.json",
            "resolution/72_resolved_regressions.json",
            "resolution/73_unresolved_regressions.json",
            "resolution/74_resolution_summary.md",
        ],
    }
