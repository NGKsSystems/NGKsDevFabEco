from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.build import build_project, configure_project
from ngksgraph.torture_project import gen_project


REQUIRED_DURATIONS = {
    "load_config_ms",
    "scan_tree_ms",
    "qt_detect_ms",
    "plan_build_ms",
    "emit_compdb_ms",
    "validate_contracts_ms",
    "total_configure_ms",
    "total_build_ms",
}


def _report(project_root: Path, profile: str) -> dict:
    report_path = project_root / "build" / profile / "ngksgraph_build_report.json"
    assert report_path.exists(), f"missing report: {report_path}"
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_perf_report_configure_fields_and_cache_toggle(tmp_path: Path):
    project = gen_project(tmp_path, seed=9401, qobject_headers=3, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    report_a = _report(project.repo_root, "debug")

    assert report_a.get("profile") == "debug"
    assert report_a.get("cache_hit") is False
    assert set(report_a.get("durations", {}).keys()) >= REQUIRED_DURATIONS
    assert isinstance(report_a.get("key_hashes", {}).get("plan_key_sha", ""), str)
    assert isinstance(report_a.get("key_hashes", {}).get("fingerprint_sha", ""), str)
    assert isinstance(report_a.get("contract_outcomes", {}).get("compdb_contract_pass"), bool)
    assert isinstance(report_a.get("contract_outcomes", {}).get("graph_contract_pass"), bool)

    configure_project(project.repo_root, project.config_path, profile="debug")
    report_b = _report(project.repo_root, "debug")

    assert report_b.get("cache_hit") is True
    assert report_b.get("durations", {}).get("total_configure_ms") is not None


def test_perf_report_build_handoff_sets_total_build_time(tmp_path: Path, monkeypatch):
    project = gen_project(tmp_path, seed=9402, qobject_headers=2, ui_files=1, qrc_files=1, with_profiles=True)

    configure_project(project.repo_root, project.config_path, profile="debug")
    monkeypatch.setattr("ngksgraph.build.has_cl_link", lambda env: False)

    rc = build_project(project.repo_root, project.config_path, profile="debug")
    assert rc == 0

    report = _report(project.repo_root, "debug")
    durations = report.get("durations", {})
    assert isinstance(durations.get("total_build_ms"), int)
