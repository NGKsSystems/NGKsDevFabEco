from __future__ import annotations

import json
from pathlib import Path

from ngksdevfabric.ngk_fabric.main import DEVFABRIC_ROOT, main
from ngksdevfabric.ngk_fabric.validation_plugin_registry import ValidationPluginRegistry, execute_validation_plugins
from ngksdevfabric.ngk_fabric.validation_rerun_pipeline import run_validation_and_certify_pipeline


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _layout_snapshot(path: Path, *, containers: list[dict[str, object]]) -> Path:
    _write_json(
        path,
        {
            "view_name": "runtime_update_loop_scheduler",
            "root_container": "root",
            "supported_viewports": [
                {"name": "desktop", "height": 900, "width": 1400},
                {"name": "laptop", "height": 720, "width": 1200},
            ],
            "containers": containers,
        },
    )
    return path


def _seed_performance_inputs(
    *,
    pf: Path,
    scenario_runtimes: list[tuple[str, float]],
    stage_runtime_seconds: dict[str, float] | None = None,
    rerun_runtime_seconds: float = 0.0,
    transport_runtimes: list[float] | None = None,
    component_history_rows: list[dict[str, object]] | None = None,
    watch_rows: list[dict[str, object]] | None = None,
) -> None:
    _write_json(
        pf / "execution" / "132_execution_receipts.json",
        {
            "rows": [
                {
                    "scenario_id": scenario_id,
                    "runtime_seconds": runtime,
                    "execution_status": "COMPLETED",
                    "result_classification": "PASS",
                }
                for scenario_id, runtime in scenario_runtimes
            ]
        },
    )
    _write_json(pf / "execution" / "133_execution_failures.json", {"rows": []})
    _write_json(
        pf / "pipeline" / "141_execution_stage_summary.json",
        {"stage_runtime_seconds": dict(stage_runtime_seconds or {})},
    )
    _write_json(pf / "pipeline" / "142_certification_rerun_summary.json", {"runtime_seconds": rerun_runtime_seconds})
    _write_json(
        pf / "transport" / "91_transport_receipts.json",
        {"receipts": [{"request_id": f"req_{idx}", "runtime_seconds": runtime} for idx, runtime in enumerate(transport_runtimes or [])]},
    )
    _write_json(pf / "history" / "40_run_record.json", {"rows": []})
    _write_json(pf / "history" / "43_component_history_context.json", {"rows": list(component_history_rows or [])})
    _write_json(pf / "intelligence" / "110_component_watchlist.json", {"rows": list(watch_rows or [])})


def _performance_plugin_row(result: dict[str, object]) -> dict[str, object]:
    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("plugin_name", "")) == "performance_bottleneck_validation"
        ),
        {},
    )


def _seed_memory_inputs(
    *,
    pf: Path,
    scenario_memories: list[tuple[str, float]],
    stage_memory_mb: dict[str, float] | None = None,
    component_history_rows: list[dict[str, object]] | None = None,
    watch_rows: list[dict[str, object]] | None = None,
) -> None:
    _write_json(
        pf / "execution" / "132_execution_receipts.json",
        {
            "rows": [
                {
                    "scenario_id": scenario_id,
                    "peak_memory_mb": peak_memory_mb,
                    "runtime_seconds": 1.0,
                    "execution_status": "COMPLETED",
                    "result_classification": "PASS",
                }
                for scenario_id, peak_memory_mb in scenario_memories
            ]
        },
    )
    _write_json(pf / "execution" / "133_execution_failures.json", {"rows": []})
    _write_json(
        pf / "pipeline" / "141_execution_stage_summary.json",
        {"stage_peak_memory_mb": dict(stage_memory_mb or {})},
    )
    _write_json(pf / "pipeline" / "142_certification_rerun_summary.json", {"runtime_seconds": 0.0})
    _write_json(pf / "history" / "40_run_record.json", {"rows": []})
    _write_json(pf / "history" / "43_component_history_context.json", {"rows": list(component_history_rows or [])})
    _write_json(pf / "intelligence" / "110_component_watchlist.json", {"rows": list(watch_rows or [])})


def _memory_plugin_row(result: dict[str, object]) -> dict[str, object]:
    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("plugin_name", "")) == "memory_usage_validation"
        ),
        {},
    )


def _seed_architecture_inputs(
    *,
    pf: Path,
    modules: list[dict[str, object]],
    dependency_cycles: list[list[str]] | None = None,
    watch_rows: list[dict[str, object]] | None = None,
) -> None:
    _write_json(
        pf / "architecture" / "200_structural_profile.json",
        {
            "modules": list(modules),
            "dependency_cycles": list(dependency_cycles or []),
        },
    )
    _write_json(pf / "history" / "43_component_history_context.json", {"rows": []})
    _write_json(pf / "intelligence" / "110_component_watchlist.json", {"rows": list(watch_rows or [])})


def _architecture_plugin_row(result: dict[str, object]) -> dict[str, object]:
    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("plugin_name", "")) == "architectural_complexity_validation"
        ),
        {},
    )


