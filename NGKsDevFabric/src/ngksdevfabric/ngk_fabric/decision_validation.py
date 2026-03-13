from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .certify_compare import run_certification_comparison


CERTIFICATION_GATE_POLICY: dict[str, dict[str, object]] = {
    "CERTIFIED_IMPROVEMENT": {
        "gate": "PASS",
        "exit_code": 0,
        "severity": "success",
        "recommended_next_action": "promote_this_baseline_or_continue_monitoring",
    },
    "CERTIFIED_STABLE": {
        "gate": "PASS",
        "exit_code": 0,
        "severity": "success",
        "recommended_next_action": "continue_periodic_validation",
    },
    "CERTIFIED_REGRESSION": {
        "gate": "FAIL",
        "exit_code": 1,
        "severity": "failure",
        "recommended_next_action": "block_release_and_fix_regressions",
    },
    "CERTIFICATION_INCONCLUSIVE": {
        "gate": "FAIL",
        "exit_code": 1,
        "severity": "failure",
        "recommended_next_action": "repair_inputs_and_rerun_validation",
    },
}


@dataclass
class CaseSpec:
    case_id: str
    input_type: str
    expected_decision: str
    baseline_path: Path
    current_path: Path


def gate_policy_for(decision: str) -> dict[str, object]:
    return dict(
        CERTIFICATION_GATE_POLICY.get(
            decision,
            {
                "gate": "FAIL",
                "exit_code": 1,
                "severity": "failure",
                "recommended_next_action": "inspect_decision_engine_output",
            },
        )
    )


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _build_inconclusive_fixture(base_matrix: dict[str, Any], base_metrics: dict[str, Any], base_manifest: dict[str, Any], root: Path) -> Path:
    cur = root / "inconclusive_current"
    scenarios = list(base_matrix.get("scenarios", []))
    if scenarios:
        scenarios = scenarios[:-1]
    matrix = {
        "baseline_version": "fixture_inconclusive",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenarios,
    }
    manifest = deepcopy(base_manifest)
    manifest["scenario_count"] = len(scenarios)
    metrics = deepcopy(base_metrics)

    _write_json(cur / "baseline_matrix.json", matrix)
    _write_json(cur / "diagnostic_metrics.json", metrics)
    _write_json(cur / "baseline_manifest.json", manifest)
    return cur


def _build_improvement_fixture(base_matrix: dict[str, Any], base_metrics: dict[str, Any], base_manifest: dict[str, Any], root: Path) -> Path:
    cur = root / "improvement_current"
    matrix = deepcopy(base_matrix)
    matrix["baseline_version"] = "fixture_improvement"
    matrix["generated_at"] = datetime.now(timezone.utc).isoformat()

    for row in matrix.get("scenarios", []):
        if not isinstance(row, dict):
            continue
        row["diagnostic_score"] = round(_clamp(float(row.get("diagnostic_score", 0.0)) + 0.06, 0.0, 1.0), 4)
        scores = row.get("scores", {}) if isinstance(row.get("scores"), dict) else {}
        for key in ("remediation_quality", "proof_quality"):
            val = float(scores.get(key, 0.0))
            scores[key] = round(_clamp(val + 0.2, 0.0, 2.0), 4)
        row["scores"] = scores

    metrics = deepcopy(base_metrics)
    metrics["average_diagnostic_score"] = round(float(base_metrics.get("average_diagnostic_score", 0.0)) + 0.05, 4)
    metrics["average_remediation_quality"] = round(_clamp(float(base_metrics.get("average_remediation_quality", 0.0)) + 0.1, 0.0, 2.0), 4)

    manifest = deepcopy(base_manifest)
    manifest["baseline_version"] = "fixture_improvement"

    _write_json(cur / "baseline_matrix.json", matrix)
    _write_json(cur / "diagnostic_metrics.json", metrics)
    _write_json(cur / "baseline_manifest.json", manifest)
    return cur


def _build_regression_fixture(base_matrix: dict[str, Any], base_metrics: dict[str, Any], base_manifest: dict[str, Any], root: Path) -> Path:
    cur = root / "regression_current"
    matrix = deepcopy(base_matrix)
    matrix["baseline_version"] = "fixture_regression"
    matrix["generated_at"] = datetime.now(timezone.utc).isoformat()

    for row in matrix.get("scenarios", []):
        if not isinstance(row, dict):
            continue
        row["diagnostic_score"] = round(_clamp(float(row.get("diagnostic_score", 0.0)) - 0.08, 0.0, 1.0), 4)
        scores = row.get("scores", {}) if isinstance(row.get("scores"), dict) else {}
        for key, drop in (
            ("component_ownership_accuracy", 0.4),
            ("root_cause_accuracy", 0.4),
            ("remediation_quality", 0.2),
            ("proof_quality", 0.2),
        ):
            val = float(scores.get(key, 0.0))
            scores[key] = round(_clamp(val - drop, 0.0, 2.0), 4)
        row["scores"] = scores

    metrics = deepcopy(base_metrics)
    metrics["average_diagnostic_score"] = round(float(base_metrics.get("average_diagnostic_score", 0.0)) - 0.07, 4)
    metrics["average_root_cause_accuracy"] = round(_clamp(float(base_metrics.get("average_root_cause_accuracy", 0.0)) - 0.2, 0.0, 2.0), 4)
    metrics["average_component_ownership_accuracy"] = round(
        _clamp(float(base_metrics.get("average_component_ownership_accuracy", 0.0)) - 0.2, 0.0, 2.0),
        4,
    )

    manifest = deepcopy(base_manifest)
    manifest["baseline_version"] = "fixture_regression"

    _write_json(cur / "baseline_matrix.json", matrix)
    _write_json(cur / "diagnostic_metrics.json", metrics)
    _write_json(cur / "baseline_manifest.json", manifest)
    return cur


