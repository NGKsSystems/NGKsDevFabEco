from __future__ import annotations

from pathlib import Path

from ngksgraph.authority.authority_engine import evaluate_authority
from ngksgraph.contradiction.contradiction_engine import detect_contradictions
from ngksgraph.env.env_contract import build_env_contract
from ngksgraph.stale.stale_guard import evaluate_stale_risk


def test_authority_exposes_precedence_and_import_mode(tmp_path: Path) -> None:
    (tmp_path / "CMakeLists.txt").write_text("project(Demo)\n", encoding="utf-8")

    result = evaluate_authority(tmp_path, "import_foreign")

    assert result["authority_mode"] == "import_foreign"
    assert result["source_precedence"][0] == "native_ngks_contract"
    cmake_item = next(item for item in result["items"] if item["tool_or_file"] == "CMakeLists.txt")
    assert cmake_item["import_strategy"] == "importable"
    assert cmake_item["execution_allowed"] is False


def test_stale_guard_detects_dead_path_in_cmake_cache(tmp_path: Path) -> None:
    (tmp_path / "build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "build" / "CMakeCache.txt").write_text("CMAKE_CXX_COMPILER:PATH=C:/definitely/missing/compiler.exe\n", encoding="utf-8")

    result = evaluate_stale_risk(tmp_path)

    reasons = [str(item["reason"]) for item in result["stale_items"]]
    assert any("dead absolute path" in reason for reason in reasons)
    assert result["summary"]["medium"] >= 1


def test_contradictions_include_package_manager_mismatch(tmp_path: Path) -> None:
    manifests = {"yarn.lock"}
    source_paths: set[str] = set()

    result = detect_contradictions(tmp_path, manifests, source_paths)

    ids = {item["contradiction_id"] for item in result["contradictions"]}
    assert "package_manager_mismatch_001" in ids


def test_env_contract_reports_missing_vcvars(monkeypatch) -> None:
    monkeypatch.delenv("VCINSTALLDIR", raising=False)
    monkeypatch.delenv("VSCMD_ARG_TGT_ARCH", raising=False)
    monkeypatch.delenv("VSINSTALLDIR", raising=False)
    monkeypatch.setenv("QTDIR", "C:/Qt/6.8.0/msvc2022_64")

    requirements = [
        {
            "requirement_id": "qt6_msvc_cpp17",
            "required_tools": ["cl.exe", "link.exe", "lib.exe", "qt"],
            "required_flags": {"msvc": ["/std:c++17", "/Zc:__cplusplus", "/permissive-"]},
            "required_env": ["vcvars active", "Qt bin on PATH"],
        }
    ]
    tool_lookup = {
        "cxx": "C:/VS/cl.exe",
        "cl.exe": "C:/VS/cl.exe",
        "link.exe": "C:/VS/link.exe",
        "lib.exe": "C:/VS/lib.exe",
    }

    result = build_env_contract(Path("."), requirements, tool_lookup)
    root = result["subprojects"][0]

    assert root["missing"] == []
    assert "vcvars active" in root["missing_env"]
    assert root["status"] == "warn"


def test_env_contract_accepts_msvc_override(monkeypatch) -> None:
    monkeypatch.delenv("VCINSTALLDIR", raising=False)
    monkeypatch.delenv("VSCMD_ARG_TGT_ARCH", raising=False)
    monkeypatch.delenv("VSINSTALLDIR", raising=False)

    requirements = [
        {
            "requirement_id": "qt6_msvc_cpp17",
            "required_tools": ["cl.exe", "link.exe", "lib.exe"],
            "required_flags": {"msvc": ["/std:c++17"]},
            "required_env": ["vcvars active"],
        }
    ]
    tool_lookup = {
        "cxx": "C:/VS/cl.exe",
        "cl.exe": "C:/VS/cl.exe",
        "link.exe": "C:/VS/link.exe",
        "lib.exe": "C:/VS/lib.exe",
    }

    result = build_env_contract(Path("."), requirements, tool_lookup, msvc_env_active_override=True)
    root = result["subprojects"][0]
    assert root["missing_env"] == []
    assert root["status"] == "pass"
