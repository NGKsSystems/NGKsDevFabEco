from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolutionRow:
    capability: str
    classification: str
    required: bool
    status: str
    detail: str
    detected_version: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": str(self.capability),
            "classification": str(self.classification),
            "required": bool(self.required),
            "status": str(self.status),
            "detail": str(self.detail),
            "detected_version": str(self.detected_version),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ResolutionReport:
    target_name: str
    build_allowed: bool
    resolved: list[ResolutionRow]
    missing: list[ResolutionRow]
    conflicting: list[ResolutionRow]
    downgraded: list[ResolutionRow]
    optional_missing: list[ResolutionRow]
    inferred: list[ResolutionRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": str(self.target_name),
            "build_allowed": bool(self.build_allowed),
            "resolved": [row.to_dict() for row in self.resolved],
            "missing": [row.to_dict() for row in self.missing],
            "conflicting": [row.to_dict() for row in self.conflicting],
            "downgraded": [row.to_dict() for row in self.downgraded],
            "optional_missing": [row.to_dict() for row in self.optional_missing],
            "inferred": [row.to_dict() for row in self.inferred],
            "summary": {
                "resolved_count": len(self.resolved),
                "missing_count": len(self.missing),
                "conflicting_count": len(self.conflicting),
                "downgraded_count": len(self.downgraded),
                "optional_missing_count": len(self.optional_missing),
                "inferred_count": len(self.inferred),
            },
        }
