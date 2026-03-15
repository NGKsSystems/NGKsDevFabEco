from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RUN_FILE_RE = re.compile(r"^run_(\d{6})\.json$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _next_run_id(runs_dir: Path) -> str:
    runs_dir.mkdir(parents=True, exist_ok=True)
    max_id = 0
    for child in runs_dir.iterdir():
        if not child.is_file():
            continue
        m = _RUN_FILE_RE.match(child.name)
        if not m:
            continue
        max_id = max(max_id, int(m.group(1)))
    return f"run_{max_id + 1:06d}"


def _severity_bucket(score: float) -> str:
    if score >= 0.15:
        return "HIGH"
    if score >= 0.10:
        return "MEDIUM"
    if score >= 0.05:
        return "LOW"
    return "TRACE"


def _fingerprint_key(payload: dict[str, Any]) -> str:
    return "|".join(
        [
            str(payload.get("scenario_id", "")),
            str(payload.get("metric", "")),
            str(payload.get("component", "")),
            str(payload.get("severity_bucket", "")),
        ]
    )


def _extract_fingerprints_from_root(root: Path) -> list[dict[str, Any]]:
    triage_path = root / "hotspots" / "22_triage_tickets.json"
    triage = _read_json(triage_path)
    tickets = triage.get("tickets", []) if isinstance(triage.get("tickets", []), list) else []

    fingerprints: list[dict[str, Any]] = []
    for row in tickets:
        if not isinstance(row, dict):
            continue
        scenario_id = str(row.get("scenario_id", "")).strip()
        metric = str(row.get("metric", "")).strip()
        component = str(row.get("likely_component", "")).strip() or "unknown_component"
        severity_score = float(row.get("severity_score", 0.0) or 0.0)
        if not scenario_id or not metric:
            continue

        fp = {
            "scenario_id": scenario_id,
            "metric": metric,
            "component": component,
            "severity_bucket": _severity_bucket(severity_score),
        }
        fp["fingerprint"] = _fingerprint_key(fp)
        fp["severity_score"] = round(severity_score, 6)
        fingerprints.append(fp)

    return fingerprints


def _collect_detected_fingerprints(roots: list[Path]) -> list[dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for root in sorted(roots, key=lambda p: str(p)):
        for fp in _extract_fingerprints_from_root(root):
            key = str(fp.get("fingerprint", ""))
            if key and key not in collected:
                collected[key] = fp
    return [collected[key] for key in sorted(collected.keys())]


def record_regression_history(
    *,
    history_root: Path,
    pf: Path,
    run_id: str,
    project_name: str,
    execution_profile: str,
    certification_decision: str,
    gate_result: str,
    subtarget_count: int,
    fingerprint_source_roots: list[Path] | None = None,
) -> dict[str, Any]:
    source_roots = fingerprint_source_roots or [pf]
    history_runs = history_root / "runs"
    history_regressions = history_root / "regressions"
    history_components = history_root / "components"
    history_summary = history_root / "summary"

    history_runs.mkdir(parents=True, exist_ok=True)
    history_regressions.mkdir(parents=True, exist_ok=True)
    history_components.mkdir(parents=True, exist_ok=True)
    history_summary.mkdir(parents=True, exist_ok=True)

    history_run_id = _next_run_id(history_runs)
    detected = _collect_detected_fingerprints(source_roots)

    index_path = history_regressions / "regression_index.json"
    fingerprint_path = history_regressions / "regression_fingerprints.json"
    component_path = history_components / "component_regression_stats.json"

    regression_index = _read_json(index_path)
    regression_rows = regression_index.get("fingerprints", {}) if isinstance(regression_index.get("fingerprints", {}), dict) else {}

    fingerprint_store = _read_json(fingerprint_path)
    fingerprint_rows = fingerprint_store.get("rows", []) if isinstance(fingerprint_store.get("rows", []), list) else []

    component_store = _read_json(component_path)
    component_rows = component_store.get("components", {}) if isinstance(component_store.get("components", {}), dict) else {}

    recurrence_matches: list[dict[str, Any]] = []
    detected_rows: list[dict[str, Any]] = []

    for fp in detected:
        key = str(fp.get("fingerprint", ""))
        if not key:
            continue

        prev = regression_rows.get(key, {}) if isinstance(regression_rows.get(key, {}), dict) else {}
        prev_count = int(prev.get("occurrences", 0) or 0)
        next_count = prev_count + 1

        if prev_count > 0:
            recurrence_matches.append(
                {
                    "fingerprint": key,
                    "occurrences": next_count,
                    "last_seen_run": history_run_id,
                }
            )

        regression_rows[key] = {
            "fingerprint": key,
            "scenario_id": fp.get("scenario_id", ""),
            "metric": fp.get("metric", ""),
            "component": fp.get("component", ""),
            "severity_bucket": fp.get("severity_bucket", ""),
            "occurrences": next_count,
            "first_seen_run": str(prev.get("first_seen_run", history_run_id)),
            "last_seen_run": history_run_id,
        }

        detected_rows.append(
            {
                "fingerprint": key,
                "scenario_id": fp.get("scenario_id", ""),
                "metric": fp.get("metric", ""),
                "component": fp.get("component", ""),
                "severity_bucket": fp.get("severity_bucket", ""),
                "severity_score": fp.get("severity_score", 0.0),
                "previous_occurrences": prev_count,
                "current_occurrences": next_count,
            }
        )

    # Rebuild fingerprint catalog deterministically from index for append-only history semantics.
    fingerprint_rows_by_key = {str(item.get("fingerprint", "")): item for item in fingerprint_rows if isinstance(item, dict)}
    for key, row in regression_rows.items():
        fingerprint_rows_by_key[key] = {
            "fingerprint": key,
            "scenario_id": row.get("scenario_id", ""),
            "metric": row.get("metric", ""),
            "component": row.get("component", ""),
            "severity_bucket": row.get("severity_bucket", ""),
            "occurrences": row.get("occurrences", 0),
            "first_seen_run": row.get("first_seen_run", ""),
            "last_seen_run": row.get("last_seen_run", ""),
        }

    for row in detected_rows:
        component = str(row.get("component", "")).strip() or "unknown_component"
        current = component_rows.get(component, {}) if isinstance(component_rows.get(component, {}), dict) else {}
        component_rows[component] = {
            "component": component,
            "total_regression_occurrences": int(current.get("total_regression_occurrences", 0) or 0) + 1,
            "unique_fingerprints": int(current.get("unique_fingerprints", 0) or 0),
            "last_seen_run": history_run_id,
        }

    # Recompute deterministic unique fingerprint counts per component.
    component_to_keys: dict[str, set[str]] = {}
    for key, row in regression_rows.items():
        component = str(row.get("component", "")).strip() or "unknown_component"
        component_to_keys.setdefault(component, set()).add(key)
    for component, keys in component_to_keys.items():
        current = component_rows.get(component, {}) if isinstance(component_rows.get(component, {}), dict) else {}
        current["component"] = component
        current["unique_fingerprints"] = len(keys)
        current.setdefault("total_regression_occurrences", 0)
        current.setdefault("last_seen_run", history_run_id)
        component_rows[component] = current

    run_record = {
        "history_run_id": history_run_id,
        "run_id": run_id,
        "timestamp": _iso_now(),
        "project_name": project_name,
        "execution_profile": execution_profile,
        "certification_decision": certification_decision,
        "gate_result": gate_result,
        "subtarget_count": int(subtarget_count),
        "regression_count": len(detected_rows),
    }

    _write_json(history_runs / f"{history_run_id}.json", run_record)
    _write_json(index_path, {"fingerprints": dict(sorted(regression_rows.items()))})
    _write_json(
        fingerprint_path,
        {
            "rows": [fingerprint_rows_by_key[key] for key in sorted(fingerprint_rows_by_key.keys())],
        },
    )
    _write_json(
        component_path,
        {
            "components": {key: component_rows[key] for key in sorted(component_rows.keys())},
        },
    )

    summary_lines = [
        "# DevFabEco History Summary",
        "",
        f"- latest_history_run_id: {history_run_id}",
        f"- total_history_runs: {len(list(history_runs.glob('run_*.json')))}",
        f"- total_known_fingerprints: {len(regression_rows)}",
        f"- latest_regression_count: {len(detected_rows)}",
        f"- recurrence_matches_in_latest_run: {len(recurrence_matches)}",
        "",
    ]
    _write_text(history_summary / "history_summary.md", "\n".join(summary_lines))

    history_out = pf / "history"
    _write_json(history_out / "40_run_record.json", run_record)
    _write_json(history_out / "41_regression_fingerprints_detected.json", {"rows": detected_rows})
    _write_json(history_out / "42_recurrence_matches.json", {"rows": recurrence_matches})

    current_components = sorted({str(row.get("component", "")) for row in detected_rows if str(row.get("component", ""))})
    component_context_rows = [component_rows.get(name, {}) for name in current_components]
    _write_json(history_out / "43_component_history_context.json", {"rows": component_context_rows})

    history_summary_lines = [
        "# Historical Regression Summary",
        "",
        f"- history_run_id: {history_run_id}",
        f"- project_name: {project_name}",
        f"- execution_profile: {execution_profile}",
        f"- certification_decision: {certification_decision}",
        f"- gate_result: {gate_result}",
        f"- regression_count: {len(detected_rows)}",
        f"- recurrence_matches: {len(recurrence_matches)}",
        "",
    ]
    _write_text(history_out / "44_history_summary.md", "\n".join(history_summary_lines))

    return {
        "history_run_id": history_run_id,
        "run_record": run_record,
        "detected_fingerprints": detected_rows,
        "recurrence_matches": recurrence_matches,
        "component_context": component_context_rows,
        "history_root": str(history_root.resolve()),
        "artifacts": [
            "history/40_run_record.json",
            "history/41_regression_fingerprints_detected.json",
            "history/42_recurrence_matches.json",
            "history/43_component_history_context.json",
            "history/44_history_summary.md",
        ],
    }
