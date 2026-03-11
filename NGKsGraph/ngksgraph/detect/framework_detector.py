from __future__ import annotations

from pathlib import Path


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def detect_frameworks(repo_root: Path, source_paths: set[str]) -> list[dict[str, object]]:
    frameworks: list[dict[str, object]] = []
    qt_evidence: list[str] = []
    juce_evidence: list[str] = []
    flutter_evidence: list[str] = []
    pyside_evidence: list[str] = []
    electron_evidence: list[str] = []
    django_evidence: list[str] = []
    react_evidence: list[str] = []

    cmake_path = repo_root / "CMakeLists.txt"
    cmake_text = load_text(cmake_path)
    if "find_package(Qt6" in cmake_text:
        qt_evidence.append("CMakeLists.txt:find_package(Qt6)")
    if "juce_add_" in cmake_text:
        juce_evidence.append("CMakeLists.txt:juce_add_*")

    # Check Python files for framework imports
    for rel in source_paths:
        if rel.endswith(".py"):
            text = load_text(repo_root / rel)
            if "from PySide6" in text or "import PySide6" in text:
                pyside_evidence.append(rel)
            if "from django" in text or "import django" in text or "DJANGO_SETTINGS_MODULE" in text:
                django_evidence.append(rel)

        elif rel.endswith(".cpp") or rel.endswith(".hpp") or rel.endswith(".h"):
            text = load_text(repo_root / rel)
            if "QApplication" in text or "Q_OBJECT" in text or "#include <Q" in text:
                qt_evidence.append(rel)
            if "JuceHeader.h" in text or "namespace juce" in text or "JUCEApplication" in text:
                juce_evidence.append(rel)

        elif rel.endswith(".js") or rel.endswith(".ts") or rel.endswith(".jsx") or rel.endswith(".tsx"):
            text = load_text(repo_root / rel)
            if "require('electron')" in text or "from 'electron'" in text or "import electron" in text:
                electron_evidence.append(rel)
            if ("React" in text and ("import React" in text or "from 'react'" in text)) or "jsx" in rel:
                react_evidence.append(rel)

    # Check package.json for Node.js frameworks
    package_json = load_text(repo_root / "package.json")
    if package_json:
        if '"electron"' in package_json or '"electron":' in package_json:
            electron_evidence.append("package.json:electron")
        if '"react"' in package_json or '"react":' in package_json:
            react_evidence.append("package.json:react")

    # Check pubspec.yaml for Flutter
    pubspec = load_text(repo_root / "pubspec.yaml")
    if "sdk: flutter" in pubspec or "flutter:" in pubspec:
        flutter_evidence.append("pubspec.yaml")
    if (repo_root / "lib" / "main.dart").exists():
        flutter_evidence.append("lib/main.dart")

    # Check requirements.txt or pyproject.toml for Python frameworks
    requirements_txt = load_text(repo_root / "requirements.txt")
    pyproject_toml = load_text(repo_root / "pyproject.toml")
    if "PySide6" in requirements_txt or "PySide6" in pyproject_toml:
        pyside_evidence.append("requirements.txt" if "PySide6" in requirements_txt else "pyproject.toml")
    if "Django" in requirements_txt or "Django" in pyproject_toml:
        django_evidence.append("requirements.txt" if "Django" in requirements_txt else "pyproject.toml")

    if qt_evidence:
        frameworks.append({"name": "Qt6", "confidence": 0.95, "evidence": sorted(set(qt_evidence))[:8]})
    if juce_evidence:
        frameworks.append({"name": "JUCE", "confidence": 0.9, "evidence": sorted(set(juce_evidence))[:8]})
    if flutter_evidence:
        frameworks.append({"name": "Flutter", "confidence": 0.9, "evidence": sorted(set(flutter_evidence))[:8]})
    if pyside_evidence:
        frameworks.append({"name": "PySide6", "confidence": 0.9, "evidence": sorted(set(pyside_evidence))[:8]})
    if electron_evidence:
        frameworks.append({"name": "Electron", "confidence": 0.9, "evidence": sorted(set(electron_evidence))[:8]})
    if django_evidence:
        frameworks.append({"name": "Django", "confidence": 0.9, "evidence": sorted(set(django_evidence))[:8]})
    if react_evidence:
        frameworks.append({"name": "React", "confidence": 0.85, "evidence": sorted(set(react_evidence))[:8]})

    return frameworks
