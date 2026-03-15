from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ngksgraph.capability.capability_reporter import inventory_payload
from ngksgraph.capability.capability_types import CapabilityInventory
from ngksgraph.targetspec.target_spec_types import CanonicalTargetSpec

from .target_resolution_types import ResolutionReport


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _recommendations(report: ResolutionReport) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in report.missing + report.downgraded + report.conflicting:
        capability = row.capability
        if capability.startswith("qt."):
            action = "Install or enable the required Qt module and ensure Qt include/lib roots are configured."
        elif capability.startswith("cxx.standard:"):
            action = "Set the target C++ standard explicitly in ngksgraph target config (cxx_std) to meet required capability."
        elif capability == "msvc.linker":
            action = "Install MSVC Build Tools linker components and run from a valid VS developer environment."
        elif capability == "windows.sdk":
            action = "Install Windows SDK 10+ and verify Include path is present."
        elif capability == "cxx.compiler":
            action = "Install MSVC C++ compiler toolset and verify cl.exe is discoverable."
        else:
            action = "Provide the missing required capability in toolchain or project configuration."
        out.append(
            {
                "capability": capability,
                "classification": row.classification,
                "recommendation": action,
            }
        )
    return out


def write_resolution_artifacts(
    *,
    output_dir: Path,
    target_spec: CanonicalTargetSpec,
    inventory: CapabilityInventory,
    report: ResolutionReport,
    spec_source: str,
    spec_path: str,
) -> dict[str, str]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths = {
        "10_target_spec.json": output_dir / "10_target_spec.json",
        "11_capability_inventory.json": output_dir / "11_capability_inventory.json",
        "12_required_vs_available.json": output_dir / "12_required_vs_available.json",
        "13_capability_conflicts.json": output_dir / "13_capability_conflicts.json",
        "14_resolution_report.json": output_dir / "14_resolution_report.json",
        "15_build_plan_resolution_context.json": output_dir / "15_build_plan_resolution_context.json",
        "16_fix_recommendations.json": output_dir / "16_fix_recommendations.json",
        "17_resolution_summary.md": output_dir / "17_resolution_summary.md",
    }

    _write_json(
        artifact_paths["10_target_spec.json"],
        {
            "target_spec": target_spec.to_dict(),
            "source": spec_source,
            "path": spec_path,
        },
    )

    _write_json(
        artifact_paths["11_capability_inventory.json"],
        inventory_payload(inventory),
    )

    _write_json(
        artifact_paths["12_required_vs_available.json"],
        {
            "required": list(target_spec.required_capabilities),
            "resolved": [row.to_dict() for row in report.resolved],
            "missing": [row.to_dict() for row in report.missing],
            "downgraded": [row.to_dict() for row in report.downgraded],
            "optional_missing": [row.to_dict() for row in report.optional_missing],
            "inferred": [row.to_dict() for row in report.inferred],
        },
    )

    _write_json(
        artifact_paths["13_capability_conflicts.json"],
        {
            "rows": [row.to_dict() for row in report.conflicting],
            "count": len(report.conflicting),
        },
    )

    resolution_dict = report.to_dict()
    _write_json(artifact_paths["14_resolution_report.json"], resolution_dict)

    _write_json(
        artifact_paths["15_build_plan_resolution_context.json"],
        {
            "target_name": target_spec.target_name,
            "build_allowed": report.build_allowed,
            "required_capabilities": list(target_spec.required_capabilities),
            "blocking_capabilities": [
                row.capability for row in (report.missing + report.conflicting + report.downgraded)
            ],
            "policy_flags": dict(target_spec.policy_flags),
        },
    )

    recommendations = _recommendations(report)
    _write_json(
        artifact_paths["16_fix_recommendations.json"],
        {
            "rows": recommendations,
            "count": len(recommendations),
        },
    )

    lines = [
        "# Capability Resolution Summary",
        "",
        f"- target_name: {target_spec.target_name}",
        f"- spec_source: {spec_source}",
        f"- build_allowed: {report.build_allowed}",
        f"- resolved_count: {len(report.resolved)}",
        f"- missing_count: {len(report.missing)}",
        f"- conflicting_count: {len(report.conflicting)}",
        f"- downgraded_count: {len(report.downgraded)}",
        f"- optional_missing_count: {len(report.optional_missing)}",
        "",
        "## Blocking Capabilities",
    ]
    blocking = report.missing + report.conflicting + report.downgraded
    if blocking:
        for row in blocking:
            lines.append(f"- capability={row.capability} classification={row.classification} detail={row.detail}")
    else:
        lines.append("- none")

    _write_text(artifact_paths["17_resolution_summary.md"], "\n".join(lines) + "\n")

    return {name: str(path) for name, path in artifact_paths.items()}
