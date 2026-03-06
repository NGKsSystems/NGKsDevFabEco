from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

from ngksgraph.build import configure_project, latest_diff_summary
from ngksgraph.capsule import freeze_capsule, verify_capsule

from tests.torture.gen_project import GeneratedProject, gen_project


def _hashes(configured: dict) -> tuple[str, str]:
    hashes = configured["snapshot_info"]["hashes"]
    return hashes["graph_hash"], hashes["compdb_hash"]


def _generator_fps(configured: dict) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {"moc": {}, "uic": {}, "rcc": {}}
    for node in configured["qt_result"].generator_nodes:
        out.setdefault(node.kind, {})[node.input] = node.fingerprint
    return out


def _single_node(configured: dict, kind: str):
    nodes = [n for n in configured["qt_result"].generator_nodes if n.kind == kind]
    assert nodes, f"expected at least one {kind} node"
    return nodes[0]


def test_qt_torture_scale_moc_many_headers(tmp_path):
    scale = int(os.environ.get("NGK_TORTURE_SCALE", "200"))
    if scale < 200:
        scale = 200

    project = gen_project(
        tmp_path,
        seed=1001,
        large_scale=False,
        qobject_headers=scale,
        ui_files=0,
        qrc_files=0,
    )

    first = configure_project(project.repo_root, project.config_path)
    moc_nodes = [n for n in first["qt_result"].generator_nodes if n.kind == "moc"]
    assert len(moc_nodes) == scale, f"expected {scale} moc nodes, got {len(moc_nodes)}"
    for node in moc_nodes:
        assert Path(node.output).exists(), f"expected generated moc output: {node.output}"

    first_hashes = _hashes(first)
    second = configure_project(project.repo_root, project.config_path)
    second_hashes = _hashes(second)
    assert first_hashes == second_hashes, "configure is not deterministic for graph/compdb hashes"


def test_qt_torture_paths_with_spaces_and_mixed_slashes(tmp_path):
    project = gen_project(tmp_path, seed=1002, path_with_spaces=True, mixed_slashes=True)

    configured = configure_project(project.repo_root, project.config_path)
    assert configured["ok"] is True

    compdb = configured["compdb"]
    app_commands = [entry["command"] for entry in compdb if "app_main.cpp" in entry["file"]]
    assert app_commands, "expected app compile command in compile_commands"
    assert any('"src/app/space dir/app_main.cpp"' in cmd for cmd in app_commands), (
        "compile command must quote source path containing spaces"
    )

    include_dirs = configured["graph"].targets["app"].include_dirs
    assert any(v.endswith("build/qt") for v in include_dirs), "Qt include injection missing build/qt path"


def test_qt_torture_duplicate_basenames_no_moc_collision(tmp_path):
    project = gen_project(tmp_path, seed=1003, duplicate_basenames=True, qobject_headers=6)

    configured = configure_project(project.repo_root, project.config_path)
    moc_nodes = [n for n in configured["qt_result"].generator_nodes if n.kind == "moc" and "EngineBridge.hpp" in n.input]
    assert len(moc_nodes) == 2, "expected two moc nodes for duplicate EngineBridge.hpp headers"

    outputs = [n.output for n in moc_nodes]
    assert len(set(outputs)) == 2, "duplicate basenames caused moc output collision"
    assert any("__" in Path(p).stem for p in outputs), "expected deterministic disambiguation suffix for duplicate basename"


def test_qt_torture_qrc_nested_resources_fingerprint_sensitivity(tmp_path):
    project = gen_project(tmp_path, seed=1004, qobject_headers=2, ui_files=0, qrc_files=1)

    first = configure_project(project.repo_root, project.config_path)
    rcc_a = _single_node(first, "rcc")

    referenced = project.repo_root / project.qrc_referenced_files[0]
    referenced.write_text(referenced.read_text(encoding="utf-8") + "mutate\n", encoding="utf-8")

    second = configure_project(project.repo_root, project.config_path)
    rcc_b = _single_node(second, "rcc")
    assert rcc_a.fingerprint != rcc_b.fingerprint, "rcc fingerprint must change when referenced resource changes"

    unrelated = project.repo_root / project.unrelated_files[0]
    unrelated.write_text(unrelated.read_text(encoding="utf-8") + "noise\n", encoding="utf-8")

    third = configure_project(project.repo_root, project.config_path)
    rcc_c = _single_node(third, "rcc")
    assert rcc_b.fingerprint == rcc_c.fingerprint, "rcc fingerprint must ignore unrelated file changes"


