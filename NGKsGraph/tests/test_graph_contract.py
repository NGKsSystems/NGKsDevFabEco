from __future__ import annotations

from pathlib import Path

from ngksgraph.build import configure_project
from ngksgraph.graph_contract import (
    expected_compile_units,
    expected_link_inputs,
    expected_objects,
    validate_graph_integrity,
)
from ngksgraph.torture_project import gen_project


def test_graph_link_inputs_deterministic(tmp_path):
    project = gen_project(tmp_path, seed=8101, qobject_headers=8, ui_files=1, qrc_files=1)

    first = configure_project(project.repo_root, project.config_path)
    links_a = expected_link_inputs(first["graph"], first["config"])

    second = configure_project(project.repo_root, project.config_path)
    links_b = expected_link_inputs(second["graph"], second["config"])

    assert links_a == links_b, "link input plan changed across repeated configure runs"


def test_graph_no_orphan_objects_in_plan(tmp_path):
    project = gen_project(tmp_path, seed=8102, qobject_headers=6, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    objects = expected_objects(configured["graph"], configured["config"])
    owner_map: dict[str, set[str]] = {}
    for target_name, obj_set in objects.items():
        for obj in obj_set:
            owner_map.setdefault(obj, set()).add(target_name)

    dupes = {obj: sorted(list(owners)) for obj, owners in owner_map.items() if len(owners) > 1}
    assert not dupes, f"each planned object must belong to exactly one target: {dupes}"


def test_graph_detects_missing_dependency(tmp_path):
    project = gen_project(tmp_path, seed=8103, qobject_headers=4, ui_files=1, qrc_files=1, omit_app_util_link=True)
    configured = configure_project(project.repo_root, project.config_path)

    links = expected_link_inputs(configured["graph"], configured["config"])
    app_inputs = links.get("app", [])
    assert not any(v.endswith("build/lib/util.lib") for v in app_inputs)
    violations = validate_graph_integrity(configured["graph"], configured["config"], configured["paths"]["out_dir"])
    assert not violations


def test_graph_accounts_for_qt_generated_units(tmp_path):
    project = gen_project(tmp_path, seed=8104, qobject_headers=5, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    units = expected_compile_units(configured["graph"], configured["config"])
    all_units = sorted({u for values in units.values() for u in values})

    assert any("build/qt/moc_" in u for u in all_units), "moc generated compile unit missing from expected compile units"
    assert any("build/qt/qrc_" in u for u in all_units), "qrc generated compile unit missing from expected compile units"

    links = expected_link_inputs(configured["graph"], configured["config"])
    app_inputs = links.get("app", [])
    assert any("build/qt/moc_" in v and v.endswith(".obj") for v in app_inputs), "moc objects missing from app link inputs"
    assert any("build/qt/qrc_" in v and v.endswith(".obj") for v in app_inputs), "qrc objects missing from app link inputs"
