from __future__ import annotations

from pathlib import Path

from ngksgraph.plan.capability_mapper import capability_map


def build_native_plan(repo_root: Path, source_paths: set[str], framework_names: set[str], required_flags: list[str]) -> dict[str, object]:
    default_target = repo_root.name.replace(" ", "_")

    def _infer_target_type(paths: list[str]) -> str:
        has_main = any(Path(path).name.lower() in {"main.cpp", "main.c", "main.cs", "main.rs", "main.go", "main.py"} for path in paths)
        if has_main:
            return "executable"
        if framework_names & {"Qt6", "JUCE"}:
            return "shared"
        return "staticlib"

    def _source_groups(paths: list[str]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "cpp": [],
            "c": [],
            "headers": [],
            "dotnet": [],
            "python": [],
            "typescript": [],
            "rust": [],
            "go": [],
        }
        for path in paths:
            suffix = Path(path).suffix.lower()
            if suffix in {".cpp", ".cc", ".cxx"}:
                groups["cpp"].append(path)
            elif suffix == ".c":
                groups["c"].append(path)
            elif suffix in {".h", ".hpp", ".hh", ".hxx"}:
                groups["headers"].append(path)
            elif suffix == ".cs":
                groups["dotnet"].append(path)
            elif suffix in {".py", ".pyw"}:
                groups["python"].append(path)
            elif suffix in {".ts", ".tsx"}:
                groups["typescript"].append(path)
            elif suffix == ".rs":
                groups["rust"].append(path)
            elif suffix == ".go":
                groups["go"].append(path)
        return {name: values for name, values in groups.items() if values}

    def _include_dirs(paths: list[str]) -> list[str]:
        roots = {"include", "src"}
        for path in paths:
            p = Path(path)
            parts = p.parts
            if not parts:
                continue
            if "include" in parts:
                idx = parts.index("include")
                roots.add("/".join(parts[: idx + 1]))
            elif len(parts) >= 2 and parts[0] in {"src", "source", "app", "lib"}:
                roots.add(parts[0])
        return sorted(roots)

    sources = sorted(
        path
        for path in source_paths
        if path.endswith((".cpp", ".c", ".cc", ".cxx", ".h", ".hpp", ".cs", ".py", ".pyw", ".ts", ".tsx", ".rs", ".go"))
    )
    if len(sources) > 400:
        sources = sources[:400]

    target_type = _infer_target_type(sources)
    source_groups = _source_groups(sources)
    inferred_include_dirs = _include_dirs(sources)
    link_libraries = ["Qt6Core", "Qt6Widgets"] if "Qt6" in framework_names else []
    if "JUCE" in framework_names:
        link_libraries.extend(["juce_core", "juce_gui_basics"])
    link_libraries = sorted(set(link_libraries))

    execution_steps = [
        {
            "step": "compile",
            "tool": "cl.exe",
            "flags": list(required_flags),
            "input_groups": sorted(source_groups.keys()),
        },
        {
            "step": "link",
            "tool": "link.exe",
            "libraries": link_libraries,
        },
    ]

    return {
        "repo_root": str(repo_root),
        "subprojects": [
            {
                "subproject_id": "root",
                "target_name": default_target,
                "target_type": target_type,
                "sources": sources,
                "source_groups": source_groups,
                "include_dirs": inferred_include_dirs,
                "defines": ["UNICODE", "_UNICODE"],
                "compile_options": {"msvc": list(required_flags)},
                "link_libraries": link_libraries,
                "execution_steps": execution_steps,
                "execution_support": capability_map(framework_names),
            }
        ],
    }
