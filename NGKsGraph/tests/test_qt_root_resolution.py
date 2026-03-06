from __future__ import annotations

from pathlib import Path

from ngksgraph.config import Config, QtConfig
from ngksgraph.qt import resolve_qt_toolchain


def _cfg(root: Path, *, libs: list[str] | None = None) -> Config:
    return Config(
        qt=QtConfig(enabled=True, qt_root=str(root), libs=libs or ["Qt6Widgets", "Qt6Core"])
    )


def test_qt_root_resolution_fills_tools_and_paths(tmp_path: Path) -> None:
    qt_root = tmp_path / "qt"
    (qt_root / "bin").mkdir(parents=True)
    (qt_root / "include" / "QtCore").mkdir(parents=True)
    (qt_root / "include" / "QtWidgets").mkdir(parents=True)
    (qt_root / "lib").mkdir(parents=True)

    cfg = _cfg(qt_root)
    resolved = resolve_qt_toolchain(cfg, check_exists=False)
    payload = resolved["resolved"]

    assert payload["moc_path"].endswith("bin/moc.exe") or payload["moc_path"].endswith("bin\\moc.exe")
    assert payload["uic_path"].endswith("bin/uic.exe") or payload["uic_path"].endswith("bin\\uic.exe")
    assert payload["rcc_path"].endswith("bin/rcc.exe") or payload["rcc_path"].endswith("bin\\rcc.exe")
    assert any("include" in p for p in payload["include_dirs"])
    assert any("lib" in p for p in payload["lib_dirs"])


def test_qt_root_resolution_preserves_explicit_tools(tmp_path: Path) -> None:
    qt_root = tmp_path / "qt"
    cfg = Config(
        qt=QtConfig(
            enabled=True,
            qt_root=str(qt_root),
            moc_path="C:/custom/moc.exe",
            uic_path="C:/custom/uic.exe",
            rcc_path="C:/custom/rcc.exe",
            libs=["Qt6Core"],
        )
    )

    resolved = resolve_qt_toolchain(cfg, check_exists=False)
    payload = resolved["resolved"]

    assert payload["moc_path"] == "C:/custom/moc.exe"
    assert payload["uic_path"] == "C:/custom/uic.exe"
    assert payload["rcc_path"] == "C:/custom/rcc.exe"
