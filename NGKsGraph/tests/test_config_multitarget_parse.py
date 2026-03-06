from pathlib import Path

from ngksgraph.config import load_config


def test_parse_multitarget_schema(tmp_path: Path):
    cfg_path = tmp_path / "ngksgraph.toml"
    cfg_path.write_text(
        "\n".join(
            [
                'out_dir = "build"',
                '',
                '[build]',
                'default_target = "app"',
                '',
                '[[targets]]',
                'name = "core"',
                'type = "staticlib"',
                'src_glob = ["src/core/**/*.cpp"]',
                'include_dirs = ["src/core"]',
                'links = []',
                '',
                '[[targets]]',
                'name = "app"',
                'type = "exe"',
                'src_glob = ["src/app/**/*.cpp"]',
                'include_dirs = ["src/core"]',
                'links = ["core"]',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)
    assert len(cfg.targets) == 2
    assert cfg.targets[0].name == "core"
    assert cfg.targets[1].name == "app"
    assert cfg.build_default_target == "app"


