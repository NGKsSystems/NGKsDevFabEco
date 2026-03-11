from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MSVCBootstrapResult:
    success: bool
    vswhere_path: str | None
    vs_install_path: str | None
    vsdevcmd_path: str | None
    env: dict[str, str]
    error: str | None = None


@dataclass
class MSVCToolchainPaths:
    cl_path: str
    link_path: str
    lib_path: str
    rc_path: str
    source: str


def _strip_wrapping_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].strip()
    return text


def find_vswhere_path() -> Path | None:
    pf86 = os.environ.get("ProgramFiles(x86)")
    if not pf86:
        return None
    candidate = Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if candidate.exists():
        return candidate
    return None


def find_vs_installation(vswhere_path: Path) -> str | None:
    proc = subprocess.run(
        [
            str(vswhere_path),
            "-latest",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        capture_output=True,
        text=True,
        shell=False,
    )
    if proc.returncode != 0:
        return None
    value = _strip_wrapping_quotes(proc.stdout or "")
    return value or None


def _latest_msvc_tool_bin(vs_install_path: str) -> Path | None:
    base = Path(vs_install_path) / "VC" / "Tools" / "MSVC"
    if not base.exists():
        return None
    versions = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not versions:
        return None
    candidate = versions[-1] / "bin" / "Hostx64" / "x64"
    if candidate.exists():
        return candidate
    return None


def _which_in_env(tool: str, env: dict[str, str] | None = None) -> str:
    if env is None:
        found = shutil.which(tool)
    else:
        found = shutil.which(tool, path=_env_get(env, "PATH"))
    return str(Path(found).resolve()) if found else ""


def resolve_msvc_toolchain_paths(env: dict[str, str] | None = None) -> MSVCToolchainPaths:
    cl = _which_in_env("cl", env)
    link = _which_in_env("link", env)
    lib = _which_in_env("lib", env)
    rc = _which_in_env("rc", env)
    if cl and link and lib:
        return MSVCToolchainPaths(
            cl_path=cl,
            link_path=link,
            lib_path=lib,
            rc_path=rc,
            source="env",
        )

    vswhere = find_vswhere_path()
    vs_install = find_vs_installation(vswhere) if vswhere else None
    if not vs_install:
        return MSVCToolchainPaths(cl_path=cl, link_path=link, lib_path=lib, rc_path=rc, source="missing")

    bin_dir = _latest_msvc_tool_bin(vs_install)
    if not bin_dir:
        return MSVCToolchainPaths(cl_path=cl, link_path=link, lib_path=lib, rc_path=rc, source="missing")

    cl2 = str((bin_dir / "cl.exe").resolve()) if (bin_dir / "cl.exe").exists() else cl
    link2 = str((bin_dir / "link.exe").resolve()) if (bin_dir / "link.exe").exists() else link
    lib2 = str((bin_dir / "lib.exe").resolve()) if (bin_dir / "lib.exe").exists() else lib
    rc2 = str((bin_dir / "rc.exe").resolve()) if (bin_dir / "rc.exe").exists() else rc

    if not rc2:
        rc2 = _which_in_env("rc", env)

    source = "vswhere" if cl2 and link2 and lib2 else "partial"
    return MSVCToolchainPaths(
        cl_path=cl2,
        link_path=link2,
        lib_path=lib2,
        rc_path=rc2,
        source=source,
    )


def resolve_vsdevcmd_path(vs_install_path: str) -> Path:
    normalized_install = _strip_wrapping_quotes(vs_install_path)
    candidate = Path(normalized_install) / "Common7" / "Tools" / "VsDevCmd.bat"
    if candidate.exists():
        return candidate
    # Fallback for BuildTools which might be in Program Files (x86)
    alt_path = normalized_install.replace("Program Files", "Program Files (x86)")
    alt_candidate = Path(alt_path) / "Common7" / "Tools" / "VsDevCmd.bat"
    if alt_candidate.exists():
        return alt_candidate
    return candidate  # Return original even if not exists, for error reporting


def build_capture_env_command(vsdevcmd_path: str | Path, arch: str = "amd64") -> str:
    normalized_vsdevcmd = _strip_wrapping_quotes(str(vsdevcmd_path))
    return f'call "{normalized_vsdevcmd}" -arch={arch} >nul && set'


def build_capture_env_invocation(vsdevcmd_path: str | Path, arch: str = "amd64") -> str:
    inner = build_capture_env_command(vsdevcmd_path, arch=arch)
    return f'cmd.exe /d /s /c "{inner}"'


def parse_set_output(output: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or "=" not in line or line.startswith("="):
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        env[key] = value
    return env


def _env_get(env: dict[str, str], key: str) -> str | None:
    for existing_key, value in env.items():
        if existing_key.upper() == key.upper():
            return value
    return None


def capture_msvc_environment(vsdevcmd_path: str | Path, arch: str = "amd64") -> dict[str, str]:
    command = build_capture_env_command(vsdevcmd_path, arch=arch)
    script_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bat", delete=False, encoding="utf-8") as handle:
            handle.write("@echo off\n")
            handle.write(f"{command}\n")
            script_path = Path(handle.name)

        proc = subprocess.run(
            ["cmd.exe", "/d", "/c", str(script_path)],
            capture_output=True,
            text=True,
            shell=False,
        )
    finally:
        if script_path and script_path.exists():
            try:
                script_path.unlink()
            except OSError:
                pass

    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MSVC environment capture failed").strip())
    return parse_set_output(proc.stdout or "")


def _tool_on_path(tool_name: str, env: dict[str, str]) -> bool:
    return shutil.which(tool_name, path=_env_get(env, "PATH")) is not None


def has_cl_link(env: dict[str, str]) -> bool:
    return _tool_on_path("cl", env) and _tool_on_path("link", env)


def bootstrap_msvc(arch: str = "amd64") -> MSVCBootstrapResult:
    vswhere = find_vswhere_path()
    if not vswhere:
        return MSVCBootstrapResult(
            success=False,
            vswhere_path=None,
            vs_install_path=None,
            vsdevcmd_path=None,
            env={},
            error="vswhere.exe not found",
        )

    vs_install = find_vs_installation(vswhere)
    if not vs_install:
        return MSVCBootstrapResult(
            success=False,
            vswhere_path=str(vswhere),
            vs_install_path=None,
            vsdevcmd_path=None,
            env={},
            error="Visual Studio installation with VC tools not found",
        )

    vsdevcmd = resolve_vsdevcmd_path(vs_install)
    if not vsdevcmd.exists():
        return MSVCBootstrapResult(
            success=False,
            vswhere_path=str(vswhere),
            vs_install_path=vs_install,
            vsdevcmd_path=str(vsdevcmd),
            env={},
            error="VsDevCmd.bat not found",
        )

    try:
        env = capture_msvc_environment(vsdevcmd, arch=arch)
    except Exception as exc:
        return MSVCBootstrapResult(
            success=False,
            vswhere_path=str(vswhere),
            vs_install_path=vs_install,
            vsdevcmd_path=str(vsdevcmd),
            env={},
            error=f"bootstrap failed: {exc}",
        )

    ok = has_cl_link(env)
    return MSVCBootstrapResult(
        success=ok,
        vswhere_path=str(vswhere),
        vs_install_path=vs_install,
        vsdevcmd_path=str(vsdevcmd),
        env=env,
        error=None if ok else "MSVC tools not found in bootstrapped environment",
    )
