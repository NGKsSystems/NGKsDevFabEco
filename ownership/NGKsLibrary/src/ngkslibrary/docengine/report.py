from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .proof_context import ProofContext


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_kv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def render_report(
    *,
    context: ProofContext,
    build_system: str,
    build_action: str,
    build_reason: str,
    exit_code: int,
) -> tuple[Path, Path]:
    context.stage_pf.mkdir(parents=True, exist_ok=True)
    run_summary = _read_kv(context.run_pf / "99_summary.txt")

    payload: dict[str, Any] = {
        "schema": "ngks.proof.report.v1",
        "generated_utc": _utc_now(),
        "proof_context": context.as_dict(),
        "run_id": context.run_id,
        "build_system": build_system,
        "build_action": build_action,
        "build_reason": build_reason,
        "exit_code": int(exit_code),
        "noop": build_action == "skipped" and build_reason == "no_build_inputs",
        "proof_locations": {
            "run_pf": str(context.run_pf),
            "envcapsule": str(context.run_pf / "10_envcapsule"),
            "graph": str(context.run_pf / "20_graph"),
            "buildcore": str(context.run_pf / "30_buildcore"),
            "library": str(context.stage_pf),
        },
        "run_summary": run_summary,
    }

    report_json = context.stage_pf / "REPORT.json"
    report_md = context.stage_pf / "REPORT.md"

    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "<!-- markdownlint-disable MD013 MD024 -->",
        "# Ecosystem Run Report",
        "",
        f"- run_id: {context.run_id}",
        f"- exit_code: {int(exit_code)}",
        f"- detected_build_system: {build_system}",
        f"- build_action: {build_action}",
        f"- build_reason: {build_reason}",
        "",
        "## Status",
        "- nothing to build" if payload["noop"] else "- build processing completed",
        "",
        "## Proof locations",
        f"- run_pf: {context.run_pf}",
        f"- 10_envcapsule: {context.run_pf / '10_envcapsule'}",
        f"- 20_graph: {context.run_pf / '20_graph'}",
        f"- 30_buildcore: {context.run_pf / '30_buildcore'}",
        f"- 40_library: {context.stage_pf}",
    ]
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_md, report_json
