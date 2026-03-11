from __future__ import annotations

import shutil

from ngksgraph.msvc import bootstrap_msvc, resolve_msvc_toolchain_paths


TOOL_CANDIDATES = {
    "cl.exe": ["cl.exe", "cl"],
    "link.exe": ["link.exe", "link"],
    "lib.exe": ["lib.exe", "lib"],
    "cmake": ["cmake"],
    "ninja": ["ninja"],
    "dotnet": ["dotnet"],
    "python": ["python", "python3"],
    "node": ["node"],
    "cargo": ["cargo"],
    "rustc": ["rustc"],
    "go": ["go"],
    "java": ["java"],
    "clang++": ["clang++"],
    "g++": ["g++"],
    "clang-cl": ["clang-cl"],
}


def probe_tools() -> dict[str, str | None]:
    tools = {
        key: next((shutil.which(candidate) for candidate in candidates if shutil.which(candidate)), None)
        for key, candidates in TOOL_CANDIDATES.items()
    }

    msvc_paths = resolve_msvc_toolchain_paths()
    if msvc_paths.cl_path:
        tools["cl.exe"] = tools.get("cl.exe") or msvc_paths.cl_path
    if msvc_paths.link_path:
        tools["link.exe"] = tools.get("link.exe") or msvc_paths.link_path
    if msvc_paths.lib_path:
        tools["lib.exe"] = tools.get("lib.exe") or msvc_paths.lib_path

    if not (tools.get("cl.exe") and tools.get("link.exe") and tools.get("lib.exe")):
        boot = bootstrap_msvc()
        if boot.success and boot.env:
            boot_paths = resolve_msvc_toolchain_paths(boot.env)
            if boot_paths.cl_path:
                tools["cl.exe"] = tools.get("cl.exe") or boot_paths.cl_path
            if boot_paths.link_path:
                tools["link.exe"] = tools.get("link.exe") or boot_paths.link_path
            if boot_paths.lib_path:
                tools["lib.exe"] = tools.get("lib.exe") or boot_paths.lib_path

    tools["cxx"] = (
        tools.get("cl.exe")
        or tools.get("clang++")
        or tools.get("g++")
        or tools.get("clang-cl")
    )
    return tools
