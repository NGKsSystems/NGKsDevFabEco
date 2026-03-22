from __future__ import annotations

import shutil
from pathlib import Path

from ngksgraph.config import Config
from ngksgraph.graph import Target
from ngksgraph.msvc import resolve_msvc_toolchain_paths

from .capability_types import CapabilityRecord


def _record(name: str, provider: str, version: str, status: str, metadata: dict[str, object] | None = None) -> CapabilityRecord:
    return CapabilityRecord(
        capability_name=name,
        provider=provider,
        version=version,
        status=status,
        metadata=dict(metadata or {}),
    )


def _normalize_qt_module_token(token: str) -> str:
    normalized = str(token or "").strip()
    if not normalized:
        return ""
    if normalized.lower().startswith("qt6") or normalized.lower().startswith("qt5"):
        normalized = normalized[3:]
    if normalized.lower().endswith(".lib"):
        normalized = normalized[:-4]
    # MSVC debug Qt libs append lowercase 'd' (Qt6Guid.lib -> Qt6Gui semantics).
    if normalized.endswith("d"):
        normalized = normalized[:-1]
    return normalized.lower().strip()


def _qt_include_dir_name(module: str) -> str:
    key = str(module or "").strip().lower()
    mapping = {
        "printsupport": "PrintSupport",
        "quickcontrols2": "QuickControls2",
        "openglwidgets": "OpenGLWidgets",
        "multimediawidgets": "MultimediaWidgets",
        "websockets": "WebSockets",
        "webchannel": "WebChannel",
        "webengine": "WebEngine",
        "webenginecore": "WebEngineCore",
        "webenginewidgets": "WebEngineWidgets",
        "webenginequick": "WebEngineQuick",
    }
    if key in mapping:
        return mapping[key]
    if not key:
        return ""
    return key[0].upper() + key[1:]


def detect_compiler_capabilities(target: Target) -> list[CapabilityRecord]:
    tool_paths = resolve_msvc_toolchain_paths(None)
    records: list[CapabilityRecord] = []

    compiler_available = bool(tool_paths.cl_path and Path(tool_paths.cl_path).exists())
    linker_available = bool(tool_paths.link_path and Path(tool_paths.link_path).exists())

    records.append(
        _record(
            "cxx.compiler",
            "MSVC",
            "",
            "available" if compiler_available else "missing",
            {"cl_path": tool_paths.cl_path, "source": tool_paths.source},
        )
    )
    records.append(
        _record(
            "msvc.linker",
            "MSVC",
            "",
            "available" if linker_available else "missing",
            {"link_path": tool_paths.link_path, "source": tool_paths.source},
        )
    )

    active_standard = int(getattr(target, "cxx_std", 0) or 0)
    if compiler_available:
        max_supported = 23
        records.append(
            _record(
                "cxx.standard.max",
                "MSVC",
                str(max_supported),
                "available",
                {"max_supported_standard": max_supported},
            )
        )
    else:
        records.append(_record("cxx.standard.max", "MSVC", "", "missing", {}))

    if active_standard > 0:
        records.append(
            _record(
                "cxx.standard.active",
                "BuildConfig",
                str(active_standard),
                "available",
                {"configured_standard": active_standard},
            )
        )
    else:
        records.append(_record("cxx.standard.active", "BuildConfig", "", "missing", {"reason": "not_configured"}))

    return records


def detect_windows_sdk_capability() -> CapabilityRecord:
    sdk_dir = Path(r"C:\Program Files (x86)\Windows Kits\10")
    include_dir = sdk_dir / "Include"
    available = include_dir.exists() and include_dir.is_dir()
    version = ""
    if available:
        try:
            versions = sorted([p.name for p in include_dir.iterdir() if p.is_dir()])
            version = versions[-1] if versions else ""
        except OSError:
            version = ""
    return _record(
        "windows.sdk",
        "WindowsSDK",
        version,
        "available" if available else "missing",
        {"include_root": str(include_dir.resolve()) if include_dir.exists() else str(include_dir)},
    )


def detect_debug_symbols_capability() -> CapabilityRecord:
    pdb_supported = bool(shutil.which("link") or shutil.which("link.exe"))
    return _record(
        "pdb.debug",
        "MSVC",
        "",
        "available" if pdb_supported else "missing",
        {},
    )


def detect_qt_capabilities(config: Config, target: Target) -> list[CapabilityRecord]:
    qt_records: list[CapabilityRecord] = []
    qt_root = Path(str(config.qt.qt_root).strip()) if str(config.qt.qt_root).strip() else None

    required_modules: set[str] = set()
    for lib in list(target.libs):
        item = str(lib).strip()
        if not item:
            continue
        if item.lower().startswith("qt"):
            normalized = _normalize_qt_module_token(item)
            if normalized:
                required_modules.add(normalized)

    declared_modules = {str(module).strip().lower() for module in list(config.qt.modules) if str(module).strip()}
    required_modules |= declared_modules

    include_root = qt_root / "include" if qt_root is not None else None
    for module in sorted(required_modules):
        module_dir_name = _qt_include_dir_name(module)
        candidate_dir = (include_root / f"Qt{module_dir_name}") if include_root is not None else None
        available = bool(candidate_dir and candidate_dir.exists())
        qt_records.append(
            _record(
                f"qt.{module}",
                "Qt",
                str(config.qt.version or ""),
                "available" if available else "missing",
                {
                    "qt_root": str(qt_root) if qt_root is not None else "",
                    "include_root": str(include_root) if include_root is not None else "",
                    "module_dir": str(candidate_dir) if candidate_dir is not None else "",
                },
            )
        )

    windeploy_path = str(target.toolchain.get("qt_windeployqt", "")).strip()
    has_windeploy = bool(windeploy_path and Path(windeploy_path).exists())
    qt_records.append(
        _record(
            "windeployqt",
            "Qt",
            str(config.qt.version or ""),
            "available" if has_windeploy else "missing",
            {"windeployqt_path": windeploy_path},
        )
    )

    return qt_records
