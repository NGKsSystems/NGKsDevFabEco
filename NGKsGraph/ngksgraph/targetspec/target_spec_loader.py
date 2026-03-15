from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ngksgraph.config import Config
from ngksgraph.graph import BuildGraph
from ngksgraph.util import normalize_path

from .canonical_target_spec import derive_canonical_target_spec
from .target_spec_types import CanonicalTargetSpec


def _candidate_paths(repo_root: Path) -> list[Path]:
    return [
        (repo_root / "ngks_target_spec.json").resolve(),
        (repo_root / "ngksgraph_target_spec.json").resolve(),
        (repo_root / "ngksgraph" / "target_spec.json").resolve(),
    ]


def _to_spec(payload: dict[str, Any]) -> CanonicalTargetSpec:
    required = [str(v).strip() for v in payload.get("required_capabilities", []) if str(v).strip()]
    optional = [str(v).strip() for v in payload.get("optional_capabilities", []) if str(v).strip()]
    source_roots = [normalize_path(str(v)) for v in payload.get("source_roots", []) if str(v).strip()]
    entrypoints = [normalize_path(str(v)) for v in payload.get("entrypoints", []) if str(v).strip()]
    policy_flags = payload.get("policy_flags", {}) if isinstance(payload.get("policy_flags", {}), dict) else {}

    return CanonicalTargetSpec(
        target_name=str(payload.get("target_name", "")).strip(),
        target_type=str(payload.get("target_type", "desktop_app")).strip() or "desktop_app",
        language=str(payload.get("language", "c++")).strip() or "c++",
        platform=str(payload.get("platform", "windows")).strip() or "windows",
        configuration=str(payload.get("configuration", "debug")).strip() or "debug",
        required_capabilities=required,
        optional_capabilities=optional,
        policy_flags=policy_flags,
        source_roots=source_roots,
        entrypoints=entrypoints,
    )


def _validate_required(spec: CanonicalTargetSpec) -> None:
    missing: list[str] = []
    if not str(spec.target_name).strip():
        missing.append("target_name")
    if not str(spec.target_type).strip():
        missing.append("target_type")
    if not str(spec.language).strip():
        missing.append("language")
    if not str(spec.platform).strip():
        missing.append("platform")
    if not str(spec.configuration).strip():
        missing.append("configuration")
    if not spec.required_capabilities:
        missing.append("required_capabilities")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"TARGET_SPEC_INVALID: missing fields: {joined}")


def load_or_derive_target_spec(
    *,
    repo_root: Path,
    config: Config,
    graph: BuildGraph,
    selected_target: str,
    profile: str,
) -> tuple[CanonicalTargetSpec, str, str]:
    for candidate in _candidate_paths(repo_root):
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"TARGET_SPEC_PARSE_ERROR: {candidate}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"TARGET_SPEC_INVALID: expected object in {candidate}")
        spec = _to_spec(payload)
        _validate_required(spec)
        return spec, "explicit_file", str(candidate)

    if selected_target not in graph.targets:
        raise ValueError(f"TARGET_SPEC_DERIVE_FAILED: unknown target {selected_target}")

    spec = derive_canonical_target_spec(
        config=config,
        target=graph.targets[selected_target],
        profile=profile,
    )
    _validate_required(spec)
    return spec, "derived_from_graph", ""
