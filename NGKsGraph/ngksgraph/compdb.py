from __future__ import annotations

from pathlib import Path
from typing import Any

from ngksgraph.config import Config
from ngksgraph.graph import BuildGraph, Target
from ngksgraph.util import normalize_path


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def _obj_rel_path(target: Target, src: str) -> str:
    src_path = Path(src)
    no_suffix = src_path.with_suffix("")
    return normalize_path(Path(target.obj_dir) / f"{no_suffix}.obj")


def build_compile_command(target: Target, src: str) -> str:
    obj_rel = _obj_rel_path(target, src)
    include_flags = " ".join(f"/I{_quote(normalize_path(path))}" for path in target.include_dirs)
    define_flags = " ".join(f"/D{define}" for define in target.defines)
    cflags = " ".join(target.cflags)
    parts = [
        "cl",
        "/nologo",
        "/EHsc",
        f"/std:c++{target.cxx_std}",
        "/MD",
        "/FS",
        "/showIncludes",
        "/c",
        _quote(normalize_path(src)),
        f"/Fo{_quote(obj_rel)}",
    ]
    if include_flags:
        parts.append(include_flags)
    if define_flags:
        parts.append(define_flags)
    if cflags:
        parts.append(cflags)
    return " ".join(parts)


def build_link_command(target: Target) -> str:
    obj_inputs = " ".join(_quote(_obj_rel_path(target, src)) for src in target.sources)
    out_exe = normalize_path(Path(target.bin_dir) / f"{target.name}.exe")
    lib_dirs = " ".join(f"/LIBPATH:{_quote(normalize_path(path))}" for path in target.lib_dirs)
    libs = " ".join(f"{lib}.lib" for lib in target.libs)
    ldflags = " ".join(target.ldflags)

    parts = ["link", "/nologo", obj_inputs, f"/OUT:{out_exe}"]
    if ldflags:
        parts.append(ldflags)
    if lib_dirs:
        parts.append(lib_dirs)
    if libs:
        parts.append(libs)
    return " ".join(parts)


def build_link_command_for_graph(graph: BuildGraph, target_name: str) -> str:
    target = graph.targets[target_name]
    obj_inputs = " ".join(_quote(_obj_rel_path(target, src)) for src in target.sources)
    dep_libs = []
    for dep_name in graph.link_closure(target_name):
        dep = graph.targets[dep_name]
        if dep.kind == "staticlib":
            dep_libs.append(_quote(normalize_path(Path(dep.lib_dir) / f"{dep.name}.lib")))

    out_exe = normalize_path(Path(target.bin_dir) / f"{target.name}.exe")
    lib_dirs = " ".join(f"/LIBPATH:{_quote(normalize_path(path))}" for path in target.lib_dirs)
    libs = " ".join(f"{lib}.lib" for lib in target.libs)
    ldflags = " ".join(target.ldflags)

    inputs = " ".join([obj_inputs] + dep_libs)
    parts = ["link", "/nologo", inputs, f"/OUT:{out_exe}"]
    if ldflags:
        parts.append(ldflags)
    if lib_dirs:
        parts.append(lib_dirs)
    if libs:
        parts.append(libs)
    return " ".join(parts)


def generate_compile_commands(graph: BuildGraph, config: Config, repo_root: str) -> list[dict[str, Any]]:
    repo = Path(repo_root).resolve()
    entries: list[dict[str, Any]] = []

    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        for src in sorted(target.sources):
            src_abs = (repo / src).resolve()
            entries.append(
                {
                    "directory": str(repo),
                    "file": str(src_abs),
                    "command": build_compile_command(target, src),
                }
            )

    entries.sort(key=lambda item: normalize_path(item["file"]))
    return entries
