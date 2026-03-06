import pytest

from ngksgraph.config import Config, TargetConfig
from ngksgraph.graph import build_graph_from_project


def test_graph_cycle_detection_fails():
    cfg = Config(
        targets=[
            TargetConfig(name="a", type="staticlib", links=["b"]),
            TargetConfig(name="b", type="staticlib", links=["a"]),
        ]
    )

    with pytest.raises(ValueError, match="Cycle detected"):
        build_graph_from_project(cfg, source_map={"a": [], "b": []})
