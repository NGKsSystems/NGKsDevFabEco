from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ------------------------------------------------------------
# NGKsGraph repo detector baseline
# ------------------------------------------------------------

EXTENSION_MAP: Dict[str, str] = {
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".ixx": "C++",
    ".cppm": "C++",
    ".cs": "C#",
    ".fs": "F#",
    ".vb": "VB.NET",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".groovy": "Groovy",
    ".scala": "Scala",
    ".py": "Python",
    ".pyw": "Python",
    ".rs": "Rust",
    ".go": "Go",
    ".zig": "Zig",
    ".d": "D",
    ".nim": "Nim",
    ".f": "Fortran",
    ".f90": "Fortran",
    ".f95": "Fortran",
    ".m": "Objective-C/MATLAB/Octave",
    ".mm": "Objective-C++",
    ".swift": "Swift",
    ".dart": "Dart",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".php": "PHP",
    ".rb": "Ruby",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".tcl": "Tcl",
    ".r": "R",
    ".jl": "Julia",
    ".sql": "SQL",
    ".sol": "Solidity",
    ".gd": "GDScript",
    ".pas": "Pascal",
    ".pp": "Pascal",
    ".asm": "Assembly",
    ".s": "Assembly",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
}

MANIFEST_HINTS: Dict[str, Tuple[str, int]] = {
    "pyproject.toml": ("Python", 50),
    "requirements.txt": ("Python", 30),
    "Pipfile": ("Python", 30),
    "poetry.lock": ("Python", 30),

    "package.json": ("JavaScript/TypeScript", 50),
    "package-lock.json": ("JavaScript/TypeScript", 20),
    "yarn.lock": ("JavaScript/TypeScript", 20),
    "pnpm-lock.yaml": ("JavaScript/TypeScript", 20),

    "Cargo.toml": ("Rust", 60),
    "Cargo.lock": ("Rust", 20),

    "go.mod": ("Go", 60),
    "go.sum": ("Go", 20),

    "pom.xml": ("Java", 50),
    "build.gradle": ("Java/Kotlin/Groovy", 50),
    "build.gradle.kts": ("Kotlin", 60),
    "settings.gradle": ("Java/Kotlin/Groovy", 20),
    "settings.gradle.kts": ("Kotlin", 25),

    "composer.json": ("PHP", 50),
    "Gemfile": ("Ruby", 50),
    "Package.swift": ("Swift", 60),
    "pubspec.yaml": ("Dart", 60),
    "mix.exs": ("Elixir", 60),

    "CMakeLists.txt": ("C/C++", 50),
    "Makefile": ("Make", 40),
    "makefile": ("Make", 40),
    "meson.build": ("Meson", 50),
    "BUILD": ("Bazel", 25),
    "BUILD.bazel": ("Bazel", 50),
    "WORKSPACE": ("Bazel", 50),
    "SConstruct": ("SCons", 50),
    "*.sln": ("MSBuild", 50),
    "*.csproj": ("C#", 60),
    "*.vcxproj": ("C++", 60),
    "*.fsproj": ("F#", 60),
    "*.vbproj": ("VB.NET", 60),
    "*.xcodeproj": ("Xcode", 50),
    "*.xcworkspace": ("Xcode", 50),
    "*.pro": ("QMake", 50),
}

BUILD_SYSTEM_FILES: Dict[str, str] = {
    "CMakeLists.txt": "CMake",
    "Makefile": "Make",
    "makefile": "Make",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "pom.xml": "Maven",
    "build.xml": "Ant",
    "meson.build": "Meson",
    "BUILD": "Bazel",
    "BUILD.bazel": "Bazel",
    "WORKSPACE": "Bazel",
    "SConstruct": "SCons",
    "Cargo.toml": "Cargo",
    "go.mod": "Go Modules",
    "package.json": "Node Package Runtime",
    "Package.swift": "SwiftPM",
    "pubspec.yaml": "Pub",
}

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vs", ".vscode",
    "node_modules", "dist", "build", "out", "target",
    ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".next", ".nuxt", ".turbo",
    "coverage", "bin", "obj"
}

TEXT_PROBE_LIMIT = 4096


@dataclass
class RepoDetectionResult:
    root: str
    language_scores: Dict[str, int] = field(default_factory=dict)
    extension_hits: Dict[str, int] = field(default_factory=dict)
    manifests_found: List[str] = field(default_factory=list)
    build_systems: List[str] = field(default_factory=list)
    package_ecosystems: List[str] = field(default_factory=list)
    primary_language: str = "Unknown"
    secondary_languages: List[str] = field(default_factory=list)
    mixed_repo: bool = False
    total_source_files: int = 0


def should_skip_dir(path: Path) -> bool:
    return path.name in IGNORE_DIRS


def bump(scores: Dict[str, int], key: str, amount: int) -> None:
    scores[key] = scores.get(key, 0) + amount


