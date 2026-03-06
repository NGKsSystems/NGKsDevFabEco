from __future__ import annotations

import heapq
from dataclasses import dataclass

from .plan import PlanNode


@dataclass(slots=True)
class GraphState:
    nodes_by_id: dict[str, PlanNode]
    indegree: dict[str, int]
    children: dict[str, list[str]]


def build_graph(nodes: list[PlanNode]) -> GraphState:
    nodes_by_id = {n.id: n for n in nodes}
    indegree = {n.id: 0 for n in nodes}
    children = {n.id: [] for n in nodes}
    for node in nodes:
        for dep in node.deps:
            indegree[node.id] += 1
            children[dep].append(node.id)
    for key in children:
        children[key].sort()
    return GraphState(nodes_by_id=nodes_by_id, indegree=indegree, children=children)


def seed_ready(indegree: dict[str, int]) -> list[str]:
    ready: list[str] = []
    for node_id in sorted(indegree):
        if indegree[node_id] == 0:
            heapq.heappush(ready, node_id)
    return ready


def release_children(finished_node_id: str, indegree: dict[str, int], children: dict[str, list[str]]) -> list[str]:
    newly_ready: list[str] = []
    for child in children[finished_node_id]:
        indegree[child] -= 1
        if indegree[child] == 0:
            newly_ready.append(child)
    return sorted(newly_ready)
