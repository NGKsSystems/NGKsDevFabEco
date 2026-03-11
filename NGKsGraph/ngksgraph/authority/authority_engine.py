from __future__ import annotations

from pathlib import Path

from ngksgraph.authority.authority_rules import default_authority_items


SOURCE_PRECEDENCE = [
    "native_ngks_contract",
    "first_party_authored_manifests",
    "first_party_source_reality",
    "foreign_authored_config",
    "foreign_generated_outputs",
    "runtime_leftovers_cache",
]


def _is_detected(repo_root: Path, tool_or_file: str) -> bool:
    if tool_or_file == "CMakeLists.txt":
        return (repo_root / "CMakeLists.txt").exists()
    if tool_or_file == "build.ninja":
        return any((repo_root / path).exists() for path in ["build.ninja", "build/build.ninja", "out/build.ninja"])
    if tool_or_file == "CMakeCache.txt":
        return any((repo_root / path).exists() for path in ["CMakeCache.txt", "build/CMakeCache.txt", "out/CMakeCache.txt"])
    if tool_or_file == "compile_commands.json":
        return any(
            (repo_root / path).exists()
            for path in ["compile_commands.json", "build/compile_commands.json", "out/compile_commands.json"]
        )
    return (repo_root / tool_or_file).exists()


def evaluate_authority(repo_root: Path, authority_mode: str) -> dict[str, object]:
    normalized_mode = authority_mode if authority_mode in {"native_ngks", "import_foreign", "compatibility_only", "foreign_authoritative"} else "native_ngks"
    items = []
    for rule in default_authority_items():
        item = dict(rule)
        name = str(item["tool_or_file"])
        detected = _is_detected(repo_root, name)
        item["detected"] = detected
        if normalized_mode == "foreign_authoritative":
            item["execution_allowed"] = name == "CMakeLists.txt"
            item["authoritative"] = bool(name == "CMakeLists.txt")
        elif normalized_mode == "compatibility_only":
            item["execution_allowed"] = False
            item["authoritative"] = False
        elif normalized_mode == "import_foreign":
            item["execution_allowed"] = False
            item["authoritative"] = False
            if name == "CMakeLists.txt":
                item["import_strategy"] = "importable"
        else:
            item["execution_allowed"] = False
            item["authoritative"] = False
        items.append(item)

    return {
        "repo_root": str(repo_root),
        "authority_mode": normalized_mode,
        "source_precedence": list(SOURCE_PRECEDENCE),
        "items": items,
    }
