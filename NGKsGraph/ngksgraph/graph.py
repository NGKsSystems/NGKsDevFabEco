from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ngksgraph.config import Config
from ngksgraph.util import normalize_path


@dataclass
class Edge:
    frm: str
    to: str
    type: str
    origin: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "frm": self.frm,
            "to": self.to,
            "type": self.type,
        }
        if self.origin:
            data["origin"] = dict(self.origin)
        return data


@dataclass
class Target:
    name: str
    kind: str
    out_dir: str
    obj_dir: str
    bin_dir: str
    lib_dir: str
    sources: list[str]
    include_dirs: list[str]
    defines: list[str]
    cflags: list[str]
    libs: list[str]
    lib_dirs: list[str]
    ldflags: list[str]
    cxx_std: int
    links: list[str]
    toolchain: dict[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "out_dir": self.out_dir,
            "obj_dir": self.obj_dir,
            "bin_dir": self.bin_dir,
            "lib_dir": self.lib_dir,
            "sources": list(self.sources),
            "include_dirs": list(self.include_dirs),
            "defines": list(self.defines),
            "cflags": list(self.cflags),
            "libs": list(self.libs),
            "lib_dirs": list(self.lib_dirs),
            "ldflags": list(self.ldflags),
            "cxx_std": self.cxx_std,
            "links": list(self.links),
            "toolchain": dict(self.toolchain),
        }


@dataclass
class BuildGraph:
    targets: dict[str, Target] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def validate(self) -> None:
        names = set(self.targets.keys())
        if not names:
            raise ValueError("No targets configured.")

        for edge in self.edges:
            if edge.frm not in names or edge.to not in names:
                raise ValueError(f"Invalid edge reference: {edge.frm} -> {edge.to}")

        self.build_order()

    def build_order(self) -> list[str]:
        adjacency: dict[str, list[str]] = {name: [] for name in self.targets.keys()}
        indegree: dict[str, int] = {name: 0 for name in self.targets.keys()}

        for edge in self.edges:
            if edge.type != "links_to":
                continue
            adjacency[edge.to].append(edge.frm)
            indegree[edge.frm] += 1

        queue = sorted([name for name, d in indegree.items() if d == 0])
        out: list[str] = []
        while queue:
            name = queue.pop(0)
            out.append(name)
            for nxt in sorted(adjacency[name]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
            queue.sort()

        if len(out) != len(self.targets):
            raise ValueError("Cycle detected in target graph.")
        return out

    def link_closure(self, target_name: str) -> list[str]:
        if target_name not in self.targets:
            raise KeyError(target_name)

        visited: set[str] = set()

        def dfs(name: str) -> None:
            target = self.targets[name]
            for dep in target.links:
                if dep not in visited:
                    visited.add(dep)
                    dfs(dep)

        dfs(target_name)
        order = self.build_order()
        return [name for name in order if name in visited]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "targets": {
                name: self.targets[name].to_json_dict()
                for name in sorted(self.targets.keys())
            },
            "edges": [
                edge.to_json_dict()
                for edge in sorted(self.edges, key=lambda e: (e.frm, e.to, e.type, str(e.origin)))
            ],
            "build_order": self.build_order(),
        }


def build_graph_from_config(
    config: Config,
    sources: list[str],
    msvc_auto: bool = False,
) -> BuildGraph:
    # Backward-compatible helper used by existing tests: single target graph.
    source_map = {config.default_target_name(): list(sources)}
    return build_graph_from_project(config, source_map=source_map, msvc_auto=msvc_auto)


def build_graph_from_project(
    config: Config,
    source_map: dict[str, list[str]],
    msvc_auto: bool = False,
) -> BuildGraph:
    config.normalize()

    multi_target = len(config.targets) > 1
    out_dir = normalize_path(config.out_dir)

    targets: dict[str, Target] = {}
    edges: list[Edge] = []

    for target_cfg in config.targets:
        if multi_target:
            obj_dir = normalize_path(f"{out_dir}/obj/{target_cfg.name}")
        else:
            obj_dir = normalize_path(f"{out_dir}/obj")

        target = Target(
            name=target_cfg.name,
            kind=target_cfg.type,
            out_dir=out_dir,
            obj_dir=obj_dir,
            bin_dir=normalize_path(f"{out_dir}/bin"),
            lib_dir=normalize_path(f"{out_dir}/lib"),
            sources=sorted(set(normalize_path(v) for v in source_map.get(target_cfg.name, []))),
            include_dirs=list(target_cfg.include_dirs),
            defines=list(target_cfg.defines),
            cflags=list(target_cfg.cflags),
            libs=list(target_cfg.libs),
            lib_dirs=list(target_cfg.lib_dirs),
            ldflags=list(target_cfg.ldflags),
            cxx_std=target_cfg.cxx_std,
            links=list(target_cfg.links),
            toolchain={
                "compiler": "cl",
                "linker": "link",
                "arch": "amd64",
                "msvc_auto": bool(msvc_auto),
            },
        )
        targets[target.name] = target

    target_index_map = {target_cfg.name: idx for idx, target_cfg in enumerate(config.targets)}
    for target in targets.values():
        for dep in target.links:
            edges.append(
                Edge(
                    frm=target.name,
                    to=dep,
                    type="links_to",
                    origin={
                        "type": "config_field",
                        "field": "links",
                        "target_index": target_index_map.get(target.name, -1),
                    },
                )
            )

    graph = BuildGraph(targets=targets, edges=edges)
    graph.validate()

    if not config.build_default_target:
        exe_targets = [t.name for t in config.targets if t.type == "exe"]
        if not exe_targets and len(config.targets) > 0:
            # allow pure staticlib graph, but user must specify target explicitly for build
            pass

    return graph
