from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FailureStage = Literal[
    "WORKSPACE_INTEGRITY_FAILURE",
    "GRAPH_STATE_FAILURE",
    "GRAPH_REFRESH_FAILURE",
    "TARGET_SPEC_FAILURE",
    "CAPABILITY_RESOLUTION_FAILURE",
    "VALIDATION_POLICY_BLOCK",
    "VALIDATION_PLUGIN_FAILURE",
    "COMMAND_DISPATCH_FAILURE",
    "PROFILE_LOAD_FAILURE",
    "BUILDCORE_EXECUTION_FAILURE",
    "COMPILER_FAILURE",
    "LINKER_FAILURE",
    "PACKAGING_FAILURE",
    "UNKNOWN_FAILURE",
]


@dataclass(frozen=True)
class RootCauseClassification:
    failure_stage: FailureStage
    root_cause_code: str
    summary: str
    evidence_refs: tuple[str, ...]
    recommended_fix: str
    confidence_score: float
    blocking: bool
    source_layer: str


@dataclass(frozen=True)
class RootCauseInputContext:
    project_root: str
    proof_dir: str
    command_name: str
    stage_hint: str
    failure_reason: str
    exit_code: int
    buildcore_reached: bool
    failed_before_validation_gate: bool
    failed_after_validation_gate: bool
    stderr_excerpt: str
    stdout_excerpt: str
