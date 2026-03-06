from pathlib import Path

from ngksgraph.build import load_graph_payload


CONFIG_TEXT = "\n".join(
    [
        'name = "demo"',
        'out_dir = "build"',
        'target_type = "exe"',
        'cxx_std = 20',
        'src_glob = ["src/**/*.cpp"]',
        'include_dirs = ["include"]',
        'defines = ["UNICODE", "_UNICODE"]',
        'cflags = []',
        'ldflags = []',
        'libs = []',
        'lib_dirs = []',
        'warnings = "default"',
        '',
        '[qt]',
        'enabled = false',
        'prefix = ""',
        'version = 6',
        'modules = []',
        '',
        '[ai]',
        'enabled = false',
        'plugin = ""',
        'mode = "advise"',
        'max_actions = 3',
        'log_tail_lines = 200',
        'redact_paths = true',
        'redact_env = true',
        '',
        '[ai.provider]',
        'model = ""',
        'endpoint = ""',
        'api_key_env = ""',
    ]
)


def test_graph_schema_basics(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    cfg_path = tmp_path / "ngksgraph.toml"
    cfg_path.write_text(CONFIG_TEXT, encoding="utf-8")
    payload, _ = load_graph_payload(tmp_path, cfg_path)

    assert payload["schema_version"] == 1
    assert "repo_root" in payload
    assert "generated_at" in payload
    assert "targets" in payload
    assert "edges" in payload
    assert "demo" in payload["targets"]
    assert payload["targets"]["demo"]["kind"] == "exe"
    assert payload["edges"] == []
