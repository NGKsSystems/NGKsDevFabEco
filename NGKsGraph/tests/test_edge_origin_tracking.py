from ngksgraph.config import Config, TargetConfig
from ngksgraph.graph import build_graph_from_project


def test_edge_origin_metadata_preserved():
    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=["core"]),
        ],
        build_default_target="app",
    )

    graph = build_graph_from_project(
        cfg,
        source_map={"core": ["src/core/core.cpp"], "app": ["src/app/main.cpp"]},
    )

    edge = graph.edges[0]
    assert edge.frm == "app"
    assert edge.to == "core"
    assert edge.origin["type"] == "config_field"
    assert edge.origin["field"] == "links"
    assert edge.origin["target_index"] == 1
