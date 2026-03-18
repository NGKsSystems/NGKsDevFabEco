from pathlib import Path

from ngksgraph.config import load_config, save_config
import pytest


def test_config_load_and_save_roundtrip(tmp_path: Path):
    cfg_path = tmp_path / "ngksgraph.toml"
    cfg_path.write_text(
        "\n".join(
            [
                'name = "demo"',
                'out_dir = "build"',
                'target_type = "exe"',
                "cxx_std = 20",
                'src_glob = ["src/**/*.cpp"]',
                'include_dirs = ["z_inc", "a_inc"]',
                'defines = ["B", "A"]',
                "cflags = []",
                "ldflags = []",
                'libs = ["user32.lib", "gdi32"]',
                'lib_dirs = ["z_lib", "a_lib"]',
                'warnings = "default"',
                "",
                "[qt]",
                "enabled = false",
                'prefix = ""',
                "version = 6",
                "modules = []",
                "",
                "[ai]",
                "enabled = false",
                'plugin = ""',
                'mode = "advise"',
                "max_actions = 3",
                "log_tail_lines = 200",
                "redact_paths = true",
                "redact_env = true",
                "",
                "[ai.provider]",
                'model = ""',
                'endpoint = ""',
                'api_key_env = ""',
                "",
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)
    assert cfg.include_dirs == ["a_inc", "z_inc"]
    assert cfg.defines == ["A", "B"]
    assert cfg.libs == ["gdi32", "user32"]

    save_config(cfg_path, cfg)
    cfg2 = load_config(cfg_path)
    assert cfg2.libs == ["gdi32", "user32"]


def _write_qt_version_config(tmp_path: Path, qt_version_line: str) -> Path:
    cfg_path = tmp_path / "ngksgraph.toml"
    cfg_path.write_text(
        "\n".join(
            [
                'name = "app"',
                'out_dir = "build"',
                'target_type = "exe"',
                'src_glob = ["src/**/*.cpp"]',
                "",
                "[qt]",
                "enabled = false",
                'prefix = ""',
                qt_version_line,
                "modules = []",
            ]
        ),
        encoding="utf-8",
    )
    return cfg_path


def test_qt_version_accepts_integer(tmp_path: Path):
    cfg_path = _write_qt_version_config(tmp_path, "version = 6")
    cfg = load_config(cfg_path)
    assert cfg.qt.version == 6


def test_qt_version_accepts_numeric_string(tmp_path: Path):
    cfg_path = _write_qt_version_config(tmp_path, 'version = "6"')
    cfg = load_config(cfg_path)
    assert cfg.qt.version == 6


def test_qt_version_accepts_semantic_string_and_emits_note(tmp_path: Path, capsys):
    cfg_path = _write_qt_version_config(tmp_path, 'version = "6.9.9"')
    cfg = load_config(cfg_path)
    captured = capsys.readouterr()
    assert cfg.qt.version == 6
    assert "NGKSGRAPH_CONFIG_NORMALIZATION" in captured.err


def test_qt_version_invalid_string_fails_cleanly(tmp_path: Path):
    cfg_path = _write_qt_version_config(tmp_path, 'version = "banana"')
    with pytest.raises(ValueError, match="qt.version"):
        load_config(cfg_path)


def test_qt_version_invalid_type_fails_cleanly(tmp_path: Path):
    cfg_path = _write_qt_version_config(tmp_path, "version = []")
    with pytest.raises(ValueError, match="qt.version"):
        load_config(cfg_path)
