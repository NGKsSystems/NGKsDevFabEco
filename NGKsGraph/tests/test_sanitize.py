from ngksgraph.sanitize import sanitize_compile_commands, sanitize_graph_dict


def test_sanitize_graph_dict_redacts_paths():
    raw = {
        "repo_root": "C:/repo",
        "targets": {
            "app": {
                "out_dir": "C:/repo/build",
                "sources": ["C:/repo/src/main.cpp"],
            }
        },
    }

    clean = sanitize_graph_dict(raw, repo_root="C:/repo", out_dir="C:/repo/build")
    text = str(clean)
    assert "<REPO>" in text
    assert "<OUT>" in text
    assert "C:/repo" not in text


def test_sanitize_compile_commands_drive_redaction():
    entries = [
        {
            "directory": "C:/repo",
            "file": "C:/repo/src/main.cpp",
            "command": "cl /c C:/repo/src/main.cpp /FoC:/repo/build/obj/src/main.obj",
        }
    ]
    clean = sanitize_compile_commands(entries)
    blob = str(clean)
    assert "<DRIVE>" in blob
    assert "C:" not in blob
