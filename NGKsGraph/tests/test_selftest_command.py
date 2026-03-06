from __future__ import annotations

import json
from pathlib import Path

from ngksgraph.cli import main


def test_selftest_command_pass_small(tmp_path):
    out_dir = tmp_path / "selftest_pass"
    rc = main(
        [
            "selftest",
            "--scale",
            "20",
            "--seeds",
            "1..1",
            "--json-only",
            "--out",
            str(out_dir),
            "--timeout",
            "120",
        ]
    )

    assert rc == 0
    report_path = out_dir / "report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["phase"] == "6F"
    assert report["pass"] is True
    assert report["seeds"] == [1]
    assert len(report["results"]) > 0


def test_selftest_command_fail_path_injected_corruption(tmp_path):
    out_dir = tmp_path / "selftest_fail"
    rc = main(
        [
            "selftest",
            "--scale",
            "20",
            "--seeds",
            "1..1",
            "--json-only",
            "--out",
            str(out_dir),
            "--timeout",
            "120",
            "--fail-fast",
            "--_inject-corruption-failure",
        ]
    )

    assert rc == 2
    report_path = out_dir / "report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["pass"] is False
    assert report["failures"], "expected at least one failure entry"
    assert any(item.get("name") == "capsule.corruption.detect" for item in report["failures"])
    assert any(item.get("repro_path") for item in report["failures"])


def test_selftest_command_profiles_mode(tmp_path):
    out_dir = tmp_path / "selftest_profiles"
    rc = main(
        [
            "selftest",
            "--profiles",
            "--scale",
            "10",
            "--seeds",
            "1..1",
            "--json-only",
            "--out",
            str(out_dir),
            "--timeout",
            "180",
        ]
    )

    assert rc == 0
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    names = {item.get("name") for item in report.get("results", [])}
    assert "profiles.parity" in names
