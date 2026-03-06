import sys
from pathlib import Path

from ngksgraph.config import AIConfig
from ngksgraph.config import Config, TargetConfig
from ngksgraph.plugins.loader import load_plugin
from ngksgraph.repair import validate_ai_actions


def test_loader_falls_back_to_stub_when_missing_plugin():
    plugin = load_plugin(AIConfig(enabled=True, plugin="missing.module"))
    result = plugin.suggest({})
    assert result["actions"] == []


def test_loader_uses_custom_plugin(tmp_path: Path):
    plugin_file = tmp_path / "custom_plugin.py"
    plugin_file.write_text(
        "\n".join(
            [
                "class Plugin:",
                "    def suggest(self, context):",
                "        return {'actions': [{'op': 'config.add', 'field': 'libs', 'value': 'user32'}], 'notes': 'ok'}",
            ]
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        plugin = load_plugin(AIConfig(enabled=True, plugin="custom_plugin"))
        result = plugin.suggest({})
        assert result["actions"][0]["field"] == "libs"
    finally:
        sys.path = [p for p in sys.path if p != str(tmp_path)]


def test_validate_ai_actions_allowlist_and_limit():
    actions = [
        {"op": "config.add", "field": "libs", "value": "user32"},
        {"op": "config.add", "field": "bad_field", "value": "x"},
        {"op": "config.add", "field": "defines", "value": "X"},
    ]
    validated = validate_ai_actions(actions, max_actions=1)
    assert validated == [{"op": "config.add", "field": "libs", "value": "user32"}]


def test_validate_ai_actions_graph_ops():
    cfg = Config(
        targets=[
            TargetConfig(name="core", type="staticlib"),
            TargetConfig(name="app", type="exe", links=["core"]),
        ],
        build_default_target="app",
    )
    actions = [
        {"op": "target.add", "target": {"name": "util", "type": "staticlib", "src_glob": ["src/util/**/*.cpp"]}},
        {"op": "target.link_add", "target": "app", "value": "core"},
        {"op": "target.set_field", "target": "app", "field": "defines", "value": ["USE_X"]},
        {"op": "target.set_field", "target": "app", "field": "bad", "value": ["X"]},
    ]
    validated = validate_ai_actions(actions, max_actions=10, config=cfg)

    assert any(a["op"] == "target.add" for a in validated)
    assert any(a["op"] == "target.link_add" for a in validated)
    assert any(a["op"] == "target.set_field" and a["field"] == "defines" for a in validated)
    assert not any(a.get("field") == "bad" for a in validated)
