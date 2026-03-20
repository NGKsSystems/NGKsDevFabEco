from __future__ import annotations

"""release_gate.py — Release gate wrapper around certify-baseline.

Runs the full certify-baseline check and emits a compact machine-readable
release_gate_verdict.json artifact.

Exit semantics (reflected in the returned exit_code field):
    0  PASS  — no regressions, release may proceed
    1  FAIL  — regression detected, release BLOCKED
    2  ERROR — misconfiguration or missing baseline
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certify_baseline import _read_manifest, find_baseline_manifest, run_certify_baseline


def run_release_gate(
    *,
    eco_root: Path | None,
    baseline_arg: str,
    strict: bool,
    no_build: bool,
    build_mode: str,
    pf: Path,
) -> dict[str, Any]:
    """Run the release gate and return a result dict.

    Keys in the returned dict:
        gate         : "PASS" | "FAIL" | "ERROR"
        exit_code    : 0 | 1 | 2
        error        : str | None
        verdict      : dict — the payload written to release_gate_verdict.json
        verdict_path : Path | None
    """
    # ------------------------------------------------------------------
    # 1. Locate baseline manifest
    # ------------------------------------------------------------------
    try:
        manifest_path = find_baseline_manifest(baseline_arg, eco_root)
    except RuntimeError as exc:
        return {
            "gate": "ERROR",
            "exit_code": 2,
            "error": str(exc),
            "verdict": {},
            "verdict_path": None,
        }

    # ------------------------------------------------------------------
    # 2. Read manifest for tier metadata
    # ------------------------------------------------------------------
    try:
        manifest = _read_manifest(manifest_path)
    except RuntimeError as exc:
        return {
            "gate": "ERROR",
            "exit_code": 2,
            "error": str(exc),
            "verdict": {},
            "verdict_path": None,
        }

    baseline_name = str(manifest.get("baseline_name", "UNKNOWN"))
    certified_repos: list[dict] = manifest.get("certified_repos", [])
    tier_1_count = sum(1 for r in certified_repos if str(r.get("tier", "")) == "TIER_1")
    tier_2_count = sum(1 for r in certified_repos if str(r.get("tier", "")) == "TIER_2")

    # ------------------------------------------------------------------
    # 3. Capture git HEAD
    # ------------------------------------------------------------------
    search_root = eco_root or Path.cwd()
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(search_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        git_head = "UNKNOWN"

    # ------------------------------------------------------------------
    # 4. Run certify-baseline
    # ------------------------------------------------------------------
    pf.mkdir(parents=True, exist_ok=True)
    try:
        certify_result = run_certify_baseline(
            manifest_path=manifest_path,
            repo_filter=None,
            build_mode=build_mode,
            strict=strict,
            no_build=no_build,
            pf=pf,
        )
    except RuntimeError as exc:
        return {
            "gate": "ERROR",
            "exit_code": 2,
            "error": str(exc),
            "verdict": {},
            "verdict_path": None,
        }

    # ------------------------------------------------------------------
    # 5. Build verdict payload
    # ------------------------------------------------------------------
    gate = str(certify_result.get("gate", "FAIL"))
    regression_count = int(certify_result.get("repos_regression", 0))
    run_id = str(certify_result.get("run_id", "release_gate"))
    timestamp = datetime.now(timezone.utc).isoformat()

    verdict: dict[str, Any] = {
        "verdict": gate,
        "baseline_name": baseline_name,
        "baseline_path": str(manifest_path),
        "git_head": git_head,
        "timestamp": timestamp,
        "strict": strict,
        "no_build": no_build,
        "build_mode": build_mode,
        "repos_checked": int(certify_result.get("repos_checked", 0)),
        "repos_pass": int(certify_result.get("repos_pass", 0)),
        "regression_count": regression_count,
        "improvement_count": int(certify_result.get("repos_improvement", 0)),
        "tier_1_count": tier_1_count,
        "tier_2_count": tier_2_count,
        "certify_baseline_run_id": run_id,
    }

    # ------------------------------------------------------------------
    # 6. Write verdict artifact
    # ------------------------------------------------------------------
    verdict_dir = pf / run_id
    verdict_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = verdict_dir / "release_gate_verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    exit_code = 0 if gate == "PASS" else 1

    return {
        "gate": gate,
        "exit_code": exit_code,
        "error": None,
        "verdict": verdict,
        "verdict_path": verdict_path,
    }