def _seed_api_contract_inputs(
    *,
    pf: Path,
    contracts: list[dict[str, object]],
) -> None:
    _write_json(
        pf / "api_contract" / "201_contract_evidence.json",
        {
            "contracts": list(contracts),
        },
    )
    _write_json(pf / "history" / "43_component_history_context.json", {"rows": []})
    _write_json(pf / "intelligence" / "111_regression_pattern_memory.json", {"rows": []})


def _api_contract_plugin_row(result: dict[str, object]) -> dict[str, object]:
    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("plugin_name", "")) == "api_contract_validation"
        ),
        {},
    )


def _seed_security_inputs(
    *,
    pf: Path,
    entries: list[dict[str, object]],
) -> None:
    _write_json(
        pf / "security" / "201_security_configuration_evidence.json",
        {
            "entries": list(entries),
        },
    )
    _write_json(pf / "history" / "43_component_history_context.json", {"rows": []})
    _write_json(pf / "intelligence" / "111_regression_pattern_memory.json", {"rows": []})


def _security_plugin_row(result: dict[str, object]) -> dict[str, object]:
    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("plugin_name", "")) == "security_misconfiguration_validation"
        ),
        {},
    )


def test_plugin_framework_load(tmp_path: Path) -> None:
    registry = ValidationPluginRegistry()
    plugins = registry.discover_available_plugins()
    names = [item.plugin_name for item in plugins]

    assert "ui_layout_integrity" in names
    assert "performance_bottleneck_validation" in names
    assert "memory_usage_validation" in names
    assert "architectural_complexity_validation" in names
    assert "api_contract_validation" in names
    assert "security_misconfiguration_validation" in names


def test_ui_layout_overflow_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "plugin_overflow"

    snapshot = _layout_snapshot(
        tmp_path / "overflow_layout_snapshot.json",
        containers=[
            {"name": "root", "type": "panel", "height": 420, "padding": 8, "spacing": 6},
            {"name": "status_row", "parent": "root", "type": "panel", "height": 80, "min_height": 80, "y": 8},
            {"name": "control_card", "parent": "root", "type": "card", "height": 260, "min_height": 260, "y": 96},
            {"name": "button_row", "parent": "root", "type": "panel", "height": 140, "min_height": 140, "y": 360},
        ],
    )

    result = execute_validation_plugins(
        project_root=project_root,
        pf=pf,
        view_name="runtime_update_loop_scheduler",
        layout_snapshot_path=snapshot,
    )

    rows = result.get("rows", []) if isinstance(result.get("rows", []), list) else []
    ui_row = next((row for row in rows if isinstance(row, dict) and str(row.get("plugin_name", "")) == "ui_layout_integrity"), {})
    assert ui_row
    assert str(ui_row.get("status", "")) in {"WARNING", "FAIL"}

    overflow_payload = json.loads((pf / "validation_plugins" / "ui_layout" / "layout" / "210_layout_overflow.json").read_text(encoding="utf-8"))
    overflow_rows = overflow_payload.get("rows", []) if isinstance(overflow_payload.get("rows", []), list) else []
    assert any("LAYOUT_OVERFLOW" in str(row.get("issue_id", "")) for row in overflow_rows if isinstance(row, dict))


def test_ui_layout_collision_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "plugin_collision"

    snapshot = _layout_snapshot(
        tmp_path / "collision_layout_snapshot.json",
        containers=[
            {"name": "root", "type": "panel", "height": 400, "padding": 10, "spacing": 0},
            {"name": "status_row", "parent": "root", "type": "panel", "height": 120, "min_height": 120, "rendered_top": 20, "rendered_bottom": 170},
            {"name": "input_area", "parent": "root", "type": "panel", "height": 120, "min_height": 120, "rendered_top": 150, "rendered_bottom": 260},
        ],
    )

    execute_validation_plugins(
        project_root=project_root,
        pf=pf,
        view_name="runtime_update_loop_scheduler",
        layout_snapshot_path=snapshot,
    )

    collision_payload = json.loads((pf / "validation_plugins" / "ui_layout" / "layout" / "211_layout_collision.json").read_text(encoding="utf-8"))
    rows = collision_payload.get("rows", []) if isinstance(collision_payload.get("rows", []), list) else []
    assert any("LAYOUT_COLLISION" in str(row.get("issue_id", "")) for row in rows if isinstance(row, dict))


def test_nested_wrapper_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "plugin_wrapper"

    snapshot = _layout_snapshot(
        tmp_path / "wrapper_layout_snapshot.json",
        containers=[
            {"name": "root", "type": "frame", "height": 600, "padding": 8, "spacing": 4},
            {"name": "wrap_a", "parent": "root", "type": "panel", "height": 560, "min_height": 560},
            {"name": "wrap_b", "parent": "wrap_a", "type": "card", "height": 520, "min_height": 520},
            {"name": "wrap_c", "parent": "wrap_b", "type": "layout", "height": 480, "min_height": 480},
            {"name": "wrap_d", "parent": "wrap_c", "type": "panel", "height": 440, "min_height": 440},
            {"name": "content", "parent": "wrap_d", "type": "control", "height": 80, "min_height": 80},
        ],
    )

    execute_validation_plugins(
        project_root=project_root,
        pf=pf,
        view_name="runtime_update_loop_scheduler",
        layout_snapshot_path=snapshot,
    )

    wrapper_payload = json.loads((pf / "validation_plugins" / "ui_layout" / "layout" / "212_layout_wrapper_waste.json").read_text(encoding="utf-8"))
    rows = wrapper_payload.get("rows", []) if isinstance(wrapper_payload.get("rows", []), list) else []
    assert any("WRAPPER_WASTE_WARNING" in str(row.get("issue_id", "")) for row in rows if isinstance(row, dict))


