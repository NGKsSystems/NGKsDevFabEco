from __future__ import annotations

from pathlib import Path
from typing import Any

from ngksgraph.config import Config
from ngksgraph.graph import BuildGraph
from ngksgraph.hashutil import stable_json_dumps, sha256_text
from ngksgraph.util import normalize_path


def _obj_path(obj_dir: str, src: str) -> str:
    src_path = Path(src)
    return normalize_path(Path(obj_dir) / f"{src_path.with_suffix('')}.obj")


def _target_output(kind: str, lib_dir: str, bin_dir: str, name: str) -> str:
    if kind == "staticlib":
        return normalize_path(Path(lib_dir) / f"{name}.lib")
    return normalize_path(Path(bin_dir) / f"{name}.exe")


def _canonical_profile_path(path: str, out_dir: str) -> str:
    norm = normalize_path(path)
    out = normalize_path(out_dir).rstrip("/")
    marker = f"{out}/"
    if marker in norm:
        return norm.replace(marker, "$OUT/")
    return norm


def _to_out_relative(path: str, out_dir: str) -> str:
    norm = normalize_path(path)
    out = normalize_path(out_dir).rstrip("/")
    marker = f"{out}/"
    if norm.startswith(marker):
        return norm[len(marker) :]
    return norm


def expected_compile_units(graph: BuildGraph, config: Config | None = None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        out[target_name] = {normalize_path(src) for src in target.sources if Path(src).suffix.lower() == ".cpp"}
    return out


def expected_objects(graph: BuildGraph, config: Config | None = None) -> dict[str, set[str]]:
    units = expected_compile_units(graph, config)
    out: dict[str, set[str]] = {}
    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        out[target_name] = {normalize_path(_obj_path(target.obj_dir, src)) for src in sorted(units[target_name])}
    return out


def expected_link_inputs(graph: BuildGraph, config: Config | None = None) -> dict[str, list[str]]:
    expected_objs = expected_objects(graph, config)
    target_outputs: dict[str, str] = {
        name: _target_output(t.kind, t.lib_dir, t.bin_dir, name) for name, t in graph.targets.items()
    }

    out: dict[str, list[str]] = {}
    for target_name in graph.build_order():
        target = graph.targets[target_name]
        own_objs = sorted(expected_objs[target_name])
        dep_libs = [target_outputs[name] for name in graph.link_closure(target_name) if graph.targets[name].kind == "staticlib"]
        explicit_libs = [f"{lib}.lib" for lib in list(target.libs)]
        out[target_name] = own_objs + dep_libs + explicit_libs
    return out


def compute_structural_graph_hash(graph: BuildGraph) -> str:
    payload: dict[str, Any] = {
        "targets": {},
        "edges": sorted(
            [
                {
                    "frm": edge.frm,
                    "to": edge.to,
                    "type": edge.type,
                }
                for edge in graph.edges
            ],
            key=lambda e: (e["frm"], e["to"], e["type"]),
        ),
    }

    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        payload["targets"][target_name] = {
            "kind": target.kind,
            "links": sorted(set(target.links)),
            "sources": sorted(_canonical_profile_path(src, target.out_dir) for src in target.sources),
            "generator_inclusion": {
                "moc": any("build/qt/moc_" in normalize_path(src) for src in target.sources),
                "qrc": any("build/qt/qrc_" in normalize_path(src) for src in target.sources),
            },
        }

    return sha256_text(stable_json_dumps(payload))


def validate_profile_parity(debug_graph: BuildGraph, release_graph: BuildGraph) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []

    debug_hash = compute_structural_graph_hash(debug_graph)
    release_hash = compute_structural_graph_hash(release_graph)
    if debug_hash != release_hash:
        violations.append(
            {
                "code": "STRUCTURAL_DRIFT",
                "detail": "structural graph hash differs across profiles",
                "hint": "profile changes must not alter target graph structure or source membership",
            }
        )

    def _deps(graph: BuildGraph) -> dict[str, list[str]]:
        return {name: sorted(set(graph.targets[name].links)) for name in sorted(graph.targets.keys())}

    if _deps(debug_graph) != _deps(release_graph):
        violations.append(
            {
                "code": "DEPENDENCY_DRIFT",
                "detail": "target dependency graph differs across profiles",
                "hint": "profiles may alter flags but not target dependency closure",
            }
        )

    def _canon_units(graph: BuildGraph) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for name, units in expected_compile_units(graph).items():
            target = graph.targets[name]
            out[name] = {_canonical_profile_path(src, target.out_dir) for src in units}
        return out

    if _canon_units(debug_graph) != _canon_units(release_graph):
        violations.append(
            {
                "code": "UNIT_DRIFT",
                "detail": "compile unit membership differs across profiles",
                "hint": "profiles must not change which translation units are part of each target",
            }
        )

    def _canon_links(graph: BuildGraph) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        raw = expected_link_inputs(graph)
        for name, items in raw.items():
            target = graph.targets[name]
            out[name] = [_canonical_profile_path(v, target.out_dir) for v in items]
        return out

    if _canon_links(debug_graph) != _canon_links(release_graph):
        violations.append(
            {
                "code": "LINK_PLAN_DRIFT",
                "detail": "link input plan differs across profiles",
                "hint": "profiles may alter flags but not object/lib dependency input ordering",
            }
        )

    return violations


def validate_graph_integrity(graph: BuildGraph, config: Config, build_outputs_dir: Path) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []

    compile_units = expected_compile_units(graph, config)
    objects = expected_objects(graph, config)
    link_inputs = expected_link_inputs(graph, config)

    ownership: dict[str, list[str]] = {}
    for target, objs in objects.items():
        for obj in objs:
            ownership.setdefault(obj, []).append(target)

    for obj, owners in sorted(ownership.items()):
        uniq = sorted(set(owners))
        if len(uniq) > 1:
            violations.append(
                {
                    "code": "AMBIGUOUS_OBJECT",
                    "detail": f"object has multiple owners: {obj} -> {', '.join(uniq)}",
                    "target": ",".join(uniq),
                    "path": obj,
                    "hint": "ensure each translation unit maps to exactly one target",
                }
            )

    qt_generated = sorted(
        {
            src
            for targets in compile_units.values()
            for src in targets
            if "build/qt/moc_" in normalize_path(src) or "build/qt/qrc_" in normalize_path(src)
        }
    )
    for src in qt_generated:
        if not any(src in units for units in compile_units.values()):
            violations.append(
                {
                    "code": "MISSING_GENERATED_TU",
                    "detail": f"generated translation unit missing from graph compile units: {src}",
                    "path": src,
                    "hint": "ensure generated moc/qrc outputs are injected into target sources",
                }
            )

    obj_root = build_outputs_dir / "obj"
    actual_objs = {
        normalize_path(v.relative_to(build_outputs_dir))
        for v in obj_root.rglob("*.obj")
        if v.is_file()
    } if obj_root.exists() else set()

    planned_obj_meta: dict[str, dict[str, str]] = {}
    for target_name, values in objects.items():
        out_dir = graph.targets[target_name].out_dir
        for obj in values:
            planned_obj_meta[_to_out_relative(obj, out_dir)] = {
                "target": target_name,
                "path": obj,
            }

    planned_objs_rel = set(planned_obj_meta.keys())
    for orphan in sorted(actual_objs - planned_objs_rel):
        violations.append(
            {
                "code": "ORPHAN_OBJECT",
                "detail": f"object exists on disk but not in graph plan: {orphan}",
                "path": orphan,
                "hint": "clean stale outputs or ensure graph includes all compiled units",
            }
        )

    if actual_objs:
        for missing_rel in sorted(planned_objs_rel - actual_objs):
            meta = planned_obj_meta.get(missing_rel, {"target": "", "path": missing_rel})
            violations.append(
                {
                    "code": "MISSING_OBJECT",
                    "detail": f"planned object missing on disk: {meta['path']}",
                    "target": meta["target"],
                    "path": meta["path"],
                    "hint": "run build or verify object path generation",
                }
            )

    for target_name in sorted(graph.targets.keys()):
        target = graph.targets[target_name]
        if target.kind != "exe":
            continue
        expected = [_to_out_relative(v, target.out_dir) for v in link_inputs[target_name]]
        if not expected:
            violations.append(
                {
                    "code": "MISSING_LINK_INPUT",
                    "detail": f"expected link input plan is empty for target {target_name}",
                    "target": target_name,
                    "path": target_name,
                    "hint": "ensure target links/libs and closure are reflected in graph-derived link plan",
                }
            )

    return violations
