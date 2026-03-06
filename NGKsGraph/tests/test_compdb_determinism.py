from ngksgraph.compdb import generate_compile_commands
from ngksgraph.config import Config
from ngksgraph.graph import build_graph_from_config


def test_compile_commands_deterministic():
    cfg = Config(
        name="app",
        include_dirs=["z/inc", "a/inc"],
        defines=["Z", "A"],
        cflags=["/permissive-"],
    )
    srcs = ["src/z.cpp", "src/a.cpp"]
    graph = build_graph_from_config(cfg, srcs)

    out1 = generate_compile_commands(graph, cfg, "C:/repo")
    out2 = generate_compile_commands(graph, cfg, "C:/repo")

    assert out1 == out2
    assert out1[0]["file"].endswith("src\\a.cpp") or out1[0]["file"].endswith("src/a.cpp")
    assert "/showIncludes" in out1[0]["command"]
