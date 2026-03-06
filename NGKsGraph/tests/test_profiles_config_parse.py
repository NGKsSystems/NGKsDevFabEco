from __future__ import annotations

from ngksgraph.config import load_config
from ngksgraph.torture_project import gen_project


def test_profiles_roundtrip_parse(tmp_path):
    project = gen_project(tmp_path, seed=9301, qobject_headers=2, ui_files=1, qrc_files=1, with_profiles=True)
    cfg = load_config(project.config_path)

    assert cfg.has_profiles() is True
    assert set(cfg.profile_names()) == {"debug", "release"}

    debug = cfg.profiles["debug"]
    release = cfg.profiles["release"]

    assert "NGKS_PROFILE_DEBUG" in debug.defines
    assert "NGKS_PROFILE_RELEASE" in release.defines
