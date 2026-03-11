from __future__ import annotations

from pathlib import Path

from ngksgraph.planner.capability_mapper import capability_map


def build_native_plan(repo_root: Path, source_paths: set[str], framework_names: set[str], required_flags: list[str]) -> dict[str, object]:
    default_target = repo_root.name.replace(" ", "_")
    sources = sorted(
        path
        for path in source_paths
        if path.endswith((".cpp", ".c", ".cc", ".cxx", ".h", ".hpp", ".cs", ".py", ".ts", ".rs", ".go"))
    )
    if len(sources) > 400:
        sources = sources[:400]

    return {
        "repo_root": str(repo_root),
        "subprojects": [
            {
                "subproject_id": "root",
                "target_name": default_target,
                "target_type": "executable",
                "sources": sources,
                "include_dirs": ["include", "src"],
                "defines": ["UNICODE", "_UNICODE"],
                "compile_options": {"msvc": list(required_flags)},
                "link_libraries": ["Qt6Core", "Qt6Widgets"] if "Qt6" in framework_names else [],
                "execution_support": capability_map(framework_names),
            }
        ],
    }