def test_healthy_performance_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "healthy_performance_fixture"

    _seed_performance_inputs(
        pf=pf,
        scenario_runtimes=[("scenario_a", 2.0), ("scenario_b", 3.0)],
        stage_runtime_seconds={"planning": 4.0, "execution": 5.0, "packaging": 4.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    perf_row = _performance_plugin_row(result)
    assert perf_row
    assert str(perf_row.get("status", "")) == "PASS"

    total_report = json.loads((pf / "validation_plugins" / "performance" / "performance" / "230_total_runtime_report.json").read_text(encoding="utf-8"))
    summary = total_report.get("summary", {}) if isinstance(total_report.get("summary", {}), dict) else {}
    assert int(summary.get("finding_count", 0)) == 0


def test_total_runtime_overbudget_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "total_runtime_overbudget_fixture"

    _seed_performance_inputs(
        pf=pf,
        scenario_runtimes=[("scenario_a", 35.0), ("scenario_b", 30.0)],
        stage_runtime_seconds={"execution": 65.0, "planning": 3.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    perf_row = _performance_plugin_row(result)
    assert perf_row
    assert str(perf_row.get("status", "")) == "FAIL"

    total_report = json.loads((pf / "validation_plugins" / "performance" / "performance" / "230_total_runtime_report.json").read_text(encoding="utf-8"))
    rows = total_report.get("rows", []) if isinstance(total_report.get("rows", []), list) else []
    assert any(str(row.get("finding_id", "")).startswith("TOTAL_RUNTIME_BOTTLENECK") for row in rows if isinstance(row, dict))


def test_stage_hotspot_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "stage_hotspot_fixture"

    _seed_performance_inputs(
        pf=pf,
        scenario_runtimes=[("scenario_a", 2.0), ("scenario_b", 2.0)],
        stage_runtime_seconds={"planning": 20.0, "execution": 4.0, "packaging": 2.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    perf_row = _performance_plugin_row(result)
    assert perf_row
    assert str(perf_row.get("status", "")) == "WARNING"

    stage_report = json.loads((pf / "validation_plugins" / "performance" / "performance" / "231_stage_hotspots.json").read_text(encoding="utf-8"))
    rows = stage_report.get("rows", []) if isinstance(stage_report.get("rows", []), list) else []
    ids = {str(row.get("finding_id", "")) for row in rows if isinstance(row, dict)}
    assert any(item.startswith("STAGE_HOTSPOT") for item in ids)


def test_repeated_slow_path_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "repeated_slow_path_fixture"

    _seed_performance_inputs(
        pf=pf,
        scenario_runtimes=[("scenario_a", 2.0), ("scenario_b", 2.5)],
        stage_runtime_seconds={"planning": 1.0, "execution": 4.5},
        component_history_rows=[
            {
                "component": "critical_path",
                "slow_path_recurrence_count": 4,
                "mean_runtime_seconds": 12.0,
            }
        ],
        watch_rows=[{"component": "critical_path", "watch_class": "NORMAL"}],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    perf_row = _performance_plugin_row(result)
    assert perf_row
    assert str(perf_row.get("status", "")) in {"WARNING", "FAIL"}

    slow_path_report = json.loads((pf / "validation_plugins" / "performance" / "performance" / "233_repeated_slow_paths.json").read_text(encoding="utf-8"))
    rows = slow_path_report.get("rows", []) if isinstance(slow_path_report.get("rows", []), list) else []
    assert any(str(row.get("finding_id", "")).startswith("REPEATED_SLOW_PATH") for row in rows if isinstance(row, dict))


def test_healthy_memory_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "healthy_memory_fixture"

    _seed_memory_inputs(
        pf=pf,
        scenario_memories=[("scenario_a", 120.0), ("scenario_b", 140.0)],
        stage_memory_mb={"planning": 80.0, "execution": 120.0, "packaging": 90.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    memory_row = _memory_plugin_row(result)
    assert memory_row
    assert str(memory_row.get("status", "")) == "PASS"

    peak_report = json.loads((pf / "validation_plugins" / "memory" / "memory" / "240_peak_memory_report.json").read_text(encoding="utf-8"))
    summary = peak_report.get("summary", {}) if isinstance(peak_report.get("summary", {}), dict) else {}
    assert int(summary.get("fail_count", 0)) == 0


def test_peak_memory_overbudget_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "peak_memory_overbudget_fixture"

    _seed_memory_inputs(
        pf=pf,
        scenario_memories=[("scenario_a", 900.0), ("scenario_b", 1150.0)],
        stage_memory_mb={"execution": 1100.0, "planning": 300.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    memory_row = _memory_plugin_row(result)
    assert memory_row
    assert str(memory_row.get("status", "")) == "FAIL"

    peak_report = json.loads((pf / "validation_plugins" / "memory" / "memory" / "240_peak_memory_report.json").read_text(encoding="utf-8"))
    rows = peak_report.get("rows", []) if isinstance(peak_report.get("rows", []), list) else []
    assert any(str(row.get("finding_id", "")).startswith("PEAK_MEMORY_BUDGET_EXCEEDED") for row in rows if isinstance(row, dict))


def test_stage_memory_hotspot_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "stage_memory_hotspot_fixture"

    _seed_memory_inputs(
        pf=pf,
        scenario_memories=[("scenario_a", 320.0), ("scenario_b", 300.0)],
        stage_memory_mb={"planning": 540.0, "execution": 100.0, "packaging": 80.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    memory_row = _memory_plugin_row(result)
    assert memory_row
    assert str(memory_row.get("status", "")) in {"WARNING", "FAIL"}

    hotspot_report = json.loads((pf / "validation_plugins" / "memory" / "memory" / "241_stage_memory_hotspots.json").read_text(encoding="utf-8"))
    rows = hotspot_report.get("rows", []) if isinstance(hotspot_report.get("rows", []), list) else []
    ids = {str(row.get("finding_id", "")) for row in rows if isinstance(row, dict)}
    assert any(item.startswith("STAGE_MEMORY_HOTSPOT") for item in ids)


def test_memory_growth_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "memory_growth_fixture"

    _seed_memory_inputs(
        pf=pf,
        scenario_memories=[("scenario_a", 260.0), ("scenario_b", 280.0)],
        stage_memory_mb={"planning": 100.0, "execution": 260.0, "packaging": 270.0},
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    memory_row = _memory_plugin_row(result)
    assert memory_row
    assert str(memory_row.get("status", "")) in {"WARNING", "FAIL"}

    growth_report = json.loads((pf / "validation_plugins" / "memory" / "memory" / "242_memory_growth_report.json").read_text(encoding="utf-8"))
    rows = growth_report.get("rows", []) if isinstance(growth_report.get("rows", []), list) else []
    assert any(str(row.get("finding_id", "")).startswith("MEMORY_GROWTH_WARNING") for row in rows if isinstance(row, dict))


def test_repeated_high_memory_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "repeated_high_memory_fixture"

    _seed_memory_inputs(
        pf=pf,
        scenario_memories=[("scenario_a", 300.0), ("scenario_b", 310.0)],
        stage_memory_mb={"planning": 140.0, "execution": 280.0, "packaging": 130.0},
        component_history_rows=[
            {
                "component": "memory_intense_stage",
                "high_memory_recurrence_count": 4,
                "mean_peak_memory_mb": 700.0,
            }
        ],
        watch_rows=[{"component": "memory_intense_stage", "watch_class": "NORMAL"}],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    memory_row = _memory_plugin_row(result)
    assert memory_row
    assert str(memory_row.get("status", "")) in {"WARNING", "FAIL"}

    repeated_report = json.loads((pf / "validation_plugins" / "memory" / "memory" / "243_repeated_high_memory_paths.json").read_text(encoding="utf-8"))
    rows = repeated_report.get("rows", []) if isinstance(repeated_report.get("rows", []), list) else []
    assert any(str(row.get("finding_id", "")).startswith("REPEATED_HIGH_MEMORY_PATH") for row in rows if isinstance(row, dict))


def test_healthy_architecture_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "healthy_architecture_fixture"

    _seed_architecture_inputs(
        pf=pf,
        modules=[
            {"module": "core_a", "nesting_depth": 3, "module_size": 300, "dependency_fanout": 3, "dependency_fanin": 2, "depends_on": ["shared"]},
            {"module": "core_b", "nesting_depth": 4, "module_size": 300, "dependency_fanout": 2, "dependency_fanin": 3, "depends_on": ["shared"]},
            {"module": "shared", "nesting_depth": 2, "module_size": 300, "dependency_fanout": 1, "dependency_fanin": 4, "depends_on": []},
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    arch_row = _architecture_plugin_row(result)
    assert arch_row
    assert str(arch_row.get("status", "")) == "PASS"

    nesting_report = json.loads((pf / "validation_plugins" / "architecture" / "architecture" / "250_nesting_depth_report.json").read_text(encoding="utf-8"))
    summary = nesting_report.get("summary", {}) if isinstance(nesting_report.get("summary", {}), dict) else {}
    assert int(summary.get("fail_count", 0)) == 0


def test_excessive_nesting_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "excessive_nesting_fixture"

    _seed_architecture_inputs(
        pf=pf,
        modules=[
            {"module": "deep_module", "nesting_depth": 9, "module_size": 500, "dependency_fanout": 3, "dependency_fanin": 2, "depends_on": []},
            {"module": "support_module", "nesting_depth": 2, "module_size": 200, "dependency_fanout": 1, "dependency_fanin": 1, "depends_on": []},
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    arch_row = _architecture_plugin_row(result)
    assert arch_row
    assert str(arch_row.get("status", "")) in {"WARNING", "FAIL"}

    nesting_report = json.loads((pf / "validation_plugins" / "architecture" / "architecture" / "250_nesting_depth_report.json").read_text(encoding="utf-8"))
    rows = nesting_report.get("rows", []) if isinstance(nesting_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "EXCESSIVE_NESTING_DEPTH" for row in rows if isinstance(row, dict))


def test_coupling_hotspot_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "coupling_hotspot_fixture"

    _seed_architecture_inputs(
        pf=pf,
        modules=[
            {
                "module": "hub_module",
                "nesting_depth": 4,
                "module_size": 700,
                "dependency_fanout": 18,
                "dependency_fanin": 14,
                "depends_on": ["a", "b", "c", "d", "e", "f", "g", "h"],
            },
            {"module": "leaf_module", "nesting_depth": 2, "module_size": 180, "dependency_fanout": 1, "dependency_fanin": 1, "depends_on": []},
        ],
        watch_rows=[{"component": "hub_module", "watch_class": "HOT"}],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    arch_row = _architecture_plugin_row(result)
    assert arch_row
    assert str(arch_row.get("status", "")) in {"WARNING", "FAIL"}

    coupling_report = json.loads((pf / "validation_plugins" / "architecture" / "architecture" / "252_coupling_hotspots.json").read_text(encoding="utf-8"))
    rows = coupling_report.get("rows", []) if isinstance(coupling_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "COUPLING_HOTSPOT" for row in rows if isinstance(row, dict))


def test_circular_dependency_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "circular_dependency_fixture"

    _seed_architecture_inputs(
        pf=pf,
        modules=[
            {"module": "module_a", "nesting_depth": 3, "module_size": 400, "dependency_fanout": 2, "dependency_fanin": 2, "depends_on": ["module_b"]},
            {"module": "module_b", "nesting_depth": 3, "module_size": 420, "dependency_fanout": 2, "dependency_fanin": 2, "depends_on": ["module_a"]},
        ],
        dependency_cycles=[["module_a", "module_b"]],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    arch_row = _architecture_plugin_row(result)
    assert arch_row
    assert str(arch_row.get("status", "")) in {"WARNING", "FAIL"}

    dependency_report = json.loads((pf / "validation_plugins" / "architecture" / "architecture" / "253_dependency_risk_report.json").read_text(encoding="utf-8"))
    rows = dependency_report.get("rows", []) if isinstance(dependency_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "CIRCULAR_DEPENDENCY_RISK" for row in rows if isinstance(row, dict))


def test_god_module_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "god_module_fixture"

    _seed_architecture_inputs(
        pf=pf,
        modules=[
            {
                "module": "mega_module",
                "nesting_depth": 9,
                "module_size": 2400,
                "dependency_fanout": 20,
                "dependency_fanin": 18,
                "depends_on": ["sub_a", "sub_b", "sub_c", "sub_d"],
            },
            {"module": "sub_a", "nesting_depth": 2, "module_size": 140, "dependency_fanout": 1, "dependency_fanin": 2, "depends_on": []},
            {"module": "sub_b", "nesting_depth": 2, "module_size": 160, "dependency_fanout": 1, "dependency_fanin": 2, "depends_on": []},
        ],
        watch_rows=[{"component": "mega_module", "watch_class": "CRITICAL"}],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    arch_row = _architecture_plugin_row(result)
    assert arch_row
    assert str(arch_row.get("status", "")) in {"WARNING", "FAIL"}

    dependency_report = json.loads((pf / "validation_plugins" / "architecture" / "architecture" / "253_dependency_risk_report.json").read_text(encoding="utf-8"))
    rows = dependency_report.get("rows", []) if isinstance(dependency_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "GOD_MODULE_CANDIDATE" for row in rows if isinstance(row, dict))


def test_healthy_contract_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "healthy_contract_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.2.1",
                "expected_fields": [
                    {"field_path": "order_id", "type": "str", "required": True, "nullable": False},
                    {"field_path": "quantity", "type": "int", "required": True, "nullable": False},
                    {"field_path": "status", "type": "str", "required": True, "nullable": False, "enum": ["OPEN", "CLOSED"]},
                ],
                "observed_payload": {"order_id": "A1", "quantity": 2, "status": "OPEN"},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) == "PASS"

    required_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "260_required_field_report.json").read_text(encoding="utf-8"))
    summary = required_report.get("summary", {}) if isinstance(required_report.get("summary", {}), dict) else {}
    assert int(summary.get("fail_count", 0)) == 0


def test_missing_required_field_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "missing_required_field_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.2.0",
                "expected_fields": [
                    {"field_path": "order_id", "type": "str", "required": True, "nullable": False},
                    {"field_path": "quantity", "type": "int", "required": True, "nullable": False},
                ],
                "observed_payload": {"order_id": "A1"},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) == "FAIL"

    required_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "260_required_field_report.json").read_text(encoding="utf-8"))
    rows = required_report.get("rows", []) if isinstance(required_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "MISSING_REQUIRED_FIELD" for row in rows if isinstance(row, dict))


def test_type_mismatch_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "type_mismatch_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.2.0",
                "expected_fields": [
                    {"field_path": "quantity", "type": "int", "required": True, "nullable": False},
                ],
                "observed_payload": {"quantity": "two"},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) == "FAIL"

    type_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "261_type_mismatch_report.json").read_text(encoding="utf-8"))
    rows = type_report.get("rows", []) if isinstance(type_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "TYPE_MISMATCH" for row in rows if isinstance(row, dict))


def test_unknown_field_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "unknown_field_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.2.0",
                "expected_fields": [
                    {"field_path": "order_id", "type": "str", "required": True, "nullable": False},
                ],
                "observed_payload": {"order_id": "A1", "debug_info": "x"},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) in {"WARNING", "FAIL"}

    unknown_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "262_unknown_field_report.json").read_text(encoding="utf-8"))
    rows = unknown_report.get("rows", []) if isinstance(unknown_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "UNKNOWN_FIELD_VIOLATION" for row in rows if isinstance(row, dict))


def test_version_drift_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "version_drift_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.5.0",
                "expected_fields": [
                    {"field_path": "order_id", "type": "str", "required": True, "nullable": False},
                ],
                "observed_payload": {"order_id": "A1"},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) in {"WARNING", "FAIL"}

    version_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "263_version_drift_report.json").read_text(encoding="utf-8"))
    rows = version_report.get("rows", []) if isinstance(version_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "VERSION_DRIFT_WARNING" for row in rows if isinstance(row, dict))


def test_payload_shape_incompatibility_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "payload_shape_incompatibility_fixture"

    _seed_api_contract_inputs(
        pf=pf,
        contracts=[
            {
                "contract_name": "order_api",
                "caller_version": "1.2.0",
                "callee_version": "1.2.0",
                "expected_fields": [
                    {
                        "field_path": "metadata",
                        "type": "dict",
                        "required": True,
                        "nullable": False,
                        "shape": {"region": "str", "channel": "str"},
                    },
                ],
                "observed_payload": {"metadata": {"region": "us"}},
                "strict_unknown_fields": True,
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    api_row = _api_contract_plugin_row(result)
    assert api_row
    assert str(api_row.get("status", "")) in {"WARNING", "FAIL"}

    type_report = json.loads((pf / "validation_plugins" / "api_contract" / "api_contract" / "261_type_mismatch_report.json").read_text(encoding="utf-8"))
    rows = type_report.get("rows", []) if isinstance(type_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "PAYLOAD_SHAPE_INCOMPATIBILITY" for row in rows if isinstance(row, dict))


def test_healthy_security_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "healthy_security_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "gateway",
                "source_path": "config/gateway.yaml",
                "content": "service_url=https://api.example.com\ncrypto=sha256\n",
                "settings": {
                    "admin_host": "127.0.0.1",
                    "admin_port": "8443",
                    "allow_all": False,
                    "role": "ops_admin",
                },
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "PASS"

    secret_report = json.loads((pf / "validation_plugins" / "security" / "270_secret_detection_report.json").read_text(encoding="utf-8"))
    summary = secret_report.get("summary", {}) if isinstance(secret_report.get("summary", {}), dict) else {}
    assert int(summary.get("fail_count", 0)) == 0


def test_hardcoded_secret_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "hardcoded_secret_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "auth_service",
                "source_path": "config/auth.env",
                "content": "API_KEY=abcd1234\n",
                "settings": {"admin_host": "127.0.0.1", "admin_port": "8443"},
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    secret_report = json.loads((pf / "validation_plugins" / "security" / "270_secret_detection_report.json").read_text(encoding="utf-8"))
    rows = secret_report.get("rows", []) if isinstance(secret_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "HARD_CODED_SECRET" for row in rows if isinstance(row, dict))


def test_insecure_protocol_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "insecure_protocol_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "transport",
                "source_path": "config/transport.ini",
                "content": "upstream=http://internal.service.local\n",
                "settings": {"admin_host": "127.0.0.1", "admin_port": "8443"},
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    protocol_report = json.loads((pf / "validation_plugins" / "security" / "271_protocol_security_report.json").read_text(encoding="utf-8"))
    rows = protocol_report.get("rows", []) if isinstance(protocol_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "INSECURE_PROTOCOL_USAGE" for row in rows if isinstance(row, dict))


def test_weak_crypto_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "weak_crypto_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "crypto_service",
                "source_path": "config/crypto.toml",
                "content": "hash_algorithm=MD5\n",
                "settings": {"admin_host": "127.0.0.1", "admin_port": "8443"},
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    crypto_report = json.loads((pf / "validation_plugins" / "security" / "272_crypto_configuration_report.json").read_text(encoding="utf-8"))
    rows = crypto_report.get("rows", []) if isinstance(crypto_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "WEAK_CRYPTO_CONFIGURATION" for row in rows if isinstance(row, dict))


def test_admin_interface_exposed_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "admin_interface_exposed_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "admin_console",
                "source_path": "config/admin.yaml",
                "content": "admin_host=0.0.0.0\nadmin_port=open\n",
                "settings": {"admin_host": "0.0.0.0", "admin_port": "open"},
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    admin_report = json.loads((pf / "validation_plugins" / "security" / "273_admin_interface_report.json").read_text(encoding="utf-8"))
    rows = admin_report.get("rows", []) if isinstance(admin_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "PUBLIC_EXPOSED_ADMIN_INTERFACE" for row in rows if isinstance(row, dict))


def test_permissive_access_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "permissive_access_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "access_policy",
                "source_path": "config/policy.json",
                "content": "allow_all=true\nrole=*\n",
                "settings": {"allow_all": True, "role": "*", "admin_host": "127.0.0.1", "admin_port": "8443"},
                "headers": ["X-Frame-Options", "Content-Security-Policy", "X-Content-Type-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    access_report = json.loads((pf / "validation_plugins" / "security" / "274_access_policy_report.json").read_text(encoding="utf-8"))
    rows = access_report.get("rows", []) if isinstance(access_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "PERMISSIVE_ACCESS_POLICY" for row in rows if isinstance(row, dict))


def test_missing_security_headers_fixture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    pf = tmp_path / "proof" / "missing_security_headers_fixture"

    _seed_security_inputs(
        pf=pf,
        entries=[
            {
                "component": "web_frontend",
                "source_path": "config/web.yaml",
                "content": "service_url=https://web.example.com\n",
                "settings": {"admin_host": "127.0.0.1", "admin_port": "8443"},
                "headers": ["X-Frame-Options"],
            }
        ],
    )

    result = execute_validation_plugins(project_root=project_root, pf=pf)
    security_row = _security_plugin_row(result)
    assert security_row
    assert str(security_row.get("status", "")) == "FAIL"

    headers_report = json.loads((pf / "validation_plugins" / "security" / "275_security_headers_report.json").read_text(encoding="utf-8"))
    rows = headers_report.get("rows", []) if isinstance(headers_report.get("rows", []), list) else []
    assert any(str(row.get("risk_type", "")) == "MISSING_SECURITY_HEADERS" for row in rows if isinstance(row, dict))


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


def _seed_plan(
    *,
    project_root: Path,
    run_name: str,
    plan_class: str,
    rows: list[dict[str, object]],
    required_ids: list[str],
    optional_ids: list[str],
) -> None:
    plan_root = project_root / "_proof" / "runs" / run_name
    planning = plan_root / "planning"
    required_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(required_ids)]
    optional_rows = [row for row in rows if str(row.get("scenario_id", "")) in set(optional_ids)]

    _write_json(planning / "120_validation_plan_inputs.json", {"project_root": str(project_root.resolve()), "touched_components": ["component_a"]})
    _write_json(planning / "121_scenario_plan_ranking.json", {"rows": rows})
    _write_json(planning / "122_required_vs_optional_plan.json", {"required": required_rows, "optional": optional_rows})
    _write_json(planning / "123_component_focus_plan.json", {"rows": [{"component": "component_a", "watch_class": "NORMAL", "focus_score": 0.1}]})
    _write_json(planning / "124_plan_classification.json", {"plan_class": plan_class, "aggregate_plan_score": 0.2})


def _seed_certification_target(project_root: Path, *, baseline_score: float, current_score: float) -> None:
    cert_root = project_root / "certification" / "baseline_v1"
    _write_json(cert_root / "baseline_manifest.json", {"baseline_version": "v1", "scenario_count": 1})
    _write_json(
        cert_root / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": baseline_score,
            "average_component_ownership_accuracy": baseline_score,
            "average_root_cause_accuracy": baseline_score,
            "average_remediation_quality": baseline_score,
            "average_proof_quality": baseline_score,
            "average_diagnostic_score": baseline_score,
        },
    )
    _write_json(
        cert_root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": baseline_score,
                    "scores": {
                        "detection_accuracy": baseline_score,
                        "component_ownership_accuracy": baseline_score,
                        "root_cause_accuracy": baseline_score,
                        "remediation_quality": baseline_score,
                        "proof_quality": baseline_score,
                    },
                }
            ]
        },
    )
    _write_json(project_root / "certification" / "scenario_index.json", {"scenario_ids": ["baseline_pass"]})
    _write_json(project_root / "baseline_manifest.json", {"baseline_version": "current_run", "scenario_count": 1})
    _write_json(
        project_root / "diagnostic_metrics.json",
        {
            "average_detection_accuracy": current_score,
            "average_component_ownership_accuracy": current_score,
            "average_root_cause_accuracy": current_score,
            "average_remediation_quality": current_score,
            "average_proof_quality": current_score,
            "average_diagnostic_score": current_score,
        },
    )
    _write_json(
        project_root / "baseline_matrix.json",
        {
            "scenarios": [
                {
                    "scenario_id": "baseline_pass",
                    "scenario_name": "baseline",
                    "expected_gate": "PASS",
                    "actual_gate": "PASS",
                    "diagnostic_score": current_score,
                    "scores": {
                        "detection_accuracy": current_score,
                        "component_ownership_accuracy": current_score,
                        "root_cause_accuracy": current_score,
                        "remediation_quality": current_score,
                        "proof_quality": current_score,
                    },
                }
            ]
        },
    )
    _write_json(
        project_root / "certification_target.json",
        {
            "project_name": "PluginStageFixture",
            "target_root": ".",
            "certification_root": "certification",
            "baseline_root": "certification/baseline_v1",
            "scenario_index_path": "certification/scenario_index.json",
            "supported_baseline_versions": ["v1", "current_run"],
            "required_artifacts": ["baseline_manifest", "baseline_matrix", "diagnostic_metrics", "scenario_index"],
            "optional_artifacts": [],
            "target_type": "ngks_project",
            "schema_version": "certification_target_v1",
        },
    )


def test_pipeline_plugin_stage(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "220_plugin_execution_plan.json").is_file()
    assert (pf / "validation_plugins" / "221_plugin_results.json").is_file()
    assert (pf / "validation_plugins" / "222_plugin_summary.md").is_file()


def test_pipeline_plugin_stage_with_performance(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins_performance",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage_with_performance"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "performance" / "performance" / "230_total_runtime_report.json").is_file()
    assert (pf / "validation_plugins" / "performance" / "performance" / "231_stage_hotspots.json").is_file()
    assert (pf / "validation_plugins" / "performance" / "performance" / "232_scenario_hotspots.json").is_file()
    assert (pf / "validation_plugins" / "performance" / "performance" / "233_repeated_slow_paths.json").is_file()
    assert (pf / "validation_plugins" / "performance" / "performance" / "234_performance_recommendations.json").is_file()
    assert (pf / "validation_plugins" / "performance" / "performance" / "235_performance_summary.md").is_file()


def test_pipeline_plugin_stage_with_memory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins_memory",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage_with_memory"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "memory" / "memory" / "240_peak_memory_report.json").is_file()
    assert (pf / "validation_plugins" / "memory" / "memory" / "241_stage_memory_hotspots.json").is_file()
    assert (pf / "validation_plugins" / "memory" / "memory" / "242_memory_growth_report.json").is_file()
    assert (pf / "validation_plugins" / "memory" / "memory" / "243_repeated_high_memory_paths.json").is_file()
    assert (pf / "validation_plugins" / "memory" / "memory" / "244_memory_recommendations.json").is_file()
    assert (pf / "validation_plugins" / "memory" / "memory" / "245_memory_summary.md").is_file()


def test_pipeline_plugin_stage_with_architecture(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins_architecture",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage_with_architecture"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "250_nesting_depth_report.json").is_file()
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "251_module_size_report.json").is_file()
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "252_coupling_hotspots.json").is_file()
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "253_dependency_risk_report.json").is_file()
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "254_architecture_recommendations.json").is_file()
    assert (pf / "validation_plugins" / "architecture" / "architecture" / "255_architecture_summary.md").is_file()


def test_pipeline_plugin_stage_with_api_contract(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins_api_contract",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage_with_api_contract"
    stale_placeholder = pf / "validation_plugins" / "api_contract" / "api_contract" / "not_implemented.json"
    stale_placeholder.parent.mkdir(parents=True, exist_ok=True)
    stale_placeholder.write_text("{}", encoding="utf-8")

    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "260_required_field_report.json").is_file()
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "261_type_mismatch_report.json").is_file()
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "262_unknown_field_report.json").is_file()
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "263_version_drift_report.json").is_file()
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "264_contract_recommendations.json").is_file()
    assert (pf / "validation_plugins" / "api_contract" / "api_contract" / "265_contract_summary.md").is_file()
    assert not stale_placeholder.exists()


