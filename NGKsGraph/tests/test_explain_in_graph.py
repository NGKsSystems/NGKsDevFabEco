from pathlib import Path

from ngksgraph.build import explain_source


CONFIG_TEXT = "\n".join(
    [
        'name = "app"',
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


def test_explain_source_in_graph(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    cfg = tmp_path / "ngksgraph.toml"
    cfg.write_text(CONFIG_TEXT, encoding="utf-8")

    result = explain_source(tmp_path, cfg, "src/main.cpp")

    assert result["status"] == "IN_GRAPH"
    assert result["target"] == "app"
    assert "/showIncludes" in result["compile_command"]
    assert "build/obj/src/main.obj" in result["object_path"].replace("\\", "/")
