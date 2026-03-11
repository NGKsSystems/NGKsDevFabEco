from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.cli import main
from ngksgraph.scan_pipeline import run_scan


def test_scan_emits_phase_artifacts_for_cpp_repo(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    out_dir = tmp_path / "scan_out"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--json"])

    assert rc == 0
    for name in [
        "01_probe_facts.json",
        "02_classified_evidence.json",
        "03_detected_stack.json",
        "04_downstream_requirements.json",
        "05_build_authority.json",
        "06_stale_risk_report.json",
        "07_contradictions.json",
        "08_environment_contract.json",
        "09_native_plan.json",
        "SUMMARY.md",
        "native_contract.json",
        "plan_diff.json",
    ]:
        assert (out_dir / name).exists(), f"missing artifact {name}"

    detected = json.loads((out_dir / "03_detected_stack.json").read_text(encoding="utf-8"))
    languages = detected["subprojects"][0]["languages"]
    assert any(item["name"] == "C++" for item in languages)


def test_scan_detects_qt_implication_rule(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text(
        "#include <QApplication>\nint main(int argc, char** argv){QApplication app(argc, argv);return 0;}\n",
        encoding="utf-8",
    )
    (tmp_path / "CMakeLists.txt").write_text("find_package(Qt6 REQUIRED COMPONENTS Core Widgets)\n", encoding="utf-8")

    out_dir = tmp_path / "scan_qt"
    result = run_scan(repo_root=tmp_path, out_dir=out_dir)

    assert result.status in {"PASS", "PASS_WITH_WARNINGS", "FAIL_CLOSED"}
    requirements = json.loads((out_dir / "04_downstream_requirements.json").read_text(encoding="utf-8"))
    ids = {item["requirement_id"] for item in requirements["requirements"]}
    assert "qt6_msvc_cpp17" in ids

    detected = json.loads((out_dir / "03_detected_stack.json").read_text(encoding="utf-8"))
    detection_rule_ids = {item.get("id") for item in detected.get("detection_rule_hits", [])}
    assert "detect_qt6_cmake" in detection_rule_ids


def test_scan_fail_closed_for_manifest_source_contradiction(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").write_text("<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")

    out_dir = tmp_path / "scan_dotnet"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--json"])

    assert rc == 2
    contradictions = json.loads((out_dir / "07_contradictions.json").read_text(encoding="utf-8"))
    assert len(contradictions["contradictions"]) >= 1


def test_scan_blueprint_rule_and_schema_assets_exist() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for rel in [
        "ngksgraph/rules/detection_rules.json",
        "ngksgraph/rules/implication_rules.json",
        "ngksgraph/rules/authority_rules.json",
        "ngksgraph/rules/stale_rules.json",
        "ngksgraph/rules/contradiction_rules.json",
        "ngksgraph/schemas/probe_facts.schema.json",
        "ngksgraph/schemas/classified_evidence.schema.json",
        "ngksgraph/schemas/detected_stack.schema.json",
        "ngksgraph/schemas/downstream_requirements.schema.json",
        "ngksgraph/schemas/build_authority.schema.json",
        "ngksgraph/schemas/stale_risk_report.schema.json",
        "ngksgraph/schemas/contradictions.schema.json",
        "ngksgraph/schemas/environment_contract.schema.json",
        "ngksgraph/schemas/native_plan.schema.json",
    ]:
        assert (repo_root / rel).exists(), f"missing asset {rel}"


def test_scan_subproject_language_scoping(tmp_path: Path) -> None:
    (tmp_path / "cpp_app" / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "py_pkg").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cpp_app" / "CMakeLists.txt").write_text("project(CppApp)\n", encoding="utf-8")
    (tmp_path / "cpp_app" / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "py_pkg" / "pyproject.toml").write_text("[project]\nname='py_pkg'\n", encoding="utf-8")
    (tmp_path / "py_pkg" / "module.py").write_text("print('hi')\n", encoding="utf-8")

    out_dir = tmp_path / "scan_subprojects"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--json"])

    assert rc in {0, 2}
    detected = json.loads((out_dir / "03_detected_stack.json").read_text(encoding="utf-8"))
    by_root = {item["root_path"]: item for item in detected["subprojects"]}
    assert "cpp_app" in by_root
    cpp_langs = {lang["name"] for lang in by_root["cpp_app"]["languages"]}
    assert "C++" in cpp_langs


def test_scan_bootstrap_venv_creates_missing_project_venv(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")

    out_dir = tmp_path / "scan_bootstrap"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--bootstrap-venv", "--json"])

    assert rc in {0, 2}
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    assert venv_python.exists(), "bootstrap venv should create .venv interpreter"


def test_scan_accepts_bootstrap_msvc_flag(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    out_dir = tmp_path / "scan_bootstrap_msvc"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--bootstrap-msvc", "--json"])

    assert rc in {0, 2}
    assert (out_dir / "01_probe_facts.json").exists()


def test_summary_includes_blueprint_sections(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text("project(Demo)\n", encoding="utf-8")

    out_dir = tmp_path / "scan_summary"
    rc = main(["scan", "--project", str(tmp_path), "--out", str(out_dir), "--json"])

    assert rc in {0, 2}
    summary = (out_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "- subprojects:" in summary
    assert "- standards:" in summary
    assert "- required_env:" in summary
    assert "- generated_artifacts:" in summary
    assert "- blocked_foreign_files:" in summary
    assert "- trust_issues:" in summary
    assert "- stale_poisoning_risk_high:" in summary
