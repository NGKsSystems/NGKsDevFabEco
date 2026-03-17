"""
certification_status.py

Read-only inspector for project certification readiness state.

Rules:
- NEVER modifies files.
- NEVER triggers bootstrap or certification validation.
- Only inspects existing artifacts and reports classification.

Status states
-------------
MISSING_CERTIFICATION_STRUCTURE
    No certification_target.json and no certification/ baseline structure.

BOOTSTRAP_PLACEHOLDER_ONLY
    Required structure present; all key artifacts are bootstrap-managed
    placeholders (_bootstrap_managed=true). No real certification evidence.

CERTIFICATION_STRUCTURALLY_READY
    Required structure present and passes structural checks.
    May contain placeholder or real data.

PARTIAL_CERTIFICATION_DRIFT
    Some required assets are missing or inconsistent; scenario index
    does not match baseline matrix scenarios.

CERTIFICATION_EVIDENCE_PRESENT
    Real (non-placeholder) certification artifacts detected alongside
    structural readiness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Discovery markers (must match certification_bootstrap_templates.py)
# ---------------------------------------------------------------------------

_BOOTSTRAP_MANAGED_KEY = "_bootstrap_managed"
_PLACEHOLDER_STATUS_KEY = "placeholder_status"
_PLACEHOLDER_STATUS_VALUE = "template_not_real_certification_result"

# Required certification structural files relative to project_root
_REQUIRED_ARTIFACTS_MAP = {
    "certification_target": [
        "certification_target.json",
        "certification/certification_target.json",
    ],
    "scenario_index": ["certification/scenario_index.json"],
    "baseline_manifest": ["certification/baseline_v1/baseline_manifest.json"],
    "baseline_matrix": ["certification/baseline_v1/baseline_matrix.json"],
    "diagnostic_metrics": ["certification/baseline_v1/diagnostic_metrics.json"],
}

_BASELINE_FILES = [
    "certification/baseline_v1/baseline_manifest.json",
    "certification/baseline_v1/baseline_matrix.json",
    "certification/baseline_v1/diagnostic_metrics.json",
    "certification/scenario_index.json",
]

# States
STATE_MISSING = "MISSING_CERTIFICATION_STRUCTURE"
STATE_PLACEHOLDER = "BOOTSTRAP_PLACEHOLDER_ONLY"
STATE_STRUCTURALLY_READY = "CERTIFICATION_STRUCTURALLY_READY"
STATE_DRIFT = "PARTIAL_CERTIFICATION_DRIFT"
STATE_EVIDENCE_PRESENT = "CERTIFICATION_EVIDENCE_PRESENT"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CertificationStatusResult:
    state: str
    project: str
    structure_ok: bool
    bootstrap_managed_assets: int
    real_evidence_assets: int
    missing_assets: int
    drift_detected: bool
    drift_reasons: list[str] = field(default_factory=list)
    inspected_files: list[str] = field(default_factory=list)
    missing_file_list: list[str] = field(default_factory=list)
    bootstrap_managed_file_list: list[str] = field(default_factory=list)
    real_evidence_file_list: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "state": self.state,
            "structure_ok": self.structure_ok,
            "bootstrap_managed_assets": self.bootstrap_managed_assets,
            "real_evidence_assets": self.real_evidence_assets,
            "missing_assets": self.missing_assets,
            "drift_detected": self.drift_detected,
            "drift_reasons": self.drift_reasons,
            "inspected_files": self.inspected_files,
            "missing_file_list": self.missing_file_list,
            "bootstrap_managed_file_list": self.bootstrap_managed_file_list,
            "real_evidence_file_list": self.real_evidence_file_list,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _is_bootstrap_managed(data: dict[str, Any] | None) -> bool:
    if data is None:
        return False
    return bool(data.get(_BOOTSTRAP_MANAGED_KEY, False))


def _is_placeholder(data: dict[str, Any] | None) -> bool:
    """Returns True only if the artifact is a bootstrap placeholder (not real evidence)."""
    if data is None:
        return False
    return bool(data.get(_BOOTSTRAP_MANAGED_KEY, False)) and (
        str(data.get(_PLACEHOLDER_STATUS_KEY, "")).strip() == _PLACEHOLDER_STATUS_VALUE
    )


def _resolve_artifact_path(project_root: Path, candidates: list[str]) -> Path | None:
    for cand in candidates:
        p = project_root / cand
        if p.is_file():
            return p
    return None


def _classify_file(project_root: Path, rel_path: str) -> str:
    """Returns 'missing', 'bootstrap', or 'real'."""
    p = project_root / rel_path
    if not p.is_file():
        return "missing"
    data = _safe_load_json(p)
    if _is_placeholder(data):
        return "bootstrap"
    return "real"


def _detect_drift(project_root: Path) -> tuple[bool, list[str]]:
    """Detect scenario-index / baseline-matrix scenario list inconsistency."""
    reasons: list[str] = []

    scenario_index_path = project_root / "certification" / "scenario_index.json"
    baseline_matrix_path = project_root / "certification" / "baseline_v1" / "baseline_matrix.json"

    if not scenario_index_path.is_file() or not baseline_matrix_path.is_file():
        return False, reasons  # Not enough data to detect drift; structural check handles missing

    si_data = _safe_load_json(scenario_index_path)
    bm_data = _safe_load_json(baseline_matrix_path)

    if si_data is None:
        reasons.append("scenario_index_unreadable")
        return True, reasons
    if bm_data is None:
        reasons.append("baseline_matrix_unreadable")
        return True, reasons

    si_scenarios = si_data.get("scenarios", [])
    bm_scenarios = bm_data.get("scenarios", [])

    if not isinstance(si_scenarios, list) or not isinstance(bm_scenarios, list):
        reasons.append("scenario_list_invalid_shape")
        return True, reasons

    si_ids = {str(s.get("scenario_id", "")).strip() for s in si_scenarios if isinstance(s, dict)}
    bm_ids = {str(s.get("scenario_id", "")).strip() for s in bm_scenarios if isinstance(s, dict)}

    si_only = si_ids - bm_ids
    bm_only = bm_ids - si_ids

    if si_only:
        reasons.append(f"scenario_index_has_ids_not_in_baseline:{','.join(sorted(si_only))}")
    if bm_only:
        reasons.append(f"baseline_has_ids_not_in_scenario_index:{','.join(sorted(bm_only))}")

    return bool(reasons), reasons


# ---------------------------------------------------------------------------
# Main inspector
# ---------------------------------------------------------------------------


def inspect_certification_status(project_root: Path) -> CertificationStatusResult:
    """Inspect and classify project certification readiness. Read-only."""
    project_root = project_root.resolve()

    # ---- structural presence check ----------------------------------------
    missing_files: list[str] = []
    inspected_files: list[str] = []
    bootstrap_files: list[str] = []
    real_files: list[str] = []
    warnings: list[str] = []

    # Check certification_target (multi-candidate)
    target_candidates = _REQUIRED_ARTIFACTS_MAP["certification_target"]
    target_path = _resolve_artifact_path(project_root, target_candidates)
    if target_path is None:
        missing_files.append("certification_target.json")
    else:
        rel = str(target_path.relative_to(project_root))
        inspected_files.append(rel)
        data = _safe_load_json(target_path)
        if _is_placeholder(data):
            bootstrap_files.append(rel)
        else:
            real_files.append(rel)

    # Check single-candidate baseline files
    for rel_path in _BASELINE_FILES:
        full = project_root / rel_path
        inspected_files.append(rel_path)
        if not full.is_file():
            missing_files.append(rel_path)
        else:
            data = _safe_load_json(full)
            if _is_placeholder(data):
                bootstrap_files.append(rel_path)
            else:
                real_files.append(rel_path)

    structure_ok = len(missing_files) == 0

    # ---- drift detection --------------------------------------------------
    drift_detected, drift_reasons = _detect_drift(project_root)
    if drift_detected and structure_ok:
        # drift alone doesn't clear structure_ok; it's a separate signal
        pass

    # ---- scan for scenario proof evidence (real, non-placeholder) ----------
    cert_proof_dir = project_root / "certification" / "_proof"
    has_real_scenario_evidence = False
    if cert_proof_dir.is_dir():
        for manifest_path in cert_proof_dir.rglob("00_scenario_manifest.json"):
            data = _safe_load_json(manifest_path)
            if not _is_placeholder(data):
                has_real_scenario_evidence = True
                rel = str(manifest_path.relative_to(project_root))
                real_files.append(rel)

    # ---- classify state ---------------------------------------------------
    if len(missing_files) == 5:
        # Everything missing
        state = STATE_MISSING
    elif not structure_ok and not drift_detected:
        # Some files missing but not drift -> still partial missing
        state = STATE_DRIFT
        drift_detected = True
        drift_reasons.append(f"missing_required_files:{','.join(sorted(missing_files))}")
    elif drift_detected:
        state = STATE_DRIFT
    elif has_real_scenario_evidence and real_files:
        state = STATE_EVIDENCE_PRESENT
    elif real_files and not bootstrap_files:
        state = STATE_EVIDENCE_PRESENT
    elif bootstrap_files and not real_files:
        state = STATE_PLACEHOLDER
    elif structure_ok:
        state = STATE_STRUCTURALLY_READY
    else:
        state = STATE_DRIFT

    return CertificationStatusResult(
        state=state,
        project=str(project_root),
        structure_ok=structure_ok,
        bootstrap_managed_assets=len(bootstrap_files),
        real_evidence_assets=len(real_files),
        missing_assets=len(missing_files),
        drift_detected=drift_detected,
        drift_reasons=drift_reasons,
        inspected_files=sorted(set(inspected_files)),
        missing_file_list=sorted(set(missing_files)),
        bootstrap_managed_file_list=sorted(set(bootstrap_files)),
        real_evidence_file_list=sorted(set(real_files)),
        warnings=warnings,
    )
