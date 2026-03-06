from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .hashing import normalize_path


@dataclass(slots=True)
class PlanNode:
    id: str
    desc: str = ""
    cwd: str | None = None
    cmd: str | list[str] = ""
    deps: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class BuildPlan:
    plan_path: Path
    base_dir: Path
    nodes: list[PlanNode]


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [str(x) for x in value]


def _legacy_node(raw: dict) -> PlanNode:
    return PlanNode(
        id=str(raw["id"]),
        desc=str(raw.get("desc", "")),
        cwd=raw.get("cwd"),
        cmd=raw["cmd"],
        deps=_as_str_list(raw.get("deps", [])),
        inputs=_as_str_list(raw.get("inputs", [])),
        outputs=_as_str_list(raw.get("outputs", [])),
        env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
    )


def _graph_action_node(raw: dict) -> PlanNode:
    argv = raw.get("argv", [])
    if isinstance(argv, list):
        cmd: str | list[str] = [str(x) for x in argv]
    else:
        cmd = str(argv)
    return PlanNode(
        id=str(raw["id"]),
        desc=str(raw.get("desc", "")),
        cwd=raw.get("cwd"),
        cmd=cmd,
        deps=_as_str_list(raw.get("deps", [])),
        inputs=_as_str_list(raw.get("inputs", [])),
        outputs=_as_str_list(raw.get("outputs", [])),
        env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
    )


def load_plan(plan_path: str | Path) -> BuildPlan:
    plan_file = Path(plan_path).resolve()
    with plan_file.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload.get("actions"), list):
        raw_nodes = payload["actions"]
        node_factory = _graph_action_node
    elif isinstance(payload.get("nodes"), list):
        raw_nodes = payload["nodes"]
        node_factory = _legacy_node
    else:
        raise ValueError("plan json must include either an 'actions' array or a 'nodes' array")

    base_dir_raw = payload.get("base_dir")
    if base_dir_raw:
        base_dir = normalize_path(base_dir_raw, plan_file.parent)
    else:
        base_dir = plan_file.parent.resolve()

    nodes: list[PlanNode] = []
    seen_ids: set[str] = set()
    for raw in raw_nodes:
        node = node_factory(raw)
        if node.id in seen_ids:
            raise ValueError(f"duplicate node id: {node.id}")
        seen_ids.add(node.id)
        nodes.append(node)

    id_set = {n.id for n in nodes}
    for node in nodes:
        for dep in node.deps:
            if dep not in id_set:
                raise ValueError(f"node '{node.id}' depends on unknown node '{dep}'")

    return BuildPlan(plan_path=plan_file, base_dir=base_dir, nodes=nodes)
