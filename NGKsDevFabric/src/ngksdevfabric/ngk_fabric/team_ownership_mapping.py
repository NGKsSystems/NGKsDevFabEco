from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def _component_slug(value: str) -> str:
    text = str(value).strip().lower()
    if not text:
        return "unknown_component"
    chars = [ch if ch.isalnum() else "_" for ch in text]
    compact = "".join(chars)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_") or "unknown_component"


def _infer_team(component: str) -> str:
    slug = _component_slug(component)
    if "dependency" in slug or "resolver" in slug:
        return "core_infrastructure"
    if "diagnostic" in slug or "scoring" in slug:
        return "diagnostics_engineering"
    if "ownership" in slug or "assignment" in slug or "triage" in slug:
        return "reliability_operations"
    return "unmapped_team"


def _inferred_assignment(component: str) -> dict[str, str]:
    slug = _component_slug(component)
    return {
        "team": _infer_team(component),
        "primary_assignee": "",
        "fallback_assignee": "",
        "escalation_owner": "engineering_lead",
        "ownership_inference_assignee": "owner_" + slug,
    }


def _load_team_map(project_root: Path) -> dict[str, dict[str, str]]:
    config_path = (project_root / "ownership" / "team_map.json").resolve()
    payload = _read_json(config_path)

    rows: dict[str, dict[str, str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
            continue
        rows[key.strip()] = {
            "team": str(value.get("team", "")).strip(),
            "primary_assignee": str(value.get("primary_assignee", "")).strip(),
            "fallback_assignee": str(value.get("fallback_assignee", "")).strip(),
            "escalation_owner": str(value.get("escalation_owner", "")).strip(),
        }
    return rows


def apply_team_ownership_mapping(
    *,
    project_root: Path,
    pf: Path,
    classification: str,
    ownership_confidence: dict[str, Any],
) -> dict[str, Any]:
    team_map = _load_team_map(project_root)

    entries = ownership_confidence.get("entries", []) if isinstance(ownership_confidence.get("entries", []), list) else []
    mapped_entries: list[dict[str, Any]] = []
    confidence_adjustments: list[dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        component = str(entry.get("likely_component", "")).strip() or "unknown_component"
        mapped = team_map.get(component, {}) if isinstance(team_map.get(component, {}), dict) else {}
        inferred = _inferred_assignment(component)

        team = str(mapped.get("team", "")).strip() or inferred["team"]
        primary_assignee = str(mapped.get("primary_assignee", "")).strip()
        fallback_assignee = str(mapped.get("fallback_assignee", "")).strip()
        escalation_owner = str(mapped.get("escalation_owner", "")).strip() or inferred["escalation_owner"]

        base_confidence = _safe_float(entry.get("confidence_score", 0.0))
        mapping_bonus = 0.03 if component in team_map else 0.0
        mapped_confidence = max(0.0, min(1.0, base_confidence + mapping_bonus))

        mapping_source = "configured" if component in team_map else "inferred"
        ownership_inference_assignee = inferred["ownership_inference_assignee"]

        mapped_entry = dict(entry)
        mapped_entry["team"] = team
        mapped_entry["primary_assignee"] = primary_assignee
        mapped_entry["fallback_assignee"] = fallback_assignee
        mapped_entry["escalation_owner"] = escalation_owner
        mapped_entry["ownership_inference_assignee"] = ownership_inference_assignee
        mapped_entry["mapping_source"] = mapping_source
        mapped_entry["mapped_confidence_score"] = round(mapped_confidence, 6)
        mapped_entries.append(mapped_entry)

        confidence_adjustments.append(
            {
                "scenario_id": str(entry.get("scenario_id", "")),
                "metric": str(entry.get("metric", "")),
                "likely_component": component,
                "confidence_score": round(base_confidence, 6),
                "mapping_bonus": round(mapping_bonus, 6),
                "mapped_confidence_score": round(mapped_confidence, 6),
                "mapping_source": mapping_source,
            }
        )

    mapped_entries = sorted(
        mapped_entries,
        key=lambda item: (
            int(item.get("priority_rank", 999999)),
            -_safe_float(item.get("confidence_score", 0.0)),
            str(item.get("scenario_id", "")),
        ),
    )

    team_rows = [
        {
            "component": str(item.get("likely_component", "")),
            "team": str(item.get("team", "")),
            "primary_assignee": str(item.get("primary_assignee", "")),
            "fallback_assignee": str(item.get("fallback_assignee", "")),
            "escalation_owner": str(item.get("escalation_owner", "")),
            "mapping_source": str(item.get("mapping_source", "")),
        }
        for item in mapped_entries
    ]

    summary = {
        "classification": classification,
        "entry_count": len(mapped_entries),
        "configured_component_count": sum(1 for item in mapped_entries if str(item.get("mapping_source", "")) == "configured"),
        "inferred_component_count": sum(1 for item in mapped_entries if str(item.get("mapping_source", "")) == "inferred"),
        "team_map_size": len(team_map),
        "team_map_path": str((project_root / "ownership" / "team_map.json").resolve()),
    }

    out_dir = pf / "ownership"
    _write_json(out_dir / "80_component_team_mapping.json", {"summary": summary, "rows": team_rows})
    _write_json(out_dir / "81_assignee_resolution_results.json", {"rows": mapped_entries})
    _write_json(out_dir / "82_assignment_confidence_adjustments.json", {"rows": confidence_adjustments})

    lines = [
        "# Team Assignment Summary",
        "",
        f"- classification: {classification}",
        f"- entry_count: {len(mapped_entries)}",
        f"- configured_component_count: {summary['configured_component_count']}",
        f"- inferred_component_count: {summary['inferred_component_count']}",
        "",
        "## Component Team Mapping",
    ]
    if team_rows:
        for row in team_rows[:20]:
            lines.append(
                "- component="
                + str(row.get("component", ""))
                + " team="
                + str(row.get("team", ""))
                + " primary_assignee="
                + str(row.get("primary_assignee", ""))
                + " fallback_assignee="
                + str(row.get("fallback_assignee", ""))
                + " escalation_owner="
                + str(row.get("escalation_owner", ""))
            )
    else:
        lines.append("- no ownership entries")

    _write_text(out_dir / "83_team_assignment_summary.md", "\n".join(lines) + "\n")

    return {
        "summary": summary,
        "entries": mapped_entries,
        "artifacts": [
            "ownership/80_component_team_mapping.json",
            "ownership/81_assignee_resolution_results.json",
            "ownership/82_assignment_confidence_adjustments.json",
            "ownership/83_team_assignment_summary.md",
        ],
    }
