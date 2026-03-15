from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ISSUE_ID_RE = re.compile(r"TRIAGE-[A-Z0-9_\-]+", re.IGNORECASE)


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


def _extract_issue_id(*, target: str, payload: dict[str, Any]) -> str:
    if target == "webhook":
        body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
        issues = body.get("issues", []) if isinstance(body.get("issues", []), list) else []
        first = issues[0] if issues and isinstance(issues[0], dict) else {}
        candidate = str(first.get("issue_id", "")).strip()
        if candidate:
            return candidate

    if target == "email":
        body_text = str(payload.get("body_text", ""))
        subject = str(payload.get("subject", ""))
        match = _ISSUE_ID_RE.search(body_text) or _ISSUE_ID_RE.search(subject)
        return match.group(0).upper() if match else ""

    body = payload.get("body", {}) if isinstance(payload.get("body", {}), dict) else {}
    candidate_fields = [
        str(body.get("title", "")),
        str(body.get("body", "")),
    ]
    for text in candidate_fields:
        match = _ISSUE_ID_RE.search(text)
        if match:
            return match.group(0).upper()
    return ""


def _parse_issue_parts(issue_id: str) -> tuple[str, str]:
    text = str(issue_id).strip()
    if not text:
        return "", ""
    parts = text.split("-")
    if len(parts) < 4:
        return "", ""
    scenario = _safe_lower(parts[2])
    metric = _safe_lower("_".join(parts[3:]))
    return scenario, metric


def _issue_feed_index(pf: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(pf / "hotspots" / "27_issue_feed.json")
    rows = payload.get("issues", []) if isinstance(payload.get("issues", []), list) else []

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        issue_id = str(row.get("issue_id", "")).strip().upper()
        if not issue_id:
            continue
        index[issue_id] = row
    return index


def _reconciliation_key(issue_id: str, owner_component: str) -> str:
    scenario, metric = _parse_issue_parts(issue_id)
    return "|".join([scenario or "unknown_scenario", metric or "unknown_metric", _safe_lower(owner_component) or "unknown_component"])


def _history_store_path(project_root: Path) -> Path:
    return (project_root / "devfabeco_delivery_history" / "acknowledgment_index.json").resolve()


def load_acknowledgment_history(*, project_root: Path) -> list[dict[str, Any]]:
    store = _read_json(_history_store_path(project_root))
    rows = store.get("rows", []) if isinstance(store.get("rows", []), list) else []
    return [row for row in rows if isinstance(row, dict)]


def append_acknowledgments_history(*, project_root: Path, acknowledgments: list[dict[str, Any]]) -> None:
    existing = load_acknowledgment_history(project_root=project_root)
    merged = [*existing, *[row for row in acknowledgments if isinstance(row, dict)]]
    _write_json(
        _history_store_path(project_root),
        {
            "updated_at": _iso_now(),
            "row_count": len(merged),
            "rows": merged,
        },
    )


def find_reconciliation_match(
    *,
    history_rows: list[dict[str, Any]],
    connector_name: str,
    reconciliation_key: str,
) -> dict[str, Any] | None:
    connector = _safe_lower(connector_name)
    key = _safe_lower(reconciliation_key)
    candidates: list[dict[str, Any]] = []
    for row in history_rows:
        if not isinstance(row, dict):
            continue
        if _safe_lower(row.get("connector_name", "")) != connector:
            continue
        if _safe_lower(row.get("reconciliation_key", "")) != key:
            continue
        status = _safe_lower(row.get("transport_status", ""))
        if status in {"delivered", "reconciliation_hit"}:
            candidates.append(row)
    if not candidates:
        return None
    return candidates[-1]


def build_acknowledgment_record(
    *,
    delivery_target: str,
    issue_id: str,
    connector_name: str,
    mode: str,
    transport_status: str,
    external_id: str,
    external_url: str,
    request_identifier: str,
    reconciliation_key: str,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "delivery_target": str(delivery_target),
        "issue_id": str(issue_id),
        "connector_name": str(connector_name),
        "mode": str(mode),
        "transport_status": str(transport_status),
        "external_id": str(external_id),
        "external_url": str(external_url),
        "request_identifier": str(request_identifier),
        "timestamp": str(timestamp),
        "reconciliation_key": str(reconciliation_key),
    }


def extract_issue_context(*, pf: Path, target: str, payload: dict[str, Any]) -> dict[str, str]:
    issue_id = _extract_issue_id(target=target, payload=payload).upper()
    feed_index = _issue_feed_index(pf)
    feed_row = feed_index.get(issue_id, {}) if issue_id else {}
    owner_component = str(feed_row.get("owner", "")).strip()
    if not owner_component:
        owner_component = str(payload.get("likely_component", "")).strip()
    key = _reconciliation_key(issue_id, owner_component)
    return {
        "issue_id": issue_id,
        "owner_component": owner_component,
        "reconciliation_key": key,
    }


def write_reconciliation_artifacts(
    *,
    pf: Path,
    acknowledgments: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> list[str]:
    out_dir = pf / "transport"
    _write_json(out_dir / "94_delivery_acknowledgments.json", {"rows": acknowledgments})
    _write_json(out_dir / "95_reconciliation_matches.json", {"rows": matches})
    _write_json(out_dir / "96_reconciliation_decisions.json", {"rows": decisions})

    lines = [
        "# Delivery Reconciliation Summary",
        "",
        f"- acknowledgment_count: {len(acknowledgments)}",
        f"- reconciliation_match_count: {len(matches)}",
        f"- decision_count: {len(decisions)}",
        "",
        "## Decisions",
    ]
    if decisions:
        for row in decisions[:20]:
            if not isinstance(row, dict):
                continue
            lines.append(
                "- connector="
                + str(row.get("connector_name", ""))
                + " issue_id="
                + str(row.get("issue_id", ""))
                + " decision="
                + str(row.get("decision", ""))
                + " request_identifier="
                + str(row.get("request_identifier", ""))
            )
    else:
        lines.append("- no reconciliation decisions")

    _write_text(out_dir / "97_reconciliation_summary.md", "\n".join(lines) + "\n")

    return [
        "transport/94_delivery_acknowledgments.json",
        "transport/95_reconciliation_matches.json",
        "transport/96_reconciliation_decisions.json",
        "transport/97_reconciliation_summary.md",
    ]
