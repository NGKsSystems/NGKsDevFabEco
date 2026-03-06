from __future__ import annotations

import os
import shutil
from pathlib import Path

from ngksgraph.config import load_config
from ngksgraph.qt import resolve_qt_toolchain

from ngksgraph.msvc import bootstrap_msvc


def _exists_on_path(tool_name: str) -> bool:
    return shutil.which(tool_name) is not None


def _exists_on_env_path(tool_name: str, env_path: str | None) -> bool:
    return shutil.which(tool_name, path=env_path) is not None


def _get_env_path_case_insensitive(env: dict[str, str]) -> str | None:
    for key, value in env.items():
        if key.upper() == "PATH":
            return value
    return None


def detect_toolchain() -> dict[str, bool]:
    return {
        "cl": _exists_on_path("cl"),
        "link": _exists_on_path("link"),
        "vcvars": "VSCMD_VER" in os.environ,
    }


def doctor_report(msvc_auto: bool = False) -> tuple[bool, list[str]]:
    status = detect_toolchain()
    lines = [
        f"cl: {'ok' if status['cl'] else 'missing'}",
        f"link: {'ok' if status['link'] else 'missing'}",
        f"MSVC prompt (VSCMD_VER): {'yes' if status['vcvars'] else 'no'}",
    ]

    effective_cl = status["cl"]
    effective_link = status["link"]
    if msvc_auto and (not status["cl"] or not status["link"]):
        boot = bootstrap_msvc()
        lines.append(f"vswhere found: {'yes' if boot.vswhere_path else 'no'}")
        lines.append(f"VS path: {boot.vs_install_path or '<none>'}")
        lines.append(f"VsDevCmd path: {boot.vsdevcmd_path or '<none>'}")
        lines.append(f"bootstrap: {'success' if boot.success else 'failure'}")
        if boot.error:
            lines.append(f"bootstrap error: {boot.error}")
        if boot.env:
            env_path = _get_env_path_case_insensitive(boot.env)
            effective_cl = _exists_on_env_path("cl", env_path)
            effective_link = _exists_on_env_path("link", env_path)
            lines.append(f"bootstrap cl: {'ok' if effective_cl else 'missing'}")
            lines.append(f"bootstrap link: {'ok' if effective_link else 'missing'}")

    ok = effective_cl and effective_link
    if not ok:
        if msvc_auto:
            lines.append("MSVC still unavailable after auto-bootstrap. Install VC tools or use Native Tools prompt.")
        else:
            lines.append("Run from x64 Native Tools Command Prompt with MSVC tools installed.")
    return ok, lines


def doctor_toolchain_report(config_path: Path, profile: str | None = None) -> tuple[bool, list[str], bool]:
    lines: list[str] = []
    cl_ok = _exists_on_path("cl")
    link_ok = _exists_on_path("link")
    lines.append(f"cl: {'ok' if cl_ok else 'missing'}")
    lines.append(f"link: {'ok' if link_ok else 'missing'}")

    cfg = load_config(config_path)
    selected_profile = cfg.apply_profile(profile)
    lines.append(f"profile: {selected_profile}")

    corrupt = False
    qt_ok = True
    if cfg.qt.enabled:
        try:
            info = resolve_qt_toolchain(cfg, check_exists=True)
            resolved = info.get("resolved", {}) if isinstance(info.get("resolved", {}), dict) else {}
            lines.append(f"qt.moc: {resolved.get('moc_path', '')}")
            lines.append(f"qt.uic: {resolved.get('uic_path', '')}")
            lines.append(f"qt.rcc: {resolved.get('rcc_path', '')}")
            include_dirs = resolved.get("include_dirs", []) if isinstance(resolved.get("include_dirs", []), list) else []
            lib_dirs = resolved.get("lib_dirs", []) if isinstance(resolved.get("lib_dirs", []), list) else []
            libs = resolved.get("libs", []) if isinstance(resolved.get("libs", []), list) else []
            includes_ok = all(Path(v).exists() for v in include_dirs)
            libdirs_ok = all(Path(v).exists() for v in lib_dirs)
            lines.append(f"qt.include_dirs: {'ok' if includes_ok else 'missing'}")
            lines.append(f"qt.lib_dirs: {'ok' if libdirs_ok else 'missing'}")
            lines.append(f"qt.libs: {', '.join(libs)}")
            qt_ok = includes_ok and libdirs_ok
        except Exception as exc:
            qt_ok = False
            lines.append(f"qt.error: {exc}")
    else:
        lines.append("qt: disabled")

    ok = cl_ok and link_ok and qt_ok
    return ok, lines, corrupt
