from __future__ import annotations

import platform

from .errors import MissingRequiredError, VerifyFailedError
from .registry import PROVIDER_GROUP, PROVIDER_ORDER
from .types import Candidate, Constraint, HostContext, Selection


def _sort_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (c.version, c.id), reverse=True)


def build_host_context() -> HostContext:
    machine = platform.machine().lower()
    arch = "x64" if machine in {"amd64", "x86_64"} else machine
    os_name = "windows" if platform.system().lower().startswith("win") else platform.system().lower()
    return HostContext(os=os_name, arch=arch)


def collect_candidates(registry: dict[str, object], host: HostContext) -> dict[str, list[Candidate]]:
    output: dict[str, list[Candidate]] = {}
    for key in PROVIDER_ORDER:
        provider = registry[key]
        output[key] = _sort_candidates(provider.detect(host))
    return output


def resolve_capsule(
    constraints: dict[str, Constraint],
    registry: dict[str, object],
    host: HostContext,
    auto_provision: bool = False,
    proof_dir: str = "",
) -> tuple[dict, dict[str, Selection], list[str]]:
    candidates_map = collect_candidates(registry, host)
    selections: dict[str, Selection] = {}
    errors: list[str] = []

    payload = {
        "capsule_version": 1,
        "host": {"os": host.os, "arch": host.arch},
        "toolchains": {},
        "runtimes": {},
    }

    for key in PROVIDER_ORDER:
        provider = registry[key]
        constraint = constraints[key]
        selection = provider.select(constraint, candidates_map[key])

        if selection.status == "missing_required" and auto_provision and hasattr(provider, "provision"):
            selection = provider.provision(constraint, host, proof_dir)

        selections[key] = selection
        if selection.status in {"missing_required", "mismatch"}:
            errors.append(selection.reason or f"{key} resolution failed")
            continue
        if selection.status != "selected":
            continue

        facts = provider.fingerprint(selection) or {}
        group = PROVIDER_GROUP[key]
        payload[group][key] = facts

    return payload, selections, errors


def verify_capsule(lock_payload: dict, registry: dict[str, object], host: HostContext) -> tuple[bool, list[str]]:
    errors: list[str] = []

    for section in ["runtimes", "toolchains"]:
        entries = lock_payload.get(section, {})
        for key in sorted(entries.keys()):
            provider = registry[key]
            ok, reason = provider.verify(entries[key], host)
            if not ok:
                errors.append(reason or f"{key} verification failed")

    if errors:
        return False, errors
    return True, []


def raise_for_resolution_errors(errors: list[str]) -> None:
    if errors:
        raise MissingRequiredError("; ".join(errors))


def raise_for_verify_errors(errors: list[str]) -> None:
    if errors:
        raise VerifyFailedError("; ".join(errors))
