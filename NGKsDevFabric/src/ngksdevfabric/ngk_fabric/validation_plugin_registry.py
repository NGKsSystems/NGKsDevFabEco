from __future__ import annotations

from pathlib import Path
from typing import Any

from .api_contract_validation import APIContractValidationPlugin
from .architectural_complexity_validation import ArchitecturalComplexityValidationPlugin
from .devfabeco_validation_plugins import ValidationPlugin, read_json, write_json, write_text
from .memory_usage_validation import MemoryUsageValidationPlugin
from .performance_bottleneck_validation import PerformanceBottleneckValidationPlugin
from .security_misconfiguration_validation import SecurityMisconfigurationValidationPlugin
from .ui_layout_integrity_validation import UILayoutIntegrityValidationPlugin


class ValidationPluginRegistry:
    def __init__(self) -> None:
        self._plugins: list[type[ValidationPlugin]] = []

    def register_plugin(self, plugin_cls: type[ValidationPlugin]) -> None:
        if plugin_cls not in self._plugins:
            self._plugins.append(plugin_cls)

    def discover_available_plugins(self) -> list[type[ValidationPlugin]]:
        self.register_plugin(UILayoutIntegrityValidationPlugin)
        self.register_plugin(PerformanceBottleneckValidationPlugin)
        self.register_plugin(MemoryUsageValidationPlugin)
        self.register_plugin(ArchitecturalComplexityValidationPlugin)
        self.register_plugin(APIContractValidationPlugin)
        self.register_plugin(SecurityMisconfigurationValidationPlugin)
        return list(self._plugins)

    def run_plugins(
        self,
        *,
        context: dict[str, Any],
        output_root: Path,
        selected_plugin_names: list[str] | None = None,
    ) -> dict[str, Any]:
        plugin_classes = self.discover_available_plugins()
        selected_set = {
            str(name).strip()
            for name in list(selected_plugin_names or [])
            if str(name).strip()
        }
        if selected_set:
            plugin_classes = [cls for cls in plugin_classes if cls.plugin_name in selected_set]
        output_root.mkdir(parents=True, exist_ok=True)

        execution_plan = {
            "stage": "POST_CERTIFICATION_VALIDATION_PLUGINS",
            "plugin_order": [
                {
                    "plugin_name": cls.plugin_name,
                    "plugin_version": cls.plugin_version,
                    "plugin_category": cls.plugin_category,
                }
                for cls in plugin_classes
            ],
        }
        write_json(output_root / "220_plugin_execution_plan.json", execution_plan)

        result_rows: list[dict[str, Any]] = []
        artifact_rows: list[str] = ["validation_plugins/220_plugin_execution_plan.json"]

        for plugin_cls in plugin_classes:
            plugin = plugin_cls()
            plugin_context = dict(context)
            plugin_context["plugin_output_root"] = str(output_root.resolve())

            status = "PASS"
            message = ""
            artifacts: list[str] = []
            summary_line = ""
            try:
                plugin.load_inputs(plugin_context)
                analysis = plugin.run_analysis()
                plugin_status = str((analysis if isinstance(analysis, dict) else {}).get("status", "PASS")).strip().upper()
                status = plugin_status or "PASS"
                plugin_folder = output_root / (
                    "ui_layout"
                    if plugin_cls.plugin_name == "ui_layout_integrity"
                    else plugin_cls.plugin_name.replace("_validation", "")
                )
                artifacts = plugin.generate_artifacts(plugin_folder)
                summary_line = plugin.generate_summary()
            except Exception as exc:  # pragma: no cover - failure path still emits deterministic records
                status = "FAIL"
                message = str(exc)
                summary_line = f"plugin={plugin_cls.plugin_name} status=FAIL message={message}"

            result_row = {
                "plugin_name": plugin_cls.plugin_name,
                "plugin_version": plugin_cls.plugin_version,
                "plugin_category": plugin_cls.plugin_category,
                "status": status,
                "message": message,
                "summary": summary_line,
                "artifacts": [str(item) for item in artifacts if str(item)],
            }
            result_rows.append(result_row)
            artifact_rows.extend(result_row["artifacts"])

        fail_count = sum(1 for row in result_rows if str(row.get("status", "")).upper() == "FAIL")
        warning_count = sum(1 for row in result_rows if str(row.get("status", "")).upper() == "WARNING")
        not_implemented_count = sum(1 for row in result_rows if str(row.get("status", "")).upper() == "NOT_IMPLEMENTED")

        overall_status = "PASS"
        if fail_count > 0:
            overall_status = "FAIL"
        elif warning_count > 0:
            overall_status = "WARNING"

        write_json(
            output_root / "221_plugin_results.json",
            {
                "stage": "POST_CERTIFICATION_VALIDATION_PLUGINS",
                "overall_status": overall_status,
                "fail_count": fail_count,
                "warning_count": warning_count,
                "not_implemented_count": not_implemented_count,
                "rows": result_rows,
            },
        )

        lines = [
            "# Validation Plugin Summary",
            "",
            f"- stage: POST_CERTIFICATION_VALIDATION_PLUGINS",
            f"- overall_status: {overall_status}",
            f"- plugin_count: {len(result_rows)}",
            f"- fail_count: {fail_count}",
            f"- warning_count: {warning_count}",
            f"- not_implemented_count: {not_implemented_count}",
            "",
            "## Plugin Results",
        ]
        if result_rows:
            for row in result_rows:
                lines.append(
                    "- plugin="
                    + str(row.get("plugin_name", ""))
                    + " status="
                    + str(row.get("status", ""))
                    + " category="
                    + str(row.get("plugin_category", ""))
                )
        else:
            lines.append("- no plugins executed")

        write_text(output_root / "222_plugin_summary.md", "\n".join(lines) + "\n")
        artifact_rows.extend([
            "validation_plugins/221_plugin_results.json",
            "validation_plugins/222_plugin_summary.md",
        ])

        return {
            "stage": "POST_CERTIFICATION_VALIDATION_PLUGINS",
            "summary": {
                "overall_status": overall_status,
                "plugin_count": len(result_rows),
                "fail_count": fail_count,
                "warning_count": warning_count,
                "not_implemented_count": not_implemented_count,
            },
            "rows": result_rows,
            "artifacts": [str(item) for item in artifact_rows if str(item)],
        }


def execute_validation_plugins(
    *,
    project_root: Path,
    pf: Path,
    view_name: str = "runtime_default_view",
    layout_snapshot_path: Path | None = None,
    selected_plugin_names: list[str] | None = None,
) -> dict[str, Any]:
    registry = ValidationPluginRegistry()

    snapshot_payload = {}
    if layout_snapshot_path is not None:
        candidate = (
            layout_snapshot_path.resolve()
            if layout_snapshot_path.is_absolute()
            else (project_root / layout_snapshot_path).resolve()
        )
        snapshot_payload = read_json(candidate)

    context = {
        "project_root": str(project_root.resolve()),
        "pf": str(pf.resolve()),
        "view_name": str(view_name),
        "layout_snapshot_path": str(layout_snapshot_path.resolve()) if layout_snapshot_path is not None else "",
        "layout_snapshot": snapshot_payload,
    }
    return registry.run_plugins(
        context=context,
        output_root=pf / "validation_plugins",
        selected_plugin_names=selected_plugin_names,
    )
