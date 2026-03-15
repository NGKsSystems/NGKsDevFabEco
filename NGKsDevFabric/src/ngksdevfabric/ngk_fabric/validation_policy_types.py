from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationPluginPolicy:
    plugin_name: str
    plugin_category: str
    trigger_stages: tuple[str, ...]
    required_artifact_types: tuple[str, ...]
    required_project_capabilities: tuple[str, ...]
    required_languages: tuple[str, ...]
    required_target_types: tuple[str, ...]
    mode: str
    severity: str
    default_enabled: bool
    blocking_stages: tuple[str, ...]
    advisory_stages: tuple[str, ...]
