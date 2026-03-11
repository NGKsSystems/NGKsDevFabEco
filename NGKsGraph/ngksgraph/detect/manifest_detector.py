from __future__ import annotations


MANIFEST_LANGUAGE_HINTS = {
    "pyproject.toml": {"Python": 50},
    "requirements.txt": {"Python": 30},
    "Pipfile": {"Python": 30},
    "poetry.lock": {"Python": 30},
    "package.json": {"JavaScript": 30, "TypeScript": 30},
    "package-lock.json": {"JavaScript": 20, "TypeScript": 20},
    "yarn.lock": {"JavaScript": 20, "TypeScript": 20},
    "pnpm-lock.yaml": {"JavaScript": 20, "TypeScript": 20},
    "Cargo.toml": {"Rust": 60},
    "Cargo.lock": {"Rust": 20},
    "go.mod": {"Go": 60},
    "go.sum": {"Go": 20},
    "pom.xml": {"Java": 50},
    "build.gradle": {"Java": 35, "Kotlin": 20, "Groovy": 20},
    "build.gradle.kts": {"Kotlin": 60},
    "settings.gradle": {"Java": 20, "Kotlin": 20, "Groovy": 20},
    "settings.gradle.kts": {"Kotlin": 25},
    "composer.json": {"PHP": 50},
    "Gemfile": {"Ruby": 50},
    "Package.swift": {"Swift": 60},
    "pubspec.yaml": {"Dart": 60},
    "mix.exs": {"Elixir": 60},
    "CMakeLists.txt": {"C": 20, "C++": 30},
    "Makefile": {"C": 10, "C++": 10},
    "makefile": {"C": 10, "C++": 10},
    "*.csproj": {"C#": 60},
    "*.sln": {"C#": 40, "C++": 20},
    "*.nuspec": {"C#": 25},
    "packages.config": {"C#": 25},
    "Directory.Packages.props": {"C#": 25},
    "*.vcxproj": {"C++": 60},
    "*.fsproj": {"F#": 60},
    "*.vbproj": {"VB.NET": 60},
}

BUILD_SYSTEM_FILES = {
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
    "build.ninja": "Ninja",
    "Cargo.toml": "Cargo",
    "go.mod": "Go Modules",
    "package.json": "Node Package Runtime",
    "Package.swift": "SwiftPM",
    "pubspec.yaml": "Pub",
    "Jenkinsfile": "Jenkins",
    "Taskfile.yml": "Task",
    "Taskfile.yaml": "Task",
    "azure-pipelines.yml": "Azure Pipelines",
    "azure-pipelines.yaml": "Azure Pipelines",
    ".gitlab-ci.yml": "GitLab CI",
    "Tiltfile": "Tilt",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "Dockerfile": "Docker",
}

PACKAGE_ECOSYSTEM_MANIFESTS = {
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
    "packages.config": "nuget",
    "Directory.Packages.props": "nuget",
    "packages.lock.json": "nuget",
    "*.nuspec": "nuget",
}


def detect_manifest_hints(file_name: str) -> dict[str, int]:
    hints: dict[str, int] = {}
    for pattern, mapping in MANIFEST_LANGUAGE_HINTS.items():
        if "*" in pattern:
            suffix = pattern.replace("*", "")
            if not file_name.endswith(suffix):
                continue
        elif file_name != pattern:
            continue
        for language, weight in mapping.items():
            hints[language] = hints.get(language, 0) + weight
    return hints


def detect_package_ecosystem(file_name: str) -> str | None:
    for pattern, ecosystem in PACKAGE_ECOSYSTEM_MANIFESTS.items():
        if "*" in pattern:
            suffix = pattern.replace("*", "")
            if file_name.endswith(suffix):
                return ecosystem
        elif file_name == pattern:
            return ecosystem
    return None


def detect_build_system(file_name: str, rel_path: str | None = None) -> str | None:
    build = BUILD_SYSTEM_FILES.get(file_name)
    if build:
        return build
    if file_name.endswith(".sln"):
        return "MSBuild"

    normalized = str(rel_path or "").replace("\\", "/")
    if normalized.startswith(".github/workflows/") and (normalized.endswith(".yml") or normalized.endswith(".yaml")):
        return "GitHub Actions"
    return None
