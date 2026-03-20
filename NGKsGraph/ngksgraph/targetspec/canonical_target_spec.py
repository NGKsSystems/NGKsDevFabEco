from __future__ import annotations

from pathlib import Path

from ngksgraph.config import Config
from ngksgraph.graph import Target
from ngksgraph.util import normalize_path

from .target_spec_types import CanonicalTargetSpec, TargetLanguage, TargetPlatform, TargetType


def _source_roots(sources: list[str]) -> list[str]:
    roots: set[str] = set()
    for item in sources:
        parts = Path(str(item)).parts
        if not parts:
            continue
        roots.add(normalize_path(parts[0]))
    return sorted(roots) or ["src"]


def _entrypoints(sources: list[str]) -> list[str]:
    normalized = [normalize_path(str(item)) for item in sources]
    mains = [item for item in normalized if item.lower().endswith("main.cpp")]
    if mains:
        return sorted(mains)
    return sorted(normalized[:1])


# Qt6EntryPoint is a Windows linker bootstrap library (link-only, no public include headers).
# It must not generate a qt.entrypoint capability requirement — there is no include/QtEntrypoint
# directory in any Qt installation, so the capability detector would always mark it missing.
_LINK_ONLY_QT_LIBS: frozenset[str] = frozenset({"entrypoint"})


def _required_capabilities(target: Target) -> list[str]:
    required = [
        "cxx.compiler",
        f"cxx.standard:{int(target.cxx_std)}",
        "windows.sdk",
        "msvc.linker",
    ]
    qt_modules = sorted({str(lib).strip() for lib in target.libs if str(lib).strip().lower().startswith("qt")})
    for module in qt_modules:
        module_name = module
        if module_name.lower().startswith("qt6"):
            module_name = module_name[3:]
        if module_name.lower().endswith(".lib"):
            module_name = module_name[:-4]
        if module_name and module_name.lower() not in _LINK_ONLY_QT_LIBS:
            required.append(f"qt.{module_name.lower()}")
    return sorted(set(required), key=lambda x: x)


def derive_canonical_target_spec(
    *,
    config: Config,
    target: Target,
    profile: str,
) -> CanonicalTargetSpec:
    target_type = TargetType.DESKTOP_APP.value if str(target.kind) == "exe" else TargetType.STATIC_LIBRARY.value
    optional = ["pdb.debug"]
    if str(target.toolchain.get("qt_windeployqt", "")).strip():
        optional.append("windeployqt")

    return CanonicalTargetSpec(
        target_name=str(target.name),
        target_type=target_type,
        language=TargetLanguage.CXX.value,
        platform=TargetPlatform.WINDOWS.value,
        configuration=str(profile),
        required_capabilities=_required_capabilities(target),
        optional_capabilities=sorted(set(optional)),
        policy_flags={
            "fail_on_missing_required_capability": True,
            "require_active_language_standard": True,
        },
        source_roots=_source_roots(list(target.sources)),
        entrypoints=_entrypoints(list(target.sources)),
    )