def classify_ambiguous_m_file(path: Path) -> str:
    """
    .m can be Objective-C, MATLAB, or Octave.
    Very cheap content sniff.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:TEXT_PROBE_LIMIT]
    except Exception:
        return "Objective-C/MATLAB/Octave"

    lowered = text.lower()

    if "@interface" in text or "@implementation" in text or "#import" in text:
        return "Objective-C"
    if "function " in lowered or "end" in lowered:
        return "MATLAB/Octave"
    return "Objective-C/MATLAB/Octave"


def detect_manifest(path: Path) -> List[Tuple[str, int]]:
    hits: List[Tuple[str, int]] = []
    name = path.name

    for pattern, (label, weight) in MANIFEST_HINTS.items():
        if "*" in pattern:
            suffix = pattern.replace("*", "")
            if name.endswith(suffix):
                hits.append((label, weight))
        elif name == pattern:
            hits.append((label, weight))

    return hits


def detect_build_system(path: Path) -> str | None:
    name = path.name
    if name in BUILD_SYSTEM_FILES:
        return BUILD_SYSTEM_FILES[name]
    if name.endswith(".sln") or name.endswith("proj"):
        return "MSBuild"
    if name.endswith(".xcodeproj") or name.endswith(".xcworkspace"):
        return "Xcode"
    return None


def language_from_extension(path: Path) -> str | None:
    ext = path.suffix.lower()
    lang = EXTENSION_MAP.get(ext)
    if ext == ".m":
        return classify_ambiguous_m_file(path)
    return lang


def normalize_language(label: str) -> List[str]:
    """
    Split composite hints into multiple weighted buckets.
    """
    if label == "JavaScript/TypeScript":
        return ["JavaScript", "TypeScript"]
    if label == "Java/Kotlin/Groovy":
        return ["Java", "Kotlin", "Groovy"]
    if label == "C/C++":
        return ["C", "C++"]
    if label == "Objective-C/MATLAB/Octave":
        return ["Objective-C", "MATLAB", "Octave"]
    if label == "MATLAB/Octave":
        return ["MATLAB", "Octave"]
    return [label]


def package_ecosystem_from_manifest(name: str) -> str | None:
    mapping = {
        "pyproject.toml": "pip/poetry",
        "requirements.txt": "pip",
        "Pipfile": "pipenv",
        "poetry.lock": "poetry",
        "package.json": "npm/yarn/pnpm",
        "package-lock.json": "npm",
        "yarn.lock": "yarn",
        "pnpm-lock.yaml": "pnpm",
        "Cargo.toml": "cargo",
        "go.mod": "go mod",
        "pom.xml": "maven",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "composer.json": "composer",
        "Gemfile": "bundler",
        "Package.swift": "SwiftPM",
        "pubspec.yaml": "pub",
        "mix.exs": "mix",
    }
    return mapping.get(name)


def walk_repo(root: Path) -> RepoDetectionResult:
    result = RepoDetectionResult(root=str(root.resolve()))
    scores: Dict[str, int] = {}
    extension_hits: Dict[str, int] = {}
    build_systems: Set[str] = set()
    package_ecosystems: Set[str] = set()
    manifests_found: Set[str] = set()

    for path in root.rglob("*"):
        if path.is_dir():
            continue

        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        # Manifest / build-file detection
        manifest_hits = detect_manifest(path)
        for label, weight in manifest_hits:
            manifests_found.add(str(path.relative_to(root)))
            for lang in normalize_language(label):
                bump(scores, lang, weight)

            eco = package_ecosystem_from_manifest(path.name)
            if eco:
                package_ecosystems.add(eco)

        build = detect_build_system(path)
        if build:
            build_systems.add(build)

        # Extension detection
        lang = language_from_extension(path)
        if lang:
            result.total_source_files += 1
            bump(extension_hits, lang, 1)

            # Base source-file weight
            for normalized in normalize_language(lang):
                bump(scores, normalized, 3)

            # Heavier weight for common "main" entry files
            lowered = path.name.lower()
            if lowered in {
                "main.py", "main.rs", "main.go", "main.c", "main.cpp",
                "app.py", "program.cs", "main.java", "main.kt",
                "index.ts", "index.js"
            }:
                for normalized in normalize_language(lang):
                    bump(scores, normalized, 5)

    result.language_scores = dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))
    result.extension_hits = dict(sorted(extension_hits.items(), key=lambda kv: kv[1], reverse=True))
    result.manifests_found = sorted(manifests_found)
    result.build_systems = sorted(build_systems)
    result.package_ecosystems = sorted(package_ecosystems)

    ranked = list(result.language_scores.keys())
    if ranked:
        result.primary_language = ranked[0]
        result.secondary_languages = ranked[1:5]

        if len(ranked) > 1:
            top_score = result.language_scores[ranked[0]]
            second_score = result.language_scores[ranked[1]]
            result.mixed_repo = second_score >= max(10, int(top_score * 0.40))

    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Detect repo languages/build systems for NGKsGraph")
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = walk_repo(root)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
        return

    print(f"root: {result.root}")
    print(f"primary_language: {result.primary_language}")
    print(f"mixed_repo: {result.mixed_repo}")
    print(f"total_source_files: {result.total_source_files}")

    print("\nlanguage_scores:")
    for lang, score in result.language_scores.items():
        print(f"  - {lang}: {score}")

    print("\nbuild_systems:")
    for item in result.build_systems:
        print(f"  - {item}")

    print("\npackage_ecosystems:")
    for item in result.package_ecosystems:
        print(f"  - {item}")

    print("\nmanifests_found:")
    for item in result.manifests_found[:50]:
        print(f"  - {item}")


if __name__ == "__main__":
    main()