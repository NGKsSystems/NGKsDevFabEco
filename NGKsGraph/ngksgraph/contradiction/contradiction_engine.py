from __future__ import annotations

from pathlib import Path
import re

from ngksgraph.contradiction.contradiction_rules import contradiction_policy


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def detect_contradictions(repo_root: Path, manifests_found: set[str], source_paths: set[str]) -> dict[str, object]:
    contradictions: list[dict[str, object]] = []
    manifest_names = {Path(item).name for item in manifests_found}

    def _policy(rule_id: str) -> tuple[str, str]:
        policy = contradiction_policy(rule_id)
        return str(policy.get("severity", "medium")), str(policy.get("decision_impact", "warn"))

    csproj_exists = any(name.endswith(".csproj") for name in manifest_names)
    cs_sources = [path for path in source_paths if path.endswith(".cs")]
    if csproj_exists and not cs_sources:
        severity, decision = _policy("dotnet_manifest_without_sources")
        contradictions.append(
            {
                "contradiction_id": "dotnet_manifest_without_sources",
                "subproject_id": "root",
                "severity": severity,
                "left": {"source": ".csproj", "value": "declared"},
                "right": {"source": "source_tree", "value": "no .cs files"},
                "decision": decision,
                "reason": "manifest/source mismatch",
            }
        )

    vcxproj_exists = any(name.endswith(".vcxproj") for name in manifest_names)
    cpp_sources = [path for path in source_paths if path.endswith((".cpp", ".cc", ".cxx", ".c", ".hpp", ".h"))]
    if vcxproj_exists and not cpp_sources:
        severity, decision = _policy("project_type_mismatch_001")
        contradictions.append(
            {
                "contradiction_id": "project_type_mismatch_001",
                "subproject_id": "root",
                "severity": severity,
                "left": {"source": ".vcxproj", "value": "declared"},
                "right": {"source": "source_tree", "value": "no C/C++ sources"},
                "decision": decision,
                "reason": "project type mismatch",
            }
        )

    package_locks = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
    if (manifest_names & package_locks) and "package.json" not in manifest_names:
        severity, decision = _policy("package_manager_mismatch_001")
        contradictions.append(
            {
                "contradiction_id": "package_manager_mismatch_001",
                "subproject_id": "root",
                "severity": severity,
                "left": {"source": "lockfile", "value": sorted(manifest_names & package_locks)},
                "right": {"source": "manifest", "value": "package.json missing"},
                "decision": decision,
                "reason": "package manager mismatch",
            }
        )

    cmake_text = _load_text(repo_root / "CMakeLists.txt")
    native_config = _load_text(repo_root / "ngksgraph.toml")
    cmake_cpp17 = bool(re.search(r"CMAKE_CXX_STANDARD\s+17|cxx_std\s+17", cmake_text, flags=re.IGNORECASE))
    native_cpp20 = bool(re.search(r"cxx_std\s*=\s*20|/std:c\+\+20|-std=c\+\+20", native_config, flags=re.IGNORECASE))
    if cmake_cpp17 and native_cpp20:
        severity, decision = _policy("cpp_standard_conflict_001")
        contradictions.append(
            {
                "contradiction_id": "cpp_standard_conflict_001",
                "subproject_id": "root",
                "severity": severity,
                "left": {"source": "ngksgraph.toml", "value": "c++20"},
                "right": {"source": "CMakeLists.txt", "value": "c++17"},
                "decision": decision,
                "reason": "conflicting language standard requirements",
            }
        )

    qt_declared = "find_package(Qt6" in cmake_text
    qt_source_present = False
    if qt_declared:
        for rel in source_paths:
            if not rel.endswith((".cpp", ".hpp", ".h", ".cc", ".cxx")):
                continue
            text = _load_text(repo_root / rel)
            if "QApplication" in text or "Q_OBJECT" in text or "#include <Q" in text:
                qt_source_present = True
                break
        if not qt_source_present:
            severity, decision = _policy("framework_declared_without_source_001")
            contradictions.append(
                {
                    "contradiction_id": "framework_declared_without_source_001",
                    "subproject_id": "root",
                    "severity": severity,
                    "left": {"source": "CMakeLists.txt", "value": "Qt6 declared"},
                    "right": {"source": "source_tree", "value": "no Qt source evidence"},
                    "decision": decision,
                    "reason": "framework declared but no source evidence",
                }
            )

    if (repo_root / "CMakeLists.txt").exists() and (repo_root / "native_contract.json").exists():
        native_contract_text = _load_text(repo_root / "native_contract.json")
        cmake_mentions_qt = "find_package(Qt6" in cmake_text
        native_mentions_qt = "Qt6" in native_contract_text
        if cmake_mentions_qt != native_mentions_qt:
            severity, decision = _policy("native_foreign_disagree_001")
            contradictions.append(
                {
                    "contradiction_id": "native_foreign_disagree_001",
                    "subproject_id": "root",
                    "severity": severity,
                    "left": {"source": "CMakeLists.txt", "value": "Qt6" if cmake_mentions_qt else "Qt6 absent"},
                    "right": {"source": "native_contract.json", "value": "Qt6" if native_mentions_qt else "Qt6 absent"},
                    "decision": decision,
                    "reason": "native contract disagrees with foreign hint",
                }
            )

    return {"repo_root": str(repo_root), "contradictions": contradictions}
