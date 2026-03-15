from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TargetType(str, Enum):
    DESKTOP_APP = "desktop_app"
    STATIC_LIBRARY = "static_library"


class TargetLanguage(str, Enum):
    CXX = "c++"


class TargetPlatform(str, Enum):
    WINDOWS = "windows"


@dataclass(frozen=True)
class CanonicalTargetSpec:
    target_name: str
    target_type: str
    language: str
    platform: str
    configuration: str
    required_capabilities: list[str] = field(default_factory=list)
    optional_capabilities: list[str] = field(default_factory=list)
    policy_flags: dict[str, Any] = field(default_factory=dict)
    source_roots: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": str(self.target_name),
            "target_type": str(self.target_type),
            "language": str(self.language),
            "platform": str(self.platform),
            "configuration": str(self.configuration),
            "required_capabilities": [str(v) for v in self.required_capabilities],
            "optional_capabilities": [str(v) for v in self.optional_capabilities],
            "policy_flags": dict(self.policy_flags),
            "source_roots": [str(v) for v in self.source_roots],
            "entrypoints": [str(v) for v in self.entrypoints],
        }
