from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class HostContext:
    os: str
    arch: str


@dataclass(frozen=True)
class Constraint:
    strategy: str
    version: str | None = None
    min_version: str | None = None
    identity: str | None = None
    arch: str | None = None
    channel: str | None = None


@dataclass(frozen=True)
class Candidate:
    id: str
    version: str
    meta: dict


SelectionStatus = Literal["selected", "not_selected", "missing_required", "mismatch"]


@dataclass(frozen=True)
class Selection:
    provider: str
    status: SelectionStatus
    selected: Candidate | None = None
    reason: str | None = None


@dataclass
class CapsuleFacts:
    host: dict = field(default_factory=dict)
    runtimes: dict = field(default_factory=dict)
    toolchains: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "runtimes": self.runtimes,
            "toolchains": self.toolchains,
            "inputs": self.inputs,
        }
