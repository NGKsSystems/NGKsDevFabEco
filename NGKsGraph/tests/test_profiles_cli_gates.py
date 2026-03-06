from __future__ import annotations

from ngksgraph.cli import main
from ngksgraph.torture_project import gen_project
import pytest


def test_doctor_profiles_gate_passes_with_profiles(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9201, qobject_headers=4, ui_files=1, qrc_files=1, with_profiles=True)
    monkeypatch.chdir(project.repo_root)

    rc = main(["doctor", "--profiles"])
    assert rc == 0


def test_doctor_profile_scoped_compdb_graph_gates(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9202, qobject_headers=4, ui_files=1, qrc_files=1, with_profiles=True)
    monkeypatch.chdir(project.repo_root)

    rc_compdb = main(["doctor", "--compdb", "--profile", "debug"])
    rc_graph = main(["doctor", "--graph", "--profile", "release"])

    assert rc_compdb == 0
    assert rc_graph == 0


def test_configure_requires_profile_when_profiles_defined(tmp_path, monkeypatch):
    project = gen_project(tmp_path, seed=9203, qobject_headers=2, ui_files=1, qrc_files=1, with_profiles=True)
    monkeypatch.chdir(project.repo_root)

    with pytest.raises(ValueError, match="--profile is required"):
        main(["configure"])
