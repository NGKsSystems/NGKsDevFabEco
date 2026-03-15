from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.capability.capability_types import CapabilityInventory, CapabilityRecord
from ngksgraph.cli import main
from ngksgraph.resolver import resolve_target_capabilities
from ngksgraph.targetspec.target_spec_types import CanonicalTargetSpec


def _record(name: str, status: str = "available", version: str = "", provider: str = "test") -> CapabilityRecord:
    return CapabilityRecord(
        capability_name=name,
        provider=provider,
        version=version,
        status=status,
        metadata={},
    )


def _spec(required: list[str], optional: list[str] | None = None) -> CanonicalTargetSpec:
    return CanonicalTargetSpec(
        target_name="NGKsFileVisionary",
        target_type="desktop_app",
        language="c++",
        platform="windows",
        configuration="debug",
        required_capabilities=required,
        optional_capabilities=list(optional or []),
        policy_flags={"fail_on_missing_required_capability": True},
        source_roots=["src"],
        entrypoints=["src/main.cpp"],
    )


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(
        "\n".join(
            [
                'name = "app"',
                'out_dir = "build"',
                '',
                '[profiles.debug]',
                'cflags = []',
                'defines = []',
                'ldflags = []',
                '',
                '[[targets]]',
                'name = "app"',
                'type = "exe"',
                'src_glob = ["src/**/*.cpp"]',
                'include_dirs = ["include"]',
                'defines = []',
                'cflags = []',
                'libs = []',
                'lib_dirs = []',
                'ldflags = []',
                'cxx_std = 17',
                'links = []',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_healthy_cpp_qt_target_resolution() -> None:
    spec = _spec(
        required=[
            "cxx.compiler",
            "cxx.standard:17",
            "qt.core",
            "qt.gui",
            "qt.widgets",
            "qt.sql",
            "windows.sdk",
            "msvc.linker",
        ],
        optional=["pdb.debug", "windeployqt"],
    )
    inv = CapabilityInventory(
        records=[
            _record("cxx.compiler"),
            _record("cxx.standard.active", version="20"),
            _record("qt.core"),
            _record("qt.gui"),
            _record("qt.widgets"),
            _record("qt.sql"),
            _record("windows.sdk"),
            _record("msvc.linker"),
            _record("pdb.debug"),
            _record("windeployqt"),
        ]
    )

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is True
    assert len(report.missing) == 0
    assert len(report.downgraded) == 0


def test_missing_qt_component_resolution() -> None:
    spec = _spec(required=["qt.sql"])
    inv = CapabilityInventory(records=[_record("qt.sql", status="missing")])

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is False
    assert any(row.capability == "qt.sql" for row in report.missing)


def test_compiler_present_but_standard_unsatisfied() -> None:
    spec = _spec(required=["cxx.compiler", "cxx.standard:17"])
    inv = CapabilityInventory(
        records=[
            _record("cxx.compiler", status="available"),
            _record("cxx.standard.active", status="missing", version=""),
        ]
    )

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is False
    assert any(row.capability == "cxx.standard:17" for row in report.missing)
    assert any(row.classification == "inferred" and row.capability == "cxx.compiler" for row in report.inferred)


def test_missing_linker_capability_resolution() -> None:
    spec = _spec(required=["msvc.linker"])
    inv = CapabilityInventory(records=[_record("msvc.linker", status="missing")])

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is False
    assert any(row.capability == "msvc.linker" for row in report.missing)


def test_optional_capability_absent_still_allows_build() -> None:
    spec = _spec(required=["cxx.compiler"], optional=["windeployqt"])
    inv = CapabilityInventory(records=[_record("cxx.compiler", status="available")])

    report = resolve_target_capabilities(target_spec=spec, inventory=inv)
    assert report.build_allowed is True
    assert any(row.capability == "windeployqt" for row in report.optional_missing)


def test_ecosystem_plan_blocks_before_plan_when_required_capability_missing(tmp_path: Path, monkeypatch) -> None:
    project = _make_project(tmp_path)
    monkeypatch.chdir(project)

    hash_path = project / "env_capsule.hash.txt"
    hash_path.write_text("0" * 64 + "\n", encoding="utf-8")

    spec_payload = {
        "target_name": "app",
        "target_type": "desktop_app",
        "language": "c++",
        "platform": "windows",
        "configuration": "debug",
        "required_capabilities": ["msvc.linker"],
        "optional_capabilities": ["windeployqt"],
        "policy_flags": {"fail_on_missing_required_capability": True},
        "source_roots": ["src"],
        "entrypoints": ["src/main.cpp"],
    }
    (project / "ngks_target_spec.json").write_text(json.dumps(spec_payload, indent=2), encoding="utf-8")

    def _forced_missing_inventory(*, config, target):
        del config, target
        return CapabilityInventory(records=[_record("msvc.linker", status="missing")])

    monkeypatch.setattr("ngksgraph.cli.build_capability_inventory", _forced_missing_inventory)

    rc = main(
        [
            "plan",
            "--project",
            str(project),
            "--profile",
            "debug",
            "--mode",
            "ecosystem",
            "--env-capsule-hash",
            str(hash_path),
            "--target",
            "app",
        ]
    )
    assert rc == 2

    resolution_dir = project / "build_graph" / "debug" / "resolution"
    assert (resolution_dir / "14_resolution_report.json").exists()
    payload = json.loads((resolution_dir / "14_resolution_report.json").read_text(encoding="utf-8"))
    assert payload["build_allowed"] is False

    plan_path = project / "build_plan.json"
    assert not plan_path.exists()
