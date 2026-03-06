from pathlib import Path

from ngksgraph.config import load_config, save_config


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
