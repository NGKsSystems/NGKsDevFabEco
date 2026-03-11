from __future__ import annotations

from ngksgraph.core.enums import EvidenceType


MANIFEST_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
    "Package.swift",
    "pubspec.yaml",
    "mix.exs",
    "CMakeLists.txt",
    "Makefile",
    "makefile",
    "meson.build",
    "BUILD",
    "BUILD.bazel",
    "WORKSPACE",
    "SConstruct",
    "build.xml",
}

FOREIGN_AUTHORED_CONFIG_SUFFIXES = {
    ".sln",
    ".csproj",
    ".vcxproj",
    ".fsproj",
    ".vbproj",
    ".xcodeproj",
    ".xcworkspace",
    ".pro",
    ".pri",
}

FOREIGN_GENERATED_NAMES = {
    "compile_commands.json",
    "build.ninja",
    "cmake_install.cmake",
    "CMakeCache.txt",
}


def classify(rel_path: str, file_name: str, ext: str, is_source_ext: bool) -> tuple[EvidenceType, bool]:
    lower = rel_path.lower()
    if any(part in lower for part in ["/third_party/", "/vendor/", "/external/"]):
        return EvidenceType.VENDOR, False
    if file_name in FOREIGN_GENERATED_NAMES:
        return EvidenceType.FOREIGN_GENERATED, False
    if any(part in lower for part in ["/build/", "/out/", "/cmake-build"]):
        return EvidenceType.CACHE, False
    if file_name in MANIFEST_FILES:
        return EvidenceType.MANIFEST, True
    if is_source_ext:
        return EvidenceType.SOURCE, True
    if ext in FOREIGN_AUTHORED_CONFIG_SUFFIXES:
        return EvidenceType.FOREIGN_AUTHORED_CONFIG, True
    if any(part in lower for part in ["/docs/", "/doc/"]):
        return EvidenceType.DOCS, False
    if any(part in lower for part in ["/test/", "/tests/"]):
        return EvidenceType.TEST, True
    if any(part in lower for part in ["/sample/", "/samples/", "/examples/"]):
        return EvidenceType.SAMPLE, False
    return EvidenceType.RUNTIME_ARTIFACT, False