def run_decision_validation(
    *,
    repo_root: Path,
    baseline_path: Path,
    current_path: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    baseline = baseline_path.resolve()
    current_real = current_path.resolve()
    runs_root = output_root.resolve() if output_root else (repo_root.resolve() / "_proof" / "runs")

    run_dir = runs_root / f"decision_validation_{_now_stamp()}"
    fixtures_root = run_dir / "fixtures"
    cases_root = run_dir / "cases"
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_matrix = _read_json(baseline / "baseline_matrix.json")
    baseline_metrics = _read_json(baseline / "diagnostic_metrics.json")
    baseline_manifest = _read_json(baseline / "baseline_manifest.json")

    inconclusive_current = _build_inconclusive_fixture(baseline_matrix, baseline_metrics, baseline_manifest, fixtures_root)
    improvement_current = _build_improvement_fixture(baseline_matrix, baseline_metrics, baseline_manifest, fixtures_root)
    regression_current = _build_regression_fixture(baseline_matrix, baseline_metrics, baseline_manifest, fixtures_root)

    case_specs = [
        CaseSpec(
            case_id="stable_real",
            input_type="real_baseline_vs_real_current",
            expected_decision="CERTIFIED_STABLE",
            baseline_path=baseline,
            current_path=current_real,
        ),
        CaseSpec(
            case_id="inconclusive_missing_scenario",
            input_type="fixture_incomplete_current",
            expected_decision="CERTIFICATION_INCONCLUSIVE",
            baseline_path=baseline,
            current_path=inconclusive_current,
        ),
        CaseSpec(
            case_id="improvement_fixture",
            input_type="fixture_improved_scores",
            expected_decision="CERTIFIED_IMPROVEMENT",
            baseline_path=baseline,
            current_path=improvement_current,
        ),
        CaseSpec(
            case_id="regression_fixture",
            input_type="fixture_regressed_scores",
            expected_decision="CERTIFIED_REGRESSION",
            baseline_path=baseline,
            current_path=regression_current,
        ),
    ]

    rows: list[dict[str, Any]] = []
    for spec in case_specs:
        case_pf = cases_root / spec.case_id
        result = run_certification_comparison(
            repo_root=repo_root,
            baseline_path=spec.baseline_path,
            current_path=spec.current_path,
            pf=case_pf,
        )

        eval_path = case_pf / "10_decision_evaluation.json"
        eval_data = _read_json(eval_path) if eval_path.exists() else {}
        reasons = eval_data.get("reasons", []) if isinstance(eval_data.get("reasons", []), list) else []
        reason = "; ".join(str(item) for item in reasons) if reasons else "no_reason_reported"

        actual = str(result.get("certification_decision", ""))
        passed = actual == spec.expected_decision
        rows.append(
            {
                "case_id": spec.case_id,
                "input_type": spec.input_type,
                "expected_decision": spec.expected_decision,
                "actual_decision": actual,
                "reason": reason,
                "pass_fail": "PASS" if passed else "FAIL",
            }
        )

    mismatches = [row for row in rows if row["pass_fail"] == "FAIL"]
    gate = "PASS" if not mismatches else "FAIL"

    matrix = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_path": str(baseline),
        "current_path": str(current_real),
        "cases": rows,
        "mismatches": mismatches,
        "overall_gate": gate,
    }
    _write_json(run_dir / "decision_validation_matrix.json", matrix)

    lines = [
        "# Decision Validation Summary",
        "",
        f"- baseline_path: {baseline}",
        f"- current_path: {current_real}",
        f"- cases_executed: {len(rows)}",
        f"- mismatches: {len(mismatches)}",
        f"- overall_gate: {gate}",
        "",
        "case_id | input_type | expected_decision | actual_decision | reason | pass/fail",
        "--- | --- | --- | --- | --- | ---",
    ]
    for row in rows:
        lines.append(
            f"{row['case_id']} | {row['input_type']} | {row['expected_decision']} | {row['actual_decision']} | {row['reason']} | {row['pass_fail']}"
        )
    _write_text(run_dir / "decision_validation_summary.md", "\n".join(lines) + "\n")

    _write_json(run_dir / "certification_gate_policy.json", CERTIFICATION_GATE_POLICY)

    zip_path = run_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", str(run_dir))

    return {
        "validation_dir": str(run_dir),
        "validation_zip": str(zip_path),
        "gate": gate,
        "cases": rows,
        "mismatches": mismatches,
    }
