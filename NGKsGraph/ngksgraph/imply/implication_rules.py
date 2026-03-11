from __future__ import annotations

import json
from pathlib import Path


_FALLBACK_RULES = [
    {
        "id": "qt6_msvc_cpp17",
        "when": ["Qt6", "msvc"],
        "source_detector": "Qt6",
        "category": "compiler_standard",
        "description": "Qt6 on MSVC requires C++17 and __cplusplus reporting support",
        "required_tools": ["cl.exe", "link.exe", "lib.exe", "qt"],
        "required_minimums": {"cpp_standard": "c++17"},
        "required_flags": {"msvc": ["/std:c++17", "/Zc:__cplusplus"], "gcc": ["-std=c++17"], "clang": ["-std=c++17"]},
        "required_env": ["vcvars active", "Qt bin on PATH"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.95,
    },
    {
        "id": "juce_cpp17",
        "when": ["JUCE", "msvc"],
        "source_detector": "JUCE",
        "category": "compiler_standard",
        "description": "JUCE projects require a C++17-capable compiler",
        "required_tools": ["cl.exe", "link.exe", "lib.exe"],
        "required_minimums": {"cpp_standard": "c++17"},
        "required_flags": {"msvc": ["/std:c++17", "/Zc:__cplusplus"]},
        "required_env": ["vcvars active"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "python_pyproject_backend",
        "when": ["Python", "pyproject.toml"],
        "source_detector": "pyproject.toml",
        "category": "tool",
        "description": "Python project requires Python runtime and build backend",
        "required_tools": ["python"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": ["project venv present"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "node_typescript_toolchain",
        "when": ["TypeScript", "package.json"],
        "source_detector": "package.json",
        "category": "tool",
        "description": "TypeScript projects require node and package manager",
        "required_tools": ["node"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "cargo_rustc_required",
        "when": ["Cargo.toml"],
        "source_detector": "Cargo.toml",
        "category": "tool",
        "description": "Rust projects require cargo and rustc",
        "required_tools": ["cargo", "rustc"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.95,
    },
    {
        "id": "go_modules_required",
        "when": ["go.mod"],
        "source_detector": "go.mod",
        "category": "tool",
        "description": "Go module builds require go toolchain",
        "required_tools": ["go"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.95,
    },
    {
        "id": "dotnet_sdk_required",
        "when": [".csproj"],
        "source_detector": ".csproj",
        "category": "tool",
        "description": ".NET projects require dotnet SDK or MSBuild",
        "required_tools": ["dotnet"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "java_build_toolchain",
        "when": ["jvm_build_manifest"],
        "source_detector": "maven/gradle",
        "category": "tool",
        "description": "JVM builds require java runtime",
        "required_tools": ["java"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "flutter_dart_toolchain",
        "when": ["Flutter", "pubspec.yaml"],
        "source_detector": "Flutter",
        "category": "tool",
        "description": "Flutter projects require Dart SDK and Flutter toolchain",
        "required_tools": ["flutter", "dart"],
        "required_minimums": {},
        "required_flags": {},
        "required_env": ["flutter on PATH"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.95,
    },
    {
        "id": "pyside6_python_qt",
        "when": ["PySide6", "Python"],
        "source_detector": "PySide6",
        "category": "tool",
        "description": "PySide6 requires Python and Qt runtime",
        "required_tools": ["python", "qt"],
        "required_minimums": {"python_version": "3.8"},
        "required_flags": {},
        "required_env": ["project venv present", "Qt bin on PATH"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "electron_node_toolchain",
        "when": ["Electron", "package.json"],
        "source_detector": "package.json",
        "category": "tool",
        "description": "Electron apps require Node.js and native build tools",
        "required_tools": ["node", "npm"],
        "required_minimums": {"node_version": "14.0"},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "django_python_web",
        "when": ["Django", "Python"],
        "source_detector": "Django",
        "category": "tool",
        "description": "Django projects require Python runtime",
        "required_tools": ["python"],
        "required_minimums": {"python_version": "3.8"},
        "required_flags": {},
        "required_env": ["project venv present"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "react_typescript_toolchain",
        "when": ["React", "TypeScript"],
        "source_detector": "package.json",
        "category": "tool",
        "description": "React TypeScript projects require Node.js toolchain",
        "required_tools": ["node", "npm", "tsc"],
        "required_minimums": {"node_version": "16.0"},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "cpp20_coroutine_support",
        "when": ["C++", "coroutines"],
        "source_detector": "C++20",
        "category": "compiler_standard",
        "description": "C++20 coroutines require compiler support",
        "required_tools": ["cl.exe", "link.exe"],
        "required_minimums": {"cpp_standard": "c++20"},
        "required_flags": {
            "msvc": ["/std:c++20", "/await"],
            "gcc": ["-std=c++20", "-fcoroutines"],
            "clang": ["-std=c++20", "-fcoroutines-ts"]
        },
        "required_env": ["vcvars active"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.8,
    },
    {
        "id": "cpp_modules_support",
        "when": ["C++", "modules"],
        "source_detector": "C++20",
        "category": "compiler_standard",
        "description": "C++20 modules require compiler support",
        "required_tools": ["cl.exe", "link.exe"],
        "required_minimums": {"cpp_standard": "c++20"},
        "required_flags": {
            "msvc": ["/std:c++20", "/experimental:module"],
            "gcc": ["-std=c++20", "-fmodules-ts"],
            "clang": ["-std=c++20", "-fmodules"]
        },
        "required_env": ["vcvars active"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.8,
    },
    {
        "id": "cpp11_msvc_support",
        "when": ["C++", "msvc"],
        "source_detector": "C++11",
        "category": "compiler_standard",
        "description": "C++11 features require MSVC support",
        "required_tools": ["cl.exe", "link.exe"],
        "required_minimums": {"cpp_standard": "c++11"},
        "required_flags": {
            "msvc": ["/std:c++11"],
            "gcc": ["-std=c++11"],
            "clang": ["-std=c++11"]
        },
        "required_env": ["vcvars active"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "cpp14_msvc_support",
        "when": ["C++", "msvc"],
        "source_detector": "C++14",
        "category": "compiler_standard",
        "description": "C++14 features require MSVC support",
        "required_tools": ["cl.exe", "link.exe"],
        "required_minimums": {"cpp_standard": "c++14"},
        "required_flags": {
            "msvc": ["/std:c++14"],
            "gcc": ["-std=c++14"],
            "clang": ["-std=c++14"]
        },
        "required_env": ["vcvars active"],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "dotnet_core_sdk",
        "when": [".NET Core"],
        "source_detector": ".csproj",
        "category": "tool",
        "description": ".NET Core projects require dotnet SDK",
        "required_tools": ["dotnet"],
        "required_minimums": {"dotnet_version": "3.1"},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
    {
        "id": "java_8_minimum",
        "when": ["Java"],
        "source_detector": "maven/gradle",
        "category": "tool",
        "description": "Java projects typically require Java 8 or higher",
        "required_tools": ["java", "javac"],
        "required_minimums": {"java_version": "8"},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.8,
    },
    {
        "id": "node_lts_support",
        "when": ["Node.js"],
        "source_detector": "package.json",
        "category": "tool",
        "description": "Node.js projects require Node.js runtime",
        "required_tools": ["node", "npm"],
        "required_minimums": {"node_version": "16.0"},
        "required_flags": {},
        "required_env": [],
        "severity_if_missing": "build_blocker",
        "confidence": 0.9,
    },
]


def _rules_file() -> Path:
    return Path(__file__).resolve().parents[1] / "rules" / "implication_rules.json"


def _load_rules() -> list[dict[str, object]]:
    try:
        payload = json.loads(_rules_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(_FALLBACK_RULES)

    raw_rules = payload.get("rules", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rules, list):
        return list(_FALLBACK_RULES)

    rules: list[dict[str, object]] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("id")
        when = item.get("when", [])
        if not isinstance(rule_id, str) or not rule_id.strip() or not isinstance(when, list):
            continue
        rules.append(
            {
                "id": rule_id,
                "when": [str(token) for token in when],
                "source_detector": str(item.get("source_detector", rule_id)),
                "category": str(item.get("category", "tool")),
                "description": str(item.get("description", "derived toolchain requirement")),
                "required_tools": list(item.get("required_tools", [])),
                "required_minimums": dict(item.get("required_minimums", {})),
                "required_flags": dict(item.get("required_flags", {})),
                "required_env": list(item.get("required_env", [])),
                "severity_if_missing": str(item.get("severity_if_missing", "build_blocker")),
                "confidence": float(item.get("confidence", 0.9)),
            }
        )

    return rules or list(_FALLBACK_RULES)


def starter_rule_ids() -> list[str]:
    return [str(rule.get("id", "")) for rule in _load_rules() if str(rule.get("id", ""))]


def implication_rules() -> list[dict[str, object]]:
    return _load_rules()