def test_qt_torture_uic_include_injection_and_determinism(tmp_path):
    project = gen_project(tmp_path, seed=1005, qobject_headers=0, ui_files=3, qrc_files=0)

    first = configure_project(project.repo_root, project.config_path)
    uic_nodes = [n for n in first["qt_result"].generator_nodes if n.kind == "uic"]
    assert uic_nodes, "expected uic generator nodes"

    include_dirs = first["graph"].targets["app"].include_dirs
    assert any(v.endswith("build/qt") for v in include_dirs), "build/qt include directory was not injected"

    first_hashes = _hashes(first)
    second = configure_project(project.repo_root, project.config_path)
    second_hashes = _hashes(second)
    assert first_hashes == second_hashes, "uic scenario is not deterministic across configure runs"


def test_qt_torture_ambiguous_source_ownership_fails_explicitly(tmp_path):
    project = gen_project(tmp_path, seed=1006, ambiguous_ownership=True, qobject_headers=1, ui_files=0, qrc_files=0)

    with pytest.raises(ValueError, match="AMBIGUOUS_OWNERSHIP") as exc:
        configure_project(project.repo_root, project.config_path)

    message = str(exc.value)
    assert "core" in message and "util" in message, "ambiguity error must list owning targets"


def test_qt_torture_tool_corruption_detected_by_capsule_verify(tmp_path):
    project = gen_project(tmp_path, seed=1007, qobject_headers=4, ui_files=1, qrc_files=1)

    freeze = freeze_capsule(repo_root=project.repo_root, config_path=project.config_path, target="app", verify=True)
    capsule = Path(freeze["capsule_path"])

    moc_tool = Path(project.qt_paths["moc_path"])
    moc_tool.write_text("@echo off\necho tampered\n", encoding="utf-8")

    result = verify_capsule(capsule)
    assert result["ok"] is False, "capsule verify must fail after Qt tool corruption"
    assert any(m["component"] in {"qt_tool.moc.sha256", "qt_tool.moc.version"} for m in result["mismatches"])


def test_qt_torture_concurrency_parallel_configure_isolated(tmp_path):
    project_a = gen_project(tmp_path / "a", seed=1010, qobject_headers=10, ui_files=1, qrc_files=1)
    project_b = gen_project(tmp_path / "b", seed=2020, qobject_headers=10, ui_files=1, qrc_files=1)

    def _run(project: GeneratedProject) -> tuple[tuple[str, str], tuple[str, str], list[str]]:
        first = configure_project(project.repo_root, project.config_path)
        second = configure_project(project.repo_root, project.config_path)
        return _hashes(first), _hashes(second), [n.output for n in first["qt_result"].generator_nodes]

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_run, project_a)
        fut_b = pool.submit(_run, project_b)
        a_first, a_second, a_outputs = fut_a.result()
        b_first, b_second, b_outputs = fut_b.result()

    assert a_first == a_second, "project A hashes changed across repeated configure"
    assert b_first == b_second, "project B hashes changed across repeated configure"

    a_root = str(project_a.repo_root.resolve()).replace("\\", "/")
    b_root = str(project_b.repo_root.resolve()).replace("\\", "/")
    assert all(v.startswith(a_root) for v in a_outputs), "project A outputs contaminated with foreign paths"
    assert all(v.startswith(b_root) for v in b_outputs), "project B outputs contaminated with foreign paths"


def test_qt_torture_random_mutation_fuzz_seeded(tmp_path):
    for seed in range(1, 26):
        project = gen_project(tmp_path / f"seed_{seed:02d}", seed=seed, qobject_headers=5, ui_files=1, qrc_files=1)

        first = configure_project(project.repo_root, project.config_path)
        fps_a = _generator_fps(first)

        mutation_mode = seed % 3
        expected_changed_kind = "moc"
        if mutation_mode == 0:
            path = project.repo_root / project.qobject_headers[0]
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            expected_changed_kind = "moc"
        elif mutation_mode == 1:
            path = project.repo_root / project.ui_files[0]
            path.write_text(path.read_text(encoding="utf-8") + "<!-- touch -->\n", encoding="utf-8")
            expected_changed_kind = "uic"
        else:
            path = project.repo_root / project.qrc_referenced_files[0]
            path.write_text(path.read_text(encoding="utf-8") + "res-change\n", encoding="utf-8")
            expected_changed_kind = "rcc"

        second = configure_project(project.repo_root, project.config_path)
        fps_b = _generator_fps(second)

        changed_kinds = {
            kind
            for kind in sorted(set(fps_a.keys()) | set(fps_b.keys()))
            if fps_a.get(kind, {}) != fps_b.get(kind, {})
        }
        assert changed_kinds == {expected_changed_kind}, (
            f"seed={seed}: expected only {expected_changed_kind} fingerprints to change, got {sorted(changed_kinds)}"
        )

        diff_summary = latest_diff_summary(project.repo_root / "build")
        if diff_summary is not None:
            assert diff_summary["changed_targets"] == [], f"seed={seed}: structural target changes were not expected"
