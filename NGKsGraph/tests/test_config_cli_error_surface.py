from __future__ import annotations

import sys
from pathlib import Path

from ngksgraph.cli import main


def test_cli_invalid_qt_version_reports_clean_config_error_without_traceback(tmp_path, monkeypatch, capsys):
    repo_root = Path(tmp_path)
    (repo_root / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    (repo_root / "ngksgraph.toml").write_text(
        "\n".join(
            [
                'name = "app"',
                'out_dir = "build"',
                'target_type = "exe"',
                'src_glob = ["src/**/*.cpp"]',
                "",
                "[profiles.debug]",
                'cflags = []',
                'defines = []',
                'ldflags = []',
                "",
                "[qt]",
                "enabled = false",
                'prefix = ""',
                'version = "banana"',
                "modules = []",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(sys, "argv", ["ngksgraph", "configure", "--profile", "debug"])

    rc = main(None)
    captured = capsys.readouterr()

    assert rc == 1
    assert "CONFIG_ERROR:" in captured.err
    assert "qt.version" in captured.err
    assert "Traceback" not in captured.err
