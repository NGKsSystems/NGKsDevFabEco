from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.main import DEVFABRIC_ROOT, main
from ngksdevfabric.ngk_fabric.validation_orchestrator import run_validation_orchestrator


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_plan(
    *,
    project_root: Path,
    run_name: str,
    plan_class: str,
    rows: list[dict[str, object]],
    required_ids: list[str],
    optional_ids: list[str],
) -> Path:
    plan_root = project_root / "_proof" / "runs" / run_name
    planning = plan_root / "planning"

    required_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(required_ids)]
    optional_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(optional_ids)]

    _write_json(
        planning / "120_validation_plan_inputs.json",
        {
            "project_root": str(project_root.resolve()),
            "change_manifest": {"change_id": "chg_001", "touched_components": ["component_a"]},
            "touched_components": ["component_a"],
        },
    )
    _write_json(planning / "121_scenario_plan_ranking.json", {"rows": rows})
    _write_json(
        planning / "122_required_vs_optional_plan.json",
        {
            "required": required_rows,
            "optional": optional_rows,
        },
    )
    _write_json(
        planning / "123_component_focus_plan.json",
        {
            "rows": [
                {
                    "component": "component_a",
                    "watch_class": "NORMAL",
                    "predictive_risk_score": 0.20,
                    "unresolved_ratio": 0.10,
                    "focus_score": 0.20,
                    "priority_rank": 1,
                }
            ]
        },
    )
    _write_json(
        planning / "124_plan_classification.json",
        {
            "plan_class": plan_class,
            "aggregate_plan_score": 0.25,
            "required_scenario_count": len(required_rows),
            "optional_scenario_count": len(optional_rows),
        },
    )

    return plan_root


def _scenario_row(scenario_id: str, rank: int, score: float, required: bool) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "priority_rank": rank,
        "priority_score": score,
        "required": required,
        "selection_reason": "fixture",
        "signals": {
            "historical_detection_value": score,
            "watch_pressure": score,
            "predictive_pressure": score,
            "recurrence_pressure": score,
            "unresolved_pressure": score,
            "relevance": 1.0,
        },
    }


def _receipts(pf: Path) -> list[dict[str, object]]:
    payload = json.loads((pf / "execution" / "132_execution_receipts.json").read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    return rows if isinstance(rows, list) else []


def _failures(pf: Path) -> list[dict[str, object]]:
    payload = json.loads((pf / "execution" / "133_execution_failures.json").read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    return rows if isinstance(rows, list) else []


def test_minimal_plan_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_plan(
        project_root=project_root,
        run_name="validation_plan_minimal",
        plan_class="MINIMAL",
        rows=[
            _scenario_row("baseline_pass", 1, 0.05, True),
            _scenario_row("optional_a", 2, 0.08, False),
            _scenario_row("optional_b", 3, 0.09, False),
        ],
        required_ids=["baseline_pass"],
        optional_ids=["optional_a", "optional_b"],
    )

    pf = tmp_path / "proof" / "exec_minimal"
    result = run_validation_orchestrator(project_root=project_root, pf=pf, execution_policy="BALANCED")

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert int(summary.get("completed_scenario_count", 0)) == 1
    assert int(summary.get("skipped_scenario_count", 0)) >= 1


def test_heightened_plan_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_plan(
        project_root=project_root,
        run_name="validation_plan_heightened",
        plan_class="HEIGHTENED",
        rows=[
            _scenario_row("critical_path_a", 1, 0.70, True),
            _scenario_row("critical_path_b", 2, 0.66, True),
            _scenario_row("optional_c", 3, 0.62, False),
            _scenario_row("optional_d", 4, 0.58, False),
        ],
        required_ids=["critical_path_a", "critical_path_b"],
        optional_ids=["optional_c", "optional_d"],
    )

    pf = tmp_path / "proof" / "exec_heightened"
    result = run_validation_orchestrator(project_root=project_root, pf=pf, execution_policy="STRICT")

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert int(summary.get("completed_scenario_count", 0)) == 4
    assert int(summary.get("completed_optional_count", 0)) == 2


def test_early_failure_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_plan(
        project_root=project_root,
        run_name="validation_plan_early_failure",
        plan_class="CRITICAL",
        rows=[
            _scenario_row("critical_regression_case", 1, 0.95, True),
            _scenario_row("follow_on_required", 2, 0.70, True),
            _scenario_row("optional_tail", 3, 0.30, False),
        ],
        required_ids=["critical_regression_case", "follow_on_required"],
        optional_ids=["optional_tail"],
    )

    pf = tmp_path / "proof" / "exec_early_failure"
    run_validation_orchestrator(project_root=project_root, pf=pf, execution_policy="FAST")

    receipts = _receipts(pf)
    failures = _failures(pf)

    completed = [row for row in receipts if isinstance(row, dict) and str(row.get("execution_status", "")) == "COMPLETED"]
    assert len(completed) == 1
    top = completed[0] if isinstance(completed[0], dict) else {}
    assert str(top.get("result_classification", "")) == "CRITICAL_REGRESSION"
    assert failures


def test_balanced_execution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_plan(
        project_root=project_root,
        run_name="validation_plan_balanced",
        plan_class="STANDARD",
        rows=[
            _scenario_row("required_one", 1, 0.30, True),
            _scenario_row("optional_one", 2, 0.10, False),
            _scenario_row("optional_two", 3, 0.15, False),
        ],
        required_ids=["required_one"],
        optional_ids=["optional_one", "optional_two"],
    )

    pf = tmp_path / "proof" / "exec_balanced"
    result = run_validation_orchestrator(project_root=project_root, pf=pf, execution_policy="BALANCED")

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert int(summary.get("completed_required_count", 0)) == 1
    assert int(summary.get("completed_optional_count", 0)) == 1
    assert int(summary.get("skipped_scenario_count", 0)) == 1
    assert str(summary.get("early_stop_reason", "")) == "confidence_threshold_satisfied"



def test_run_validation_plan_cli(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_plan(
        project_root=project_root,
        run_name="validation_plan_cli",
        plan_class="STANDARD",
        rows=[
            _scenario_row("required_cli", 1, 0.20, True),
            _scenario_row("optional_cli", 2, 0.15, False),
        ],
        required_ids=["required_cli"],
        optional_ids=["optional_cli"],
    )

    pf_name = "validation_execution_cli"
    rc = main(
        [
            "run-validation-plan",
            "--project",
            str(project_root),
            "--execution-policy",
            "BALANCED",
            "--pf",
            pf_name,
        ]
    )
    assert rc == 0

    expected_pf = DEVFABRIC_ROOT.parent.resolve() / "_proof" / "runs" / pf_name
    assert (expected_pf / "execution" / "134_execution_summary.md").is_file()
