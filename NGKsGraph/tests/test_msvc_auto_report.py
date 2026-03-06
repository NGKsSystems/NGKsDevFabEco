import json

from ngksgraph.build import build_project
from ngksgraph.msvc import MSVCBootstrapResult


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


def test_msvc_auto_report_on_bootstrap_failure(monkeypatch, tmp_path):
    cfg = tmp_path / "ngksgraph.toml"
    cfg.write_text(CONFIG_TEXT, encoding="utf-8")

    monkeypatch.setattr("ngksgraph.build.has_cl_link", lambda env: False)
    monkeypatch.setattr(
        "ngksgraph.build.bootstrap_msvc",
        lambda: MSVCBootstrapResult(
            success=False,
            vswhere_path="C:/vswhere.exe",
            vs_install_path="C:/VS",
            vsdevcmd_path="C:/VS/Common7/Tools/VsDevCmd.bat",
            env={},
            error="boom",
        ),
    )

    rc = build_project(tmp_path, cfg, max_attempts=1, msvc_auto=True)
    assert rc == 0

    report = json.loads((tmp_path / "build" / "ngksgraph_last_report.json").read_text(encoding="utf-8"))
    assert report["msvc_auto"] is True
    assert report["ok"] is True


def test_msvc_auto_report_on_bootstrap_success(monkeypatch, tmp_path):
    cfg = tmp_path / "ngksgraph.toml"
    cfg.write_text(CONFIG_TEXT, encoding="utf-8")

    calls = {"count": 0}

    def fake_has_cl_link(env):
        calls["count"] += 1
        return calls["count"] > 1

    monkeypatch.setattr("ngksgraph.build.has_cl_link", fake_has_cl_link)
    monkeypatch.setattr(
        "ngksgraph.build.bootstrap_msvc",
        lambda: MSVCBootstrapResult(
            success=True,
            vswhere_path="C:/vswhere.exe",
            vs_install_path="C:/VS",
            vsdevcmd_path="C:/VS/Common7/Tools/VsDevCmd.bat",
            env={"Path": "C:/VC/bin", "INCLUDE": "C:/VC/include", "LIB": "C:/VC/lib", "VSCMD_VER": "18.3"},
            error=None,
        ),
    )
    monkeypatch.setattr(
        "ngksgraph.build.configure_project",
        lambda repo_root, config_path, msvc_auto=False, target=None: {
            "ok": True,
            "selected_target": "app",
            "source_map": {"app": ["src/main.cpp"]},
            "paths": {
                "compdb": tmp_path / "build" / "compile_commands.json",
                "graph": tmp_path / "build" / "ngksgraph_graph.json",
                "state": tmp_path / "build" / ".ngksgraph_state.json",
                "last_log": tmp_path / "build" / "ngksgraph_last_log.txt",
                "last_report": tmp_path / "build" / "ngksgraph_last_report.json",
                "build_report": tmp_path / "build" / "ngksgraph_build_report.json",
                "out_dir": tmp_path / "build",
            },
            "graph": type(
                "GraphStub",
                (),
                {
                    "targets": {
                        "app": type("TargetStub", (), {"kind": "exe", "bin_dir": "build/bin", "name": "app"})()
                    },
                    "edges": [],
                    "link_closure": staticmethod(lambda n: []),
                },
            )(),
            "graph_payload": {"targets": {"app": {}}, "edges": [], "build_order": ["app"]},
            "compdb": [],
            "snapshot_info": {"snapshot_path": None, "hashes": {}},
            "cache_hit": False,
            "cache_reason": "NO_CACHE",
        },
    )

    rc = build_project(tmp_path, cfg, max_attempts=1, msvc_auto=True)
    assert rc == 0

    report = json.loads((tmp_path / "build" / "ngksgraph_last_report.json").read_text(encoding="utf-8"))
    assert report["msvc_auto"] is True
    assert report["ok"] is True
    assert report["attempts"] == 1
