from ngksgraph.compdb import generate_compile_commands
from ngksgraph.config import Config, TargetConfig
from ngksgraph.graph import build_graph_from_project


def test_compdb_multitarget_entries():
    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=["core"]),
        ],
    )
    source_map = {
        "core": ["src/core/core.cpp"],
        "app": ["src/app/main.cpp"],
    }

    graph = build_graph_from_project(cfg, source_map=source_map)
    compdb = generate_compile_commands(graph, cfg, "C:/repo")

    assert len(compdb) == 2
    commands = "\n".join(v["command"] for v in compdb)
    assert "/Fobuild/obj/core/src/core/core.obj" in commands
    assert "/Fobuild/obj/app/src/app/main.obj" in commands
