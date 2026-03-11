from __future__ import annotations

from ngksgraph.imply.implication_rules import implication_rules


def derive_requirements(framework_names: set[str], language_names: set[str], manifest_names: set[str]) -> list[dict[str, object]]:
    requirements: list[dict[str, object]] = []
    token_space = set(framework_names) | set(language_names) | set(manifest_names)
    if any(name.endswith(".csproj") for name in manifest_names):
        token_space.add(".csproj")
    if {"pom.xml", "build.gradle", "build.gradle.kts"} & manifest_names:
        token_space.add("jvm_build_manifest")
    if "Qt6" in framework_names or "JUCE" in framework_names:
        token_space.add("msvc")

    for rule in implication_rules():
        required_tokens = set(str(token) for token in rule.get("when", []))
        if not required_tokens.issubset(token_space):
            continue
        requirements.append(
            {
                "subproject_id": "root",
                "requirement_id": str(rule.get("id", "")),
                "source_detector": str(rule.get("source_detector", "")),
                "category": str(rule.get("category", "tool")),
                "description": str(rule.get("description", "derived toolchain requirement")),
                "required_tools": list(rule.get("required_tools", [])),
                "required_minimums": dict(rule.get("required_minimums", {})),
                "required_flags": dict(rule.get("required_flags", {})),
                "required_env": list(rule.get("required_env", [])),
                "severity_if_missing": str(rule.get("severity_if_missing", "build_blocker")),
                "confidence": float(rule.get("confidence", 0.9)),
            }
        )

    return requirements
