from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROFILE_CONFIG_FILENAME = "devfabeco_profile.json"
_PROFILE_NAMES = ("SMALL", "STANDARD", "ENTERPRISE")

_SUBSYSTEM_ORDER: tuple[str, ...] = (
    "compare",
    "gate",
    "hotspot_analysis",
    "remediation_guidance",
    "ownership_confidence",
    "assignment_policy",
    "triage_tickets",
    "export_adapters",
    "delivery_payload_adapters",
)

_PROFILE_ENABLED_SUBSYSTEMS: dict[str, tuple[str, ...]] = {
    "SMALL": (
        "compare",
        "gate",
    ),
    "STANDARD": (
        "compare",
        "gate",
        "hotspot_analysis",
        "remediation_guidance",
        "ownership_confidence",
        "assignment_policy",
        "triage_tickets",
        "export_adapters",
    ),
    "ENTERPRISE": _SUBSYSTEM_ORDER,
}

_PROFILE_ARTIFACT_SCALING: dict[str, str] = {
    "SMALL": "minimal",
    "STANDARD": "diagnostic",
    "ENTERPRISE": "full",
}


@dataclass(frozen=True)
class ExecutionProfileState:
    profile_name: str
    project_root: Path
    config_path: Path
    config_loaded: bool
    warnings: tuple[str, ...]
    enabled_subsystems: dict[str, bool]
    activation_order: tuple[str, ...]
    artifact_scaling: str

    def is_enabled(self, subsystem: str) -> bool:
        return bool(self.enabled_subsystems.get(subsystem, False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "project_root": str(self.project_root.resolve()),
            "config_path": str(self.config_path.resolve()),
            "config_loaded": self.config_loaded,
            "warnings": list(self.warnings),
            "artifact_scaling": self.artifact_scaling,
            "activation_order": list(self.activation_order),
            "enabled_subsystems": dict(self.enabled_subsystems),
        }


def _normalize_profile_name(raw_name: object) -> str:
    candidate = str(raw_name or "").strip().upper()
    if candidate in _PROFILE_NAMES:
        return candidate
    return "STANDARD"


def _load_profile_config(config_path: Path) -> tuple[bool, dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not config_path.is_file():
        return False, {}, warnings

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        warnings.append("execution_profile_config_invalid_json_defaulted_to_STANDARD")
        return False, {}, warnings

    if not isinstance(loaded, dict):
        warnings.append("execution_profile_config_invalid_object_defaulted_to_STANDARD")
        return False, {}, warnings

    return True, loaded, warnings


def load_execution_profile(*, project_root: Path, explicit_config_path: Path | None = None) -> ExecutionProfileState:
    resolved_root = project_root.resolve()
    config_path = explicit_config_path.resolve() if explicit_config_path else (resolved_root / _PROFILE_CONFIG_FILENAME)

    config_loaded, payload, warnings = _load_profile_config(config_path)
    requested_name = payload.get("execution_profile", "STANDARD") if payload else "STANDARD"
    profile_name = _normalize_profile_name(requested_name)

    if str(requested_name or "").strip() and str(requested_name).strip().upper() not in _PROFILE_NAMES:
        warnings.append("execution_profile_value_invalid_defaulted_to_STANDARD")

    enabled = set(_PROFILE_ENABLED_SUBSYSTEMS.get(profile_name, _PROFILE_ENABLED_SUBSYSTEMS["STANDARD"]))
    enabled_subsystems = {name: name in enabled for name in _SUBSYSTEM_ORDER}

    return ExecutionProfileState(
        profile_name=profile_name,
        project_root=resolved_root,
        config_path=config_path,
        config_loaded=config_loaded,
        warnings=tuple(sorted(set(warnings))),
        enabled_subsystems=enabled_subsystems,
        activation_order=_SUBSYSTEM_ORDER,
        artifact_scaling=_PROFILE_ARTIFACT_SCALING.get(profile_name, "diagnostic"),
    )
