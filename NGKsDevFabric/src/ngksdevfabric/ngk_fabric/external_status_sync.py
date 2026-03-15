from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CANONICAL_EXTERNAL_STATES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "UNKNOWN"}
_ISSUE_ID_RE = re.compile(r"^TRIAGE-[A-Z0-9_\-]+$", re.IGNORECASE)
_SYNC_FILE_RE = re.compile(r"^sync_(\d{6})\.json$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _safe_lower(value: object) -> str:
    return str(value or "").strip().lower()


def _parse_issue_parts(issue_id: str) -> tuple[str, str]:
    text = str(issue_id).strip().upper()
    if not _ISSUE_ID_RE.match(text):
        return "", ""
    parts = text.split("-")
    if len(parts) < 4:
        return "", ""
    scenario = _safe_lower(parts[2])
    metric = _safe_lower("_".join(parts[3:]))
    return scenario, metric


def _default_status_sync_config() -> dict[str, Any]:
    return {
        "github": {
            "enabled": True,
            "status_snapshot_path": "fixtures/github_status_snapshot.json",
        },
        "jira": {
            "enabled": True,
            "status_snapshot_path": "fixtures/jira_status_snapshot.json",
        },
    }


def load_external_status_sync_config(*, project_root: Path) -> dict[str, Any]:
    defaults = _default_status_sync_config()
    config_path = (project_root / "external_status_sync.json").resolve()
    loaded = _read_json(config_path)

    config = {
        "config_path": str(config_path),
        "config_found": config_path.is_file(),
        "github": dict(defaults["github"]),
        "jira": dict(defaults["jira"]),
    }

    for connector in ("github", "jira"):
        incoming = loaded.get(connector, {})
        if isinstance(incoming, dict):
            config[connector].update(incoming)
        config[connector]["enabled"] = bool(config[connector].get("enabled", True))

    return config


def _snapshot_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("issues", "rows", "items"):
        rows = payload.get(key, [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_external_status(*, connector_name: str, raw_status: object) -> str:
    text = _safe_lower(raw_status)
    if not text:
        return "UNKNOWN"

    if connector_name == "github":
        if text == "open":
            return "OPEN"
        if text == "closed":
            return "CLOSED"
        return "UNKNOWN"

    if connector_name == "jira":
        mapping = {
            "to do": "OPEN",
            "todo": "OPEN",
            "open": "OPEN",
            "in progress": "IN_PROGRESS",
            "in_progress": "IN_PROGRESS",
            "doing": "IN_PROGRESS",
            "done": "RESOLVED",
            "resolved": "RESOLVED",
            "closed": "CLOSED",
        }
        return mapping.get(text, "UNKNOWN")

    return "UNKNOWN"


def _internal_lifecycle_index(pf: Path) -> dict[tuple[str, str], str]:
    lifecycle = _read_json(pf / "resolution" / "70_regression_lifecycle_states.json")
    rows = lifecycle.get("rows", []) if isinstance(lifecycle.get("rows", []), list) else []

    index: dict[tuple[str, str], str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        scenario = _safe_lower(row.get("scenario_id", ""))
        metric = _safe_lower(row.get("metric", ""))
        state = _safe_lower(row.get("state", ""))
        if not scenario or not metric:
            continue

        internal = "UNKNOWN"
        if state == "resolved":
            internal = "RESOLVED"
        elif state in {"new", "recurring", "persisting"}:
            internal = "ACTIVE"

        prev = index.get((scenario, metric), "UNKNOWN")
        if prev == "ACTIVE":
            continue
        if prev == "RESOLVED" and internal == "UNKNOWN":
            continue
        if internal == "ACTIVE":
            index[(scenario, metric)] = "ACTIVE"
        elif internal == "RESOLVED" and prev != "ACTIVE":
            index[(scenario, metric)] = "RESOLVED"
        elif (scenario, metric) not in index:
            index[(scenario, metric)] = "UNKNOWN"

    return index


def _find_external_match(
    *,
    connector_name: str,
    issue_id: str,
    external_id: str,
    external_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    target_connector = _safe_lower(connector_name)
    issue = str(issue_id).strip().upper()
    ext_id = str(external_id).strip()

    by_issue: dict[tuple[str, str], dict[str, Any]] = {}
    by_external_id: dict[tuple[str, str], dict[str, Any]] = {}
    for row in external_rows:
        connector = _safe_lower(row.get("connector_name", ""))
        if connector != target_connector:
            continue
        row_issue = str(row.get("issue_id", "")).strip().upper()
        row_external_id = str(row.get("external_id", "")).strip()
        if row_issue:
            by_issue[(connector, row_issue)] = row
        if row_external_id:
            by_external_id[(connector, row_external_id)] = row

    if issue and (target_connector, issue) in by_issue:
        return by_issue[(target_connector, issue)], "issue_id"
    if ext_id and (target_connector, ext_id) in by_external_id:
        return by_external_id[(target_connector, ext_id)], "external_id"
    return None, "none"


def _closure_state(*, external_status: str, internal_state: str, has_external_match: bool) -> str:
    if not has_external_match:
        return "NO_EXTERNAL_MATCH"
    if external_status == "UNKNOWN":
        return "UNKNOWN_EXTERNAL_STATUS"

    external_open = external_status in {"OPEN", "IN_PROGRESS"}
    external_closed = external_status in {"RESOLVED", "CLOSED"}

    if external_open and internal_state == "ACTIVE":
        return "EXTERNAL_OPEN_INTERNAL_ACTIVE"
    if external_closed and internal_state == "RESOLVED":
        return "EXTERNAL_CLOSED_INTERNAL_RESOLVED"
    if external_closed and internal_state == "ACTIVE":
        return "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH"
    if external_open and internal_state == "RESOLVED":
        return "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH"
    return "UNKNOWN_EXTERNAL_STATUS"


def _next_sync_path(project_root: Path) -> Path:
    sync_dir = (project_root / "devfabeco_delivery_history" / "status_sync").resolve()
    sync_dir.mkdir(parents=True, exist_ok=True)
    max_id = 0
    for child in sync_dir.iterdir():
        if not child.is_file():
            continue
        match = _SYNC_FILE_RE.match(child.name)
        if not match:
            continue
        max_id = max(max_id, int(match.group(1)))
    return sync_dir / f"sync_{max_id + 1:06d}.json"


def _write_delivery_history_summary(
    *,
    project_root: Path,
    sync_path: Path,
    sync_row_count: int,
    summary_counts: dict[str, int],
) -> None:
    summary_path = (project_root / "devfabeco_delivery_history" / "summary" / "delivery_history_summary.md").resolve()
    lines = [
        "# Delivery History Summary",
        "",
        f"- last_sync_file: {sync_path.name}",
        f"- last_sync_row_count: {sync_row_count}",
        f"- EXTERNAL_OPEN_INTERNAL_ACTIVE: {summary_counts.get('EXTERNAL_OPEN_INTERNAL_ACTIVE', 0)}",
        f"- EXTERNAL_CLOSED_INTERNAL_RESOLVED: {summary_counts.get('EXTERNAL_CLOSED_INTERNAL_RESOLVED', 0)}",
        f"- EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH: {summary_counts.get('EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH', 0)}",
        f"- EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH: {summary_counts.get('EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH', 0)}",
        f"- NO_EXTERNAL_MATCH: {summary_counts.get('NO_EXTERNAL_MATCH', 0)}",
        f"- UNKNOWN_EXTERNAL_STATUS: {summary_counts.get('UNKNOWN_EXTERNAL_STATUS', 0)}",
        "",
    ]
    _write_text(summary_path, "\n".join(lines))


def run_external_status_sync_and_closure_reconciliation(
    *,
    project_root: Path,
    pf: Path,
    acknowledgments: list[dict[str, Any]],
) -> dict[str, Any]:
    config = load_external_status_sync_config(project_root=project_root)
    run_timestamp = _iso_now()

    external_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    for connector_name in ("github", "jira"):
        connector_cfg = config.get(connector_name, {}) if isinstance(config.get(connector_name, {}), dict) else {}
        enabled = bool(connector_cfg.get("enabled", True))
        snapshot_rel = str(connector_cfg.get("status_snapshot_path", "")).strip()
        snapshot_path = (project_root / snapshot_rel).resolve() if snapshot_rel else Path("")

        snapshot_payload = _read_json(snapshot_path) if enabled and snapshot_rel else {}
        rows = _snapshot_rows(snapshot_payload) if enabled else []

        source_rows.append(
            {
                "connector_name": connector_name,
                "enabled": enabled,
                "snapshot_path": str(snapshot_path) if snapshot_rel else "",
                "snapshot_found": bool(snapshot_rel and snapshot_path.is_file()),
                "row_count": len(rows),
            }
        )

        for row in rows:
            issue_id = str(row.get("issue_id", "")).strip().upper()
            external_id = str(row.get("external_id", "")).strip()
            external_url = str(row.get("external_url", row.get("url", ""))).strip()
            raw_status = row.get("status", row.get("state", ""))
            normalized_status = _normalize_external_status(connector_name=connector_name, raw_status=raw_status)
            external_rows.append(
                {
                    "connector_name": connector_name,
                    "issue_id": issue_id,
                    "external_id": external_id,
                    "external_url": external_url,
                    "external_status_raw": str(raw_status),
                    "external_status_normalized": normalized_status,
                    "snapshot_path": str(snapshot_path) if snapshot_rel else "",
                }
            )

    internal_index = _internal_lifecycle_index(pf)

    latest_ack_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in acknowledgments:
        if not isinstance(row, dict):
            continue
        connector = _safe_lower(row.get("connector_name", ""))
        issue_id = str(row.get("issue_id", "")).strip().upper()
        rec_key = str(row.get("reconciliation_key", "")).strip()
        if not connector:
            continue
        latest_ack_by_key[(connector, issue_id, rec_key)] = row

    closure_rows: list[dict[str, Any]] = []
    for (_connector, _issue, _rec_key), ack in sorted(latest_ack_by_key.items(), key=lambda item: item[0]):
        connector_name = str(ack.get("connector_name", "")).strip()
        issue_id = str(ack.get("issue_id", "")).strip().upper()
        external_id = str(ack.get("external_id", "")).strip()
        external_url = str(ack.get("external_url", "")).strip()
        rec_key = str(ack.get("reconciliation_key", "")).strip()

        scenario_id, metric = _parse_issue_parts(issue_id)
        internal_state = internal_index.get((scenario_id, metric), "UNKNOWN")

        match, match_strategy = _find_external_match(
            connector_name=connector_name,
            issue_id=issue_id,
            external_id=external_id,
            external_rows=external_rows,
        )

        has_match = match is not None
        external_status_raw = str(match.get("external_status_raw", "")) if isinstance(match, dict) else ""
        external_status = str(match.get("external_status_normalized", "UNKNOWN")) if isinstance(match, dict) else "UNKNOWN"
        if external_status not in _CANONICAL_EXTERNAL_STATES:
            external_status = "UNKNOWN"

        resolved_external_id = external_id
        resolved_external_url = external_url
        if isinstance(match, dict):
            match_external_id = str(match.get("external_id", "")).strip()
            match_external_url = str(match.get("external_url", "")).strip()
            if match_external_id:
                resolved_external_id = match_external_id
            if match_external_url:
                resolved_external_url = match_external_url

        closure_state = _closure_state(
            external_status=external_status,
            internal_state=internal_state,
            has_external_match=has_match,
        )

        closure_rows.append(
            {
                "connector_name": connector_name,
                "issue_id": issue_id,
                "reconciliation_key": rec_key,
                "external_id": resolved_external_id,
                "external_url": resolved_external_url,
                "external_status_raw": external_status_raw,
                "external_status_normalized": external_status,
                "internal_regression_state": internal_state,
                "closure_reconciliation_state": closure_state,
                "match_strategy": match_strategy,
                "timestamp": run_timestamp,
            }
        )

    summary_counts: dict[str, int] = {
        "EXTERNAL_OPEN_INTERNAL_ACTIVE": 0,
        "EXTERNAL_CLOSED_INTERNAL_RESOLVED": 0,
        "EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH": 0,
        "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH": 0,
        "NO_EXTERNAL_MATCH": 0,
        "UNKNOWN_EXTERNAL_STATUS": 0,
    }
    open_external = 0
    closed_external = 0
    mismatch_count = 0
    for row in closure_rows:
        state = str(row.get("closure_reconciliation_state", "UNKNOWN_EXTERNAL_STATUS"))
        summary_counts[state] = int(summary_counts.get(state, 0)) + 1
        normalized = str(row.get("external_status_normalized", "UNKNOWN"))
        if normalized in {"OPEN", "IN_PROGRESS"}:
            open_external += 1
        elif normalized in {"RESOLVED", "CLOSED"}:
            closed_external += 1
        if state in {"EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH", "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH"}:
            mismatch_count += 1

    out_dir = pf / "transport"
    _write_json(
        out_dir / "98_external_status_sync.json",
        {
            "timestamp": run_timestamp,
            "config_path": str(config.get("config_path", "")),
            "config_found": bool(config.get("config_found", False)),
            "sources": source_rows,
            "rows": external_rows,
        },
    )
    _write_json(
        out_dir / "99_status_normalization.json",
        {
            "timestamp": run_timestamp,
            "rows": [
                {
                    "connector_name": row.get("connector_name", ""),
                    "issue_id": row.get("issue_id", ""),
                    "external_id": row.get("external_id", ""),
                    "external_status_raw": row.get("external_status_raw", ""),
                    "external_status_normalized": row.get("external_status_normalized", "UNKNOWN"),
                }
                for row in external_rows
            ],
        },
    )
    _write_json(out_dir / "100_closure_reconciliation.json", {"rows": closure_rows})
    _write_json(
        out_dir / "101_external_issue_state_summary.json",
        {
            "timestamp": run_timestamp,
            "tracked_issue_count": len(closure_rows),
            "open_external_issue_count": open_external,
            "closed_external_issue_count": closed_external,
            "mismatch_count": mismatch_count,
            "state_counts": summary_counts,
        },
    )

    summary_lines = [
        "# External Issue State Summary",
        "",
        f"- tracked_issue_count: {len(closure_rows)}",
        f"- open_external_issue_count: {open_external}",
        f"- closed_external_issue_count: {closed_external}",
        f"- mismatch_count: {mismatch_count}",
        "",
        "## Closure Reconciliation State Counts",
        f"- EXTERNAL_OPEN_INTERNAL_ACTIVE: {summary_counts.get('EXTERNAL_OPEN_INTERNAL_ACTIVE', 0)}",
        f"- EXTERNAL_CLOSED_INTERNAL_RESOLVED: {summary_counts.get('EXTERNAL_CLOSED_INTERNAL_RESOLVED', 0)}",
        f"- EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH: {summary_counts.get('EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH', 0)}",
        f"- EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH: {summary_counts.get('EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH', 0)}",
        f"- NO_EXTERNAL_MATCH: {summary_counts.get('NO_EXTERNAL_MATCH', 0)}",
        f"- UNKNOWN_EXTERNAL_STATUS: {summary_counts.get('UNKNOWN_EXTERNAL_STATUS', 0)}",
        "",
        "## Mismatch Review Candidates",
    ]
    mismatch_rows = [
        row
        for row in closure_rows
        if str(row.get("closure_reconciliation_state", ""))
        in {"EXTERNAL_CLOSED_INTERNAL_ACTIVE_MISMATCH", "EXTERNAL_OPEN_INTERNAL_RESOLVED_MISMATCH"}
    ]
    if mismatch_rows:
        for row in mismatch_rows[:20]:
            summary_lines.append(
                "- connector="
                + str(row.get("connector_name", ""))
                + " issue_id="
                + str(row.get("issue_id", ""))
                + " state="
                + str(row.get("closure_reconciliation_state", ""))
                + " external_status="
                + str(row.get("external_status_normalized", "UNKNOWN"))
                + " internal_state="
                + str(row.get("internal_regression_state", "UNKNOWN"))
            )
    else:
        summary_lines.append("- none")

    _write_text(out_dir / "102_closure_reconciliation_summary.md", "\n".join(summary_lines) + "\n")

    sync_path = _next_sync_path(project_root)
    _write_json(
        sync_path,
        {
            "timestamp": run_timestamp,
            "pf": str(pf.resolve()),
            "rows": closure_rows,
            "summary": {
                "tracked_issue_count": len(closure_rows),
                "open_external_issue_count": open_external,
                "closed_external_issue_count": closed_external,
                "mismatch_count": mismatch_count,
                "state_counts": summary_counts,
            },
        },
    )
    _write_delivery_history_summary(
        project_root=project_root,
        sync_path=sync_path,
        sync_row_count=len(closure_rows),
        summary_counts=summary_counts,
    )

    return {
        "summary": {
            "tracked_issue_count": len(closure_rows),
            "open_external_issue_count": open_external,
            "closed_external_issue_count": closed_external,
            "mismatch_count": mismatch_count,
            "state_counts": summary_counts,
            "status_sync_file": str(sync_path),
        },
        "artifacts": [
            "transport/98_external_status_sync.json",
            "transport/99_status_normalization.json",
            "transport/100_closure_reconciliation.json",
            "transport/101_external_issue_state_summary.json",
            "transport/102_closure_reconciliation_summary.md",
        ],
    }
