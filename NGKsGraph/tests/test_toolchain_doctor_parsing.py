from __future__ import annotations

from pathlib import Path

from ngksgraph.toolchain import doctor_toolchain_report


def test_doctor_toolchain_profile_echoes_selected_profile(tmp_path: Path) -> None:
    cfg = tmp_path / "ngksgraph.toml"
    cfg.write_text(
        """
name = "doctor_parse"
version = "0.1.0"

[profiles.debug]
optimize = "off"

[[targets]]
name = "app"
type = "exe"
src_glob = ["src/**/*.cpp"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    ok, lines, _corrupt = doctor_toolchain_report(config_path=cfg, profile="debug")
    out = "\n".join(lines)

    assert "profile: debug" in out
    assert "cl:" in out
    assert isinstance(ok, bool)


def test_doctor_toolchain_qt_root_missing_reports_paths(tmp_path: Path) -> None:
    cfg = tmp_path / "ngksgraph.toml"
    cfg.write_text(
        """
name = "doctor_qt"
version = "0.1.0"

[profiles.debug]
optimize = "off"

[qt]
enabled = true
qt_root = "C:/definitely_missing_qt_root"
libs = ["Qt6Widgets", "Qt6Core"]

[[targets]]
name = "app"
type = "exe"
src_glob = ["src/**/*.cpp"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    ok, lines, _corrupt = doctor_toolchain_report(config_path=cfg, profile="debug")
    out = "\n".join(lines)

    assert "qt.error:" in out
    assert "Qt root not found" in out
    assert ok is False