def test_pipeline_plugin_stage_with_security_validation(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _seed_certification_target(project_root, baseline_score=0.9, current_score=0.9)
    _seed_plan(
        project_root=project_root,
        run_name="plan_pipeline_plugins_security_validation",
        plan_class="STANDARD",
        rows=[_scenario_row("required_a", 1, 0.2, True), _scenario_row("optional_a", 2, 0.1, False)],
        required_ids=["required_a"],
        optional_ids=["optional_a"],
    )

    pf = tmp_path / "proof" / "pipeline_plugin_stage_with_security_validation"
    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=tmp_path,
        pf=pf,
        execution_policy="BALANCED",
    )

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    assert str(summary.get("validation_plugin_status", "")) in {"PASS", "WARNING", "FAIL"}
    assert (pf / "validation_plugins" / "security" / "270_secret_detection_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "271_protocol_security_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "272_crypto_configuration_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "273_admin_interface_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "274_access_policy_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "275_security_headers_report.json").is_file()
    assert (pf / "validation_plugins" / "security" / "276_security_recommendations.json").is_file()
    assert (pf / "validation_plugins" / "security" / "277_security_summary.md").is_file()


def test_run_validation_plugins_cli_entrypoint(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    snapshot = _layout_snapshot(
        tmp_path / "cli_layout_snapshot.json",
        containers=[
            {"name": "root", "type": "panel", "height": 360, "padding": 8, "spacing": 6},
            {"name": "section_a", "parent": "root", "type": "panel", "height": 140, "min_height": 140},
            {"name": "section_b", "parent": "root", "type": "panel", "height": 140, "min_height": 140},
        ],
    )

    pf_name = "validation_plugins_cli"
    rc = main(
        [
            "run-validation-plugins",
            "--project",
            str(project_root),
            "--view",
            "runtime_update_loop_scheduler",
            "--layout-snapshot",
            str(snapshot),
            "--pf",
            pf_name,
        ]
    )

    assert rc == 0
    expected_pf = DEVFABRIC_ROOT.parent.resolve() / "_proof" / "runs" / pf_name
    assert (expected_pf / "validation_plugins" / "220_plugin_execution_plan.json").is_file()
