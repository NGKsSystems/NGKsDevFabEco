from __future__ import annotations

from ngksgraph.capability.capability_types import CapabilityInventory
from ngksgraph.targetspec.target_spec_types import CanonicalTargetSpec

from .target_resolution_types import ResolutionReport, ResolutionRow


def _parse_standard(capability: str) -> int | None:
    text = str(capability).strip().lower()
    if not text.startswith("cxx.standard:"):
        return None
    raw = text.split(":", 1)[1].strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _row(
    capability: str,
    classification: str,
    required: bool,
    status: str,
    detail: str,
    detected_version: str = "",
    metadata: dict | None = None,
) -> ResolutionRow:
    return ResolutionRow(
        capability=capability,
        classification=classification,
        required=required,
        status=status,
        detail=detail,
        detected_version=detected_version,
        metadata=dict(metadata or {}),
    )


def resolve_target_capabilities(*, target_spec: CanonicalTargetSpec, inventory: CapabilityInventory) -> ResolutionReport:
    resolved: list[ResolutionRow] = []
    missing: list[ResolutionRow] = []
    conflicting: list[ResolutionRow] = []
    downgraded: list[ResolutionRow] = []
    optional_missing: list[ResolutionRow] = []
    inferred: list[ResolutionRow] = []

    for required_capability in list(target_spec.required_capabilities):
        standard_required = _parse_standard(required_capability)
        if standard_required is not None:
            active_std = inventory.by_name("cxx.standard.active")
            compiler = inventory.by_name("cxx.compiler")
            if compiler is not None and compiler.status == "available":
                inferred.append(
                    _row(
                        "cxx.compiler",
                        "inferred",
                        True,
                        "available",
                        "Compiler present; validating active language standard separately.",
                        detected_version=str(compiler.version),
                        metadata=compiler.metadata,
                    )
                )
            if active_std is None or active_std.status != "available":
                missing.append(
                    _row(
                        required_capability,
                        "missing",
                        True,
                        "missing",
                        "Required C++ standard cannot be satisfied because active standard is not configured.",
                    )
                )
                continue

            try:
                active_version = int(str(active_std.version).strip())
            except ValueError:
                active_version = 0

            if active_version < standard_required:
                downgraded.append(
                    _row(
                        required_capability,
                        "downgraded",
                        True,
                        "downgraded",
                        f"Active C++ standard ({active_version}) is below required ({standard_required}).",
                        detected_version=str(active_version),
                    )
                )
            else:
                resolved.append(
                    _row(
                        required_capability,
                        "resolved",
                        True,
                        "available",
                        "Required C++ language standard is configured and satisfied.",
                        detected_version=str(active_version),
                    )
                )
            continue

        record = inventory.by_name(required_capability)
        if record is None:
            missing.append(
                _row(
                    required_capability,
                    "missing",
                    True,
                    "missing",
                    "Required capability was not detected in capability inventory.",
                )
            )
            continue

        if record.status == "available":
            resolved.append(
                _row(
                    required_capability,
                    "resolved",
                    True,
                    "available",
                    "Required capability is available.",
                    detected_version=record.version,
                    metadata=record.metadata,
                )
            )
        elif record.status == "conflicting":
            conflicting.append(
                _row(
                    required_capability,
                    "conflicting",
                    True,
                    "conflicting",
                    "Required capability has conflicting providers or versions.",
                    detected_version=record.version,
                    metadata=record.metadata,
                )
            )
        else:
            missing.append(
                _row(
                    required_capability,
                    "missing",
                    True,
                    record.status,
                    "Required capability is unavailable.",
                    detected_version=record.version,
                    metadata=record.metadata,
                )
            )

    for optional_capability in list(target_spec.optional_capabilities):
        record = inventory.by_name(optional_capability)
        if record is None or record.status != "available":
            optional_missing.append(
                _row(
                    optional_capability,
                    "optional_missing",
                    False,
                    "missing",
                    "Optional capability is unavailable; build may continue.",
                )
            )

    build_allowed = not bool(missing or conflicting or downgraded)
    return ResolutionReport(
        target_name=target_spec.target_name,
        build_allowed=build_allowed,
        resolved=resolved,
        missing=missing,
        conflicting=conflicting,
        downgraded=downgraded,
        optional_missing=optional_missing,
        inferred=inferred,
    )
