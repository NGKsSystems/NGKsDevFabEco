from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.build import _apply_cached_target_overrides, configure_project
from ngksgraph.cli import main
from ngksgraph.config import load_config
from ngksgraph.graph import build_graph_from_project
from ngksgraph.graph_contract import compute_structural_graph_hash
from ngksgraph.plan_cache import build_plan_key, json_sha
from ngksgraph.torture_project import gen_project


def _state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_graph_bytes(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload.pop("generated_at", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_plan_cache_hit_when_unchanged(tmp_path: Path):
    project = gen_project(tmp_path, seed=9301, qobject_headers=4, ui_files=1, qrc_files=1, with_profiles=True)

    first = configure_project(project.repo_root, project.config_path, profile="debug")
    second = configure_project(project.repo_root, project.config_path, profile="debug")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["cache_reason"] == "HIT"


def test_plan_cache_miss_when_config_changes(tmp_path: Path):
    project = gen_project(tmp_path, seed=9302, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    text = project.config_path.read_text(encoding="utf-8")
    project.config_path.write_text(text.replace('cflags = ["/Od", "/Zi"]', 'cflags = ["/Od", "/Zi", "/W4"]'), encoding="utf-8")

    result = configure_project(project.repo_root, project.config_path, profile="debug")
    assert result["cache_hit"] is False
    assert result["cache_reason"] in {"KEY_CHANGED", "FINGERPRINT_CHANGED", "NO_CACHE", "CACHE_CONTRACT_FAIL", "CORRUPT_PLAN"}


def test_plan_cache_miss_when_file_content_changes(tmp_path: Path):
    project = gen_project(tmp_path, seed=9303, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    src = project.repo_root / "src" / "core" / "core.cpp"
    src.write_text("int core_fn(){return 777;}\n", encoding="utf-8")

    result = configure_project(project.repo_root, project.config_path, profile="debug")
    assert result["cache_hit"] is False


def test_plan_cache_miss_when_file_list_changes(tmp_path: Path):
    project = gen_project(tmp_path, seed=9304, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    extra = project.repo_root / "src" / "app" / "new_unit.cpp"
    extra.write_text("int phase9_new_unit(){return 1;}\n", encoding="utf-8")

    result = configure_project(project.repo_root, project.config_path, profile="debug")
    assert result["cache_hit"] is False


def test_plan_cache_corruption_triggers_regen(tmp_path: Path):
    project = gen_project(tmp_path, seed=9305, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    plan_path = project.repo_root / ".ngksgraph_cache" / "profile_debug" / "plan.json"
    plan_path.write_text("{", encoding="utf-8")

    result = configure_project(project.repo_root, project.config_path, profile="debug")
    assert result["cache_hit"] is False
    assert (project.repo_root / "build" / "debug" / "ngksgraph_graph.json").exists()
    assert (project.repo_root / "build" / "debug" / "compile_commands.json").exists()


def test_plan_cache_deterministic_outputs_cached_vs_noncached(tmp_path: Path):
    project = gen_project(tmp_path, seed=9306, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    first = configure_project(project.repo_root, project.config_path, profile="debug", no_cache=True, clear_cache=True)
    graph_a = _normalized_graph_bytes(first["paths"]["graph"])
    compdb_a = first["paths"]["compdb"].read_bytes()

    second = configure_project(project.repo_root, project.config_path, profile="debug")
    third = configure_project(project.repo_root, project.config_path, profile="debug")

    graph_b = _normalized_graph_bytes(second["paths"]["graph"])
    compdb_b = second["paths"]["compdb"].read_bytes()
    graph_c = _normalized_graph_bytes(third["paths"]["graph"])
    compdb_c = third["paths"]["compdb"].read_bytes()

    assert second["cache_hit"] is False
    assert third["cache_hit"] is True
    assert graph_a == graph_b == graph_c
    assert compdb_a == compdb_b == compdb_c


def test_doctor_cache_hit(tmp_path: Path, monkeypatch):
    project = gen_project(tmp_path, seed=9307, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)
    configure_project(project.repo_root, project.config_path, profile="debug")
    configure_project(project.repo_root, project.config_path, profile="debug")

    monkeypatch.chdir(project.repo_root)
    rc = main(["doctor", "--cache", "--profile", "debug"])
    assert rc == 0


def test_doctor_cache_corruption_exit2(tmp_path: Path, monkeypatch):
    project = gen_project(tmp_path, seed=9308, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)
    configure_project(project.repo_root, project.config_path, profile="debug")
    (project.repo_root / ".ngksgraph_cache" / "profile_debug" / "plan_key.json").write_text("{", encoding="utf-8")

    monkeypatch.chdir(project.repo_root)
    rc = main(["doctor", "--cache", "--profile", "debug"])
    assert rc == 2


def test_cache_hit_reintegrates_qt_generated_sources(tmp_path: Path):
    project = gen_project(tmp_path, seed=9309, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    first = configure_project(project.repo_root, project.config_path, profile="debug")
    assert first["cache_hit"] is False

    cache_profile = project.repo_root / ".ngksgraph_cache" / "profile_debug"
    plan_path = cache_profile / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    stale_map: dict[str, list[str]] = {}
    for target_name, sources in dict(plan.get("source_map", {})).items():
        kept = [
            src
            for src in list(sources)
            if "build/debug/qt/moc_" not in src.replace("\\", "/") and "build/debug/qt/qrc_" not in src.replace("\\", "/")
        ]
        stale_map[target_name] = kept
    plan["source_map"] = stale_map
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")

    config = load_config(project.config_path)
    selected_profile = config.apply_profile("debug")
    assert selected_profile == "debug"
    selected_target = config.default_target_name()
    _apply_cached_target_overrides(config, plan)
    graph = build_graph_from_project(config, source_map=stale_map, msvc_auto=False)
    plan_key = build_plan_key(project.config_path, selected_profile, selected_target, compute_structural_graph_hash(graph), config)
    (cache_profile / "plan_key.json").write_text(json.dumps(plan_key, indent=2, sort_keys=True), encoding="utf-8")
    (cache_profile / "plan_key.sha256").write_text(json_sha(plan_key), encoding="utf-8")

    second = configure_project(project.repo_root, project.config_path, profile="debug")
    assert second["cache_hit"] is True

    selected_sources = second["source_map"][selected_target]
    assert any("build/debug/qt/moc_" in src.replace("\\", "/") for src in selected_sources)
