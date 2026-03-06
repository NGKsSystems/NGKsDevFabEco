from __future__ import annotations

from pathlib import Path
import re

from ngksgraph.build import configure_project
from ngksgraph.compdb_contract import compdb_hash, load_compdb, validate_compdb

from tests.torture.gen_project import gen_project


def _has_generated_sources(entries: list[dict]) -> tuple[bool, bool]:
    files = [str(v.get("file", "")).replace("\\", "/") for v in entries]
    has_moc = any("/moc_" in f for f in files)
    has_qrc = any("/qrc_" in f for f in files)
    return has_moc, has_qrc


def test_compdb_deterministic_bytes(tmp_path):
    project = gen_project(tmp_path, seed=7001, qobject_headers=12, ui_files=1, qrc_files=1)

    first = configure_project(project.repo_root, project.config_path)
    compdb_path = first["paths"]["compdb"]
    bytes_a = compdb_path.read_bytes()
    hash_a = compdb_hash(load_compdb(compdb_path))

    second = configure_project(project.repo_root, project.config_path)
    compdb_path_2 = second["paths"]["compdb"]
    bytes_b = compdb_path_2.read_bytes()
    hash_b = compdb_hash(load_compdb(compdb_path_2))

    assert bytes_a == bytes_b, "compile_commands.json bytes changed between identical configure runs"
    assert hash_a == hash_b, "normalized compile_commands hash changed between identical configure runs"


def test_compdb_contains_expected_entries(tmp_path):
    project = gen_project(tmp_path, seed=7002, qobject_headers=10, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    compdb_path = configured["paths"]["compdb"]
    entries = load_compdb(compdb_path)
    violations = validate_compdb(entries, configured["graph"], configured["config"])

    missing_or_extra = [v for v in violations if v.get("code") in {"MISSING_ENTRY", "EXTRA_ENTRY"}]
    assert not missing_or_extra, f"compdb coverage violations detected: {missing_or_extra}"

    has_moc, has_qrc = _has_generated_sources(entries)
    assert has_moc, "expected generated moc translation units in compile_commands"
    assert has_qrc, "expected generated qrc translation units in compile_commands"


def test_compdb_includes_generated_qt_dir(tmp_path):
    project = gen_project(tmp_path, seed=7003, qobject_headers=6, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    entries = load_compdb(configured["paths"]["compdb"])
    violations = validate_compdb(entries, configured["graph"], configured["config"])

    generated_include_missing = [v for v in violations if v.get("code") == "MISSING_GENERATED_INCLUDE"]
    assert not generated_include_missing, f"missing generated include dir violations: {generated_include_missing}"

    for entry in entries:
        command = str(entry.get("command", ""))
        assert "/build/qt" in command.replace("\\", "/"), "expected generated build/qt include dir in every TU command"


def test_compdb_quotes_paths_with_spaces(tmp_path):
    project = gen_project(tmp_path, seed=7004, path_with_spaces=True, mixed_slashes=True, qobject_headers=8, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    entries = load_compdb(configured["paths"]["compdb"])
    violations = validate_compdb(entries, configured["graph"], configured["config"])
    bad_quotes = [v for v in violations if v.get("code") == "BAD_QUOTING"]
    assert not bad_quotes, f"quoting violations found: {bad_quotes}"


def test_compdb_validator_catches_missing_generated_include(tmp_path):
    project = gen_project(tmp_path, seed=7005, qobject_headers=6, ui_files=1, qrc_files=1)
    configured = configure_project(project.repo_root, project.config_path)

    entries = load_compdb(configured["paths"]["compdb"])
    tampered: list[dict] = []
    for entry in entries:
        command = str(entry.get("command", ""))
        command = re.sub(r'\s(?:/I|-I)(?:"[^"]*build/qt"|\S*build/qt\S*)', "", command.replace("\\", "/"))
        copy = dict(entry)
        copy["command"] = command
        tampered.append(copy)

    violations = validate_compdb(tampered, configured["graph"], configured["config"])
    codes = {v.get("code") for v in violations}
    assert "MISSING_GENERATED_INCLUDE" in codes
