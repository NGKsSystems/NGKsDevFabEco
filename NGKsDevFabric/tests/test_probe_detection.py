from __future__ import annotations

from pathlib import Path

from ngksdevfabric.ngk_fabric import probe as probe_mod


def test_probe_prefers_flutter_over_generated_windows_graph_artifacts(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text("name: demo_flutter\n", encoding="utf-8")
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")

    generated = tmp_path / "build" / "windows" / "x64"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "demo.sln").write_text("Microsoft Visual Studio Solution File\n", encoding="utf-8")
    (generated / "demo.vcxproj").write_text("<Project></Project>\n", encoding="utf-8")

    fingerprint_map, _ = probe_mod._build_fingerprints(tmp_path, max_depth=8, max_files=2000)
    primary, secondary, confidence, reasons = probe_mod._classify(fingerprint_map)

    assert primary == "flutter"
    assert "graph" in secondary
    assert confidence >= 80
    assert any("pubspec.yaml" in reason for reason in reasons)


def test_probe_keeps_graph_primary_when_solution_is_not_generated(tmp_path: Path):
    (tmp_path / "app.sln").write_text("Microsoft Visual Studio Solution File\n", encoding="utf-8")

    fingerprint_map, _ = probe_mod._build_fingerprints(tmp_path)
    primary, _, _, reasons = probe_mod._classify(fingerprint_map)

    assert primary == "graph"
    assert any("Solution/project files found" in reason for reason in reasons)


def test_flutter_recommended_commands_include_flutter_and_dart():
    commands = probe_mod._recommended_commands(
        "flutter",
        {
            "flutter_pubspec": ["pubspec.yaml"],
            "dart_sources": ["lib/main.dart"],
            "sln": [],
            "vcxproj": [],
            "meson": [],
            "npm": [],
            "python_pyproject": [],
            "python_requirements": [],
            "bootstrap_msvc_cmd": [],
            "bootstrap_enter_msvc_ps1": [],
            "bootstrap_build_ps1": [],
            "scripts_folder": [],
            "build_dirs_build": [],
            "build_dirs_out": [],
            "build_dirs_vs": [],
            "csproj": [],
        },
    )

    assert "flutter doctor -v" in commands
    assert "dart --version" in commands
