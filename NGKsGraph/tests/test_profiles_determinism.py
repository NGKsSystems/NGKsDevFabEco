from __future__ import annotations

from ngksgraph.build import configure_project
from ngksgraph.compdb_contract import compdb_hash, load_compdb
from ngksgraph.graph_contract import compute_structural_graph_hash, expected_link_inputs, validate_profile_parity
from ngksgraph.torture_project import gen_project
import pytest


def test_profiles_require_explicit_selection(tmp_path):
    project = gen_project(tmp_path, seed=9100, qobject_headers=2, ui_files=1, qrc_files=1, with_profiles=True)
    with pytest.raises(ValueError, match="--profile is required"):
        configure_project(project.repo_root, project.config_path)


def test_profile_directory_isolation(tmp_path):
    project = gen_project(tmp_path, seed=9101, qobject_headers=6, ui_files=1, qrc_files=1, with_profiles=True)

    debug = configure_project(project.repo_root, project.config_path, profile="debug")
    release = configure_project(project.repo_root, project.config_path, profile="release")

    assert debug["paths"]["out_dir"] != release["paths"]["out_dir"]
    assert str(debug["paths"]["out_dir"]).replace("\\", "/").endswith("build/debug")
    assert str(release["paths"]["out_dir"]).replace("\\", "/").endswith("build/release")
    assert debug["paths"]["compdb"].exists()
    assert release["paths"]["compdb"].exists()


def test_profile_structural_hash_equal(tmp_path):
    project = gen_project(tmp_path, seed=9102, qobject_headers=6, ui_files=1, qrc_files=1, with_profiles=True)

    debug = configure_project(project.repo_root, project.config_path, profile="debug")
    release = configure_project(project.repo_root, project.config_path, profile="release")

    assert compute_structural_graph_hash(debug["graph"]) == compute_structural_graph_hash(release["graph"])


def test_profile_compdb_deterministic(tmp_path):
    project = gen_project(tmp_path, seed=9103, qobject_headers=6, ui_files=1, qrc_files=1, with_profiles=True)

    for profile in ["debug", "release"]:
        first = configure_project(project.repo_root, project.config_path, profile=profile)
        path = first["paths"]["compdb"]
        bytes_a = path.read_bytes()
        hash_a = compdb_hash(load_compdb(path))

        second = configure_project(project.repo_root, project.config_path, profile=profile)
        path2 = second["paths"]["compdb"]
        bytes_b = path2.read_bytes()
        hash_b = compdb_hash(load_compdb(path2))

        assert bytes_a == bytes_b, f"compile_commands bytes changed across repeated configure for profile={profile}"
        assert hash_a == hash_b, f"normalized compdb hash changed across repeated configure for profile={profile}"


def test_profile_link_plan_deterministic(tmp_path):
    project = gen_project(tmp_path, seed=9104, qobject_headers=6, ui_files=1, qrc_files=1, with_profiles=True)

    for profile in ["debug", "release"]:
        first = configure_project(project.repo_root, project.config_path, profile=profile)
        second = configure_project(project.repo_root, project.config_path, profile=profile)

        assert expected_link_inputs(first["graph"], first["config"]) == expected_link_inputs(second["graph"], second["config"])


def test_profile_parity_validator_detects_drift(tmp_path):
    project = gen_project(tmp_path, seed=9105, qobject_headers=6, ui_files=1, qrc_files=1, with_profiles=True)

    debug = configure_project(project.repo_root, project.config_path, profile="debug")
    release = configure_project(project.repo_root, project.config_path, profile="release")

    # Simulate structural drift.
    release["graph"].targets["app"].sources.append("src/app/fake_drift.cpp")

    violations = validate_profile_parity(debug["graph"], release["graph"])
    codes = {v.get("code") for v in violations}
    assert "STRUCTURAL_DRIFT" in codes
