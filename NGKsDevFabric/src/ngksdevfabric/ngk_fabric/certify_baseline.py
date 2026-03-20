from __future__ import annotations

"""certify_baseline.py
---------------------
Enforced gate that re-runs probe/doctor/configure/build across all repos
in a Certification_Baseline_v1 manifest and detects regressions.

Classification:
  PASS        - all stages are identical to or improved over baseline
  REGRESSION  - any stage that was PASS is now FAIL
  IMPROVEMENT - a stage that was FAIL is now PASS (no regressions present)

Strict mode (--strict):
  Additionally fails when a probe/doctor step exits non-zero on a repo
  whose baseline value was PASS.  This catches warning-level drift that
  would otherwise be tolerated.

Exit code contract (CI-safe):
  0  PASS
  1  REGRESSION detected
  2  Command error / manifest unreadable
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_NA = "N/A"
_PASS = "PASS"
_FAIL = "FAIL"

# Module path used for subprocess invocations so we always pick the same
# Python interpreter / virtual-env as the parent process.
_DEVFABRIC_MODULE = "ngksdevfabric.ngk_fabric.main"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read baseline manifest at {manifest_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(
            f"Baseline manifest is not a JSON object: {manifest_path}"
        )
    return data


def _run_stage_subprocess(
    sub_command: str,
    project_path: str,
    extra_args: list[str],
) -> tuple[int, str, str]:
    """Invoke ngksdevfabric <sub_command> <project_path> [extra_args] as a
    subprocess using the same Python interpreter as the parent process.

    Returns (exit_code, stdout, stderr).
    """
    cmd = [sys.executable, "-m", _DEVFABRIC_MODULE, sub_command, project_path] + extra_args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return int(proc.returncode), proc.stdout or "", proc.stderr or ""
    except OSError as exc:
        return 2, "", f"OSError launching {sub_command}: {exc}"


def _classify(
    baseline_value: str,
    exit_code: int,
    *,
    strict: bool = False,
) -> tuple[str, bool, bool]:
    """Classify a single stage result.

    Returns:
        current_value   "PASS" | "FAIL" | "N/A"
        is_regression   True when was-PASS and now-FAIL
        is_improvement  True when was-FAIL and now-PASS
    """
    if baseline_value == _NA:
        return _NA, False, False
    current = _PASS if exit_code == 0 else _FAIL
    was_pass = baseline_value == _PASS
    was_fail = baseline_value == _FAIL
    is_regression = was_pass and (current == _FAIL)
    is_improvement = was_fail and (current == _PASS)
    # Strict: any non-zero exit on a previously-passing step is a regression
    if strict and was_pass and exit_code != 0:
        is_regression = True
    return current, is_regression, is_improvement


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StageOutcome:
    stage: str           # probe | doctor | configure | build
    exit_code: int
    baseline_value: str  # PASS | FAIL | N/A
    current_value: str   # PASS | FAIL | N/A
    is_regression: bool
    is_improvement: bool
    stdout: str = ""
    stderr: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class RepoCheckResult:
    name: str
    path: str
    exists: bool
    stages: list[StageOutcome]
    regressions: list[str]
    improvements: list[str]
    overall: str   # PASS | REGRESSION | IMPROVEMENT


# ---------------------------------------------------------------------------
# Per-repo gate logic
# ---------------------------------------------------------------------------

def _check_repo(
    repo_entry: dict[str, Any],
    *,
    strict: bool,
    no_build: bool,
    build_mode: str,
) -> RepoCheckResult:
    name = str(repo_entry.get("name", "UNKNOWN"))
    path_str = str(repo_entry.get("path", ""))
    repo_path = Path(path_str)

    if not repo_path.is_dir():
        bl_probe = str(repo_entry.get("probe", _PASS))
        return RepoCheckResult(
            name=name,
            path=path_str,
            exists=False,
            stages=[
                StageOutcome(
                    stage="probe",
                    exit_code=2,
                    baseline_value=bl_probe,
                    current_value=_FAIL,
                    is_regression=True,
                    is_improvement=False,
                    notes=["repo_path_not_found"],
                )
            ],
            regressions=[f"probe:REPO_NOT_FOUND:{path_str}"],
            improvements=[],
            overall="REGRESSION",
        )

    stages: list[StageOutcome] = []
    regressions: list[str] = []
    improvements: list[str] = []

    # ------------------------------------------------------------------ probe
    probe_exit, probe_out, probe_err = _run_stage_subprocess("probe", path_str, [])
    bl_probe = str(repo_entry.get("probe", _PASS))
    probe_cur, probe_reg, probe_imp = _classify(bl_probe, probe_exit, strict=strict)
    stages.append(
        StageOutcome("probe", probe_exit, bl_probe, probe_cur, probe_reg, probe_imp, probe_out, probe_err)
    )
    if probe_reg:
        regressions.append(f"probe:{bl_probe}->{probe_cur}(exit={probe_exit})")
    if probe_imp:
        improvements.append(f"probe:{bl_probe}->{probe_cur}")

    # ----------------------------------------------------------------- doctor
    doctor_exit, doctor_out, doctor_err = _run_stage_subprocess(
        "doctor", path_str, ["--no-prompt"]
    )
    bl_doctor = str(repo_entry.get("doctor", _PASS))
    doctor_cur, doctor_reg, doctor_imp = _classify(bl_doctor, doctor_exit, strict=strict)

    # Strict-mode: non-zero exit that normal mode would not flag as FAIL
    # (e.g. warnings-only exit code from doctor) is treated as drift.
    if strict and doctor_exit != 0 and not doctor_reg:
        doctor_reg = True
        regressions.append(f"doctor:warnings_drift(exit={doctor_exit})")

    stages.append(
        StageOutcome("doctor", doctor_exit, bl_doctor, doctor_cur, doctor_reg, doctor_imp, doctor_out, doctor_err)
    )
    if doctor_reg and not any("doctor:" in r for r in regressions):
        regressions.append(f"doctor:{bl_doctor}->{doctor_cur}(exit={doctor_exit})")
    if doctor_imp:
        improvements.append(f"doctor:{bl_doctor}->{doctor_cur}")

    # ------------------------------------------- configure + build (ngksgraph)
    bl_configure = str(repo_entry.get("configure", _NA))
    bl_build = str(repo_entry.get("build", _NA))

    # ---------------------------------- tier contract enforcement
    _repo_tier = str(repo_entry.get("tier", ""))
    if _repo_tier == "TIER_1" and bl_configure == _NA:
        regressions.append(
            "tier_contract_violation:TIER_1_requires_configure_PASS_but_baseline_is_NA"
        )
    if _repo_tier == "TIER_2" and bl_configure != _NA:
        regressions.append(
            "tier_contract_violation:TIER_2_requires_configure_NA_but_baseline_is_not_NA"
        )

    if bl_configure != _NA and not no_build:
        # The build command exercises both configure and build in a single
        # pipeline call.  Its exit code covers both stages.
        build_exit, build_out, build_err = _run_stage_subprocess(
            "build", path_str, ["--mode", build_mode]
        )
        cfg_cur, cfg_reg, cfg_imp = _classify(bl_configure, build_exit, strict=strict)
        bld_cur, bld_reg, bld_imp = _classify(bl_build, build_exit, strict=strict)

        stages.append(
            StageOutcome(
                "configure", build_exit, bl_configure, cfg_cur, cfg_reg, cfg_imp,
                build_out, build_err,
                notes=["exit_derived_from_build_command"],
            )
        )
        stages.append(
            StageOutcome(
                "build", build_exit, bl_build, bld_cur, bld_reg, bld_imp,
                build_out, build_err,
                notes=["exit_derived_from_build_command"],
            )
        )
        if cfg_reg:
            regressions.append(f"configure:{bl_configure}->{cfg_cur}(exit={build_exit})")
        if bld_reg:
            regressions.append(f"build:{bl_build}->{bld_cur}(exit={build_exit})")
        if cfg_imp:
            improvements.append(f"configure:{bl_configure}->{cfg_cur}")
        if bld_imp:
            improvements.append(f"build:{bl_build}->{bld_cur}")
    else:
        # N/A or --no-build: record the skip without flagging a regression.
        reason = "not_applicable" if bl_configure == _NA else "skipped_no_build_flag"
        stages.append(
            StageOutcome("configure", -1, bl_configure, bl_configure, False, False, notes=[reason])
        )
        stages.append(
            StageOutcome("build", -1, bl_build, bl_build, False, False, notes=[reason])
        )

    overall = (
        "REGRESSION" if regressions
        else "IMPROVEMENT" if improvements
        else "PASS"
    )
    return RepoCheckResult(
        name=name,
        path=path_str,
        exists=True,
        stages=stages,
        regressions=regressions,
        improvements=improvements,
        overall=overall,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_baseline_manifest(baseline_arg: str, eco_root: Path | None) -> Path:
    """Resolve the path to repo_manifest.json.

    Resolution order:
    1. ``--baseline`` as a direct .json file path.
    2. ``--baseline`` as a directory containing repo_manifest.json.
    3. Auto-discover the latest ``.baseline_v*`` directory under eco_root or cwd.
    """
    if baseline_arg:
        candidate = Path(baseline_arg).resolve()
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            f = candidate / "repo_manifest.json"
            if f.exists():
                return f
        raise RuntimeError(
            f"--baseline '{baseline_arg}' is not a repo_manifest.json file "
            f"or a directory containing one."
        )

    search_roots: list[Path] = []
    if eco_root:
        search_roots.append(eco_root.resolve())
    search_roots.append(Path.cwd().resolve())

    for root in search_roots:
        dirs = sorted(
            (d for d in root.glob(".baseline_v*") if d.is_dir()),
            reverse=True,
        )
        for d in dirs:
            f = d / "repo_manifest.json"
            if f.exists():
                return f

    raise RuntimeError(
        "Could not auto-discover a repo_manifest.json. "
        "Use --baseline <path> or --eco-root <folder-containing-baseline-dir>."
    )


def run_certify_baseline(
    *,
    manifest_path: Path,
    repo_filter: list[str] | None,
    build_mode: str,
    strict: bool,
    no_build: bool,
    pf: Path,
) -> dict[str, Any]:
    """Execute all repo certification checks and return the full gate result.

    Writes ``certify_baseline_gate.json`` under ``pf/<run_id>/``.

    Returns a dict with at least:
        ``gate``            "PASS" | "FAIL"
        ``repos_regression`` count of regressed repos
        ``repo_results``    per-repo breakdown
    """
    manifest = _read_manifest(manifest_path)
    certified_repos: list[dict[str, Any]] = manifest.get("certified_repos", [])
    baseline_name = str(manifest.get("baseline_name", "UNKNOWN"))
    baseline_locked_at = str(manifest.get("locked_at", "UNKNOWN"))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"certify_baseline_{stamp}"
    run_dir = pf / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    repo_results: list[RepoCheckResult] = []
    for repo_entry in certified_repos:
        name = str(repo_entry.get("name", "UNKNOWN"))
        if repo_filter and name not in repo_filter:
            continue
        result = _check_repo(
            repo_entry,
            strict=strict,
            no_build=no_build,
            build_mode=build_mode,
        )
        repo_results.append(result)

    any_regression = any(r.overall == "REGRESSION" for r in repo_results)
    gate = _FAIL if any_regression else _PASS

    payload: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": _iso_now(),
        "baseline_name": baseline_name,
        "baseline_locked_at": baseline_locked_at,
        "baseline_manifest": str(manifest_path),
        "strict": strict,
        "no_build": no_build,
        "build_mode": build_mode,
        "gate": gate,
        "repos_checked": len(repo_results),
        "repos_pass": sum(1 for r in repo_results if r.overall in (_PASS, "IMPROVEMENT")),
        "repos_regression": sum(1 for r in repo_results if r.overall == "REGRESSION"),
        "repos_improvement": sum(1 for r in repo_results if r.overall == "IMPROVEMENT"),
        "repo_results": [
            {
                "name": r.name,
                "path": r.path,
                "exists": r.exists,
                "overall": r.overall,
                "regressions": r.regressions,
                "improvements": r.improvements,
                "stages": [
                    {
                        "stage": s.stage,
                        "exit_code": s.exit_code,
                        "baseline_value": s.baseline_value,
                        "current_value": s.current_value,
                        "is_regression": s.is_regression,
                        "is_improvement": s.is_improvement,
                        "notes": s.notes,
                    }
                    for s in r.stages
                ],
            }
            for r in repo_results
        ],
    }

    gate_file = run_dir / "certify_baseline_gate.json"
    gate_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
