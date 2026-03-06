from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ngksgraph.hashutil import stable_json_dumps
from ngksgraph.util import normalize_path


def list_snapshots(snapshots_root: Path) -> list[Path]:
    if not snapshots_root.exists():
        return []
    items = [p for p in snapshots_root.iterdir() if p.is_dir()]
    return sorted(items, key=lambda p: p.name)


def resolve_snapshot(snapshots_root: Path, ref: str | None, fallback_index: int) -> Path | None:
    snapshots = list_snapshots(snapshots_root)
    if ref:
        candidate = Path(ref)
        if candidate.exists() and candidate.is_dir():
            return candidate
        for snap in snapshots:
            if snap.name == ref:
                return snap
        return None
    if len(snapshots) >= abs(fallback_index):
        return snapshots[fallback_index]
    return None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_diff(before: list[Any], after: list[Any]) -> dict[str, list[Any]]:
    b = list(before)
    a = list(after)
    return {
        "added": sorted([v for v in a if v not in b]),
        "removed": sorted([v for v in b if v not in a]),
    }


def _target_fields_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    list_fields = ["include_dirs", "defines", "cflags", "libs", "lib_dirs", "ldflags", "sources", "links"]
    scalar_fields = ["kind"]

    for field in list_fields:
        b = before.get(field, [])
        a = after.get(field, [])
        diff = _list_diff(b, a)
        if diff["added"] or diff["removed"]:
            key = "srcs" if field == "sources" else field
            fields[key] = diff

    for field in scalar_fields:
        if before.get(field) != after.get(field):
            fields[field] = {"from": before.get(field), "to": after.get(field)}

    return fields


def analyze_field_root_cause(diff_obj: dict[str, Any], target_name: str) -> dict[str, Any]:
    out = {
        "defines_added": [],
        "defines_removed": [],
        "include_dirs_added": [],
        "include_dirs_removed": [],
        "libs_added": [],
        "libs_removed": [],
        "links_added": [],
        "links_removed": [],
        "srcs_added": [],
        "srcs_removed": [],
        "type_changed": False,
    }

    changed = {item.get("name"): item.get("fields_changed", {}) for item in diff_obj.get("changed_targets", [])}
    fields = changed.get(target_name, {})
    if not fields:
        return out

    mapping = {
        "defines": ("defines_added", "defines_removed"),
        "include_dirs": ("include_dirs_added", "include_dirs_removed"),
        "libs": ("libs_added", "libs_removed"),
        "links": ("links_added", "links_removed"),
        "srcs": ("srcs_added", "srcs_removed"),
    }

    for key, (add_key, remove_key) in mapping.items():
        if key in fields:
            out[add_key] = list(fields[key].get("added", []))
            out[remove_key] = list(fields[key].get("removed", []))

    if "kind" in fields:
        out["type_changed"] = fields["kind"].get("from") != fields["kind"].get("to")

    return out


def _hash_changes(meta_a: dict[str, Any], meta_b: dict[str, Any], target_names: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    hash_keys = ["graph_hash", "compdb_hash", "config_hash"]
    for key in hash_keys:
        va = meta_a.get("hashes", {}).get(key)
        vb = meta_b.get("hashes", {}).get(key)
        if va != vb:
            out[key] = {"from": va, "to": vb}

    closures: dict[str, Any] = {}
    for name in sorted(target_names):
        va = meta_a.get("hashes", {}).get("closure_hashes", {}).get(name)
        vb = meta_b.get("hashes", {}).get("closure_hashes", {}).get(name)
        if va != vb:
            closures[name] = {"from": va, "to": vb}
    if closures:
        out["closure_hashes"] = closures
    return out


def _compdb_deltas(compdb_a: list[dict[str, Any]], compdb_b: list[dict[str, Any]], changed_targets: list[dict[str, Any]], max_items: int = 50) -> list[dict[str, Any]]:
    by_file_a = {normalize_path(v.get("file", "")): v for v in compdb_a}
    by_file_b = {normalize_path(v.get("file", "")): v for v in compdb_b}
    files = sorted(set(by_file_a.keys()) | set(by_file_b.keys()))

    why_tokens: list[str] = []
    for target in changed_targets:
        fields = target.get("fields_changed", {})
        for key in ["include_dirs", "defines", "cflags", "libs", "lib_dirs", "ldflags", "srcs", "links"]:
            if key in fields:
                why_tokens.append(key)
    why = ",".join(sorted(set(why_tokens))) if why_tokens else "unknown"

    out: list[dict[str, Any]] = []
    for file in files:
        ca = by_file_a.get(file, {}).get("command")
        cb = by_file_b.get(file, {}).get("command")
        if ca != cb:
            out.append(
                {
                    "file": file,
                    "before_command": ca,
                    "after_command": cb,
                    "why": why,
                }
            )
        if len(out) >= max_items:
            break
    return out


def _structural_diff_core(
    graph_a: dict[str, Any],
    graph_b: dict[str, Any],
    compdb_a: list[dict[str, Any]],
    compdb_b: list[dict[str, Any]],
    meta_a: dict[str, Any],
    meta_b: dict[str, Any],
    label_a: str,
    label_b: str,
) -> dict[str, Any]:

    targets_a = graph_a.get("targets", {})
    targets_b = graph_b.get("targets", {})

    names_a = set(targets_a.keys())
    names_b = set(targets_b.keys())

    added_targets = sorted(names_b - names_a)
    removed_targets = sorted(names_a - names_b)

    changed_targets: list[dict[str, Any]] = []
    for name in sorted(names_a & names_b):
        fields = _target_fields_diff(targets_a[name], targets_b[name])
        if fields:
            changed_targets.append({"name": name, "fields_changed": fields})

    def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
        frm = edge.get("frm", edge.get("from", ""))
        to = edge.get("to", "")
        etype = edge.get("type", "")
        origin = stable_json_dumps(edge.get("origin", {})) if isinstance(edge.get("origin", {}), dict) else ""
        return (str(frm), str(to), str(etype), origin)

    edges_a = sorted(graph_a.get("edges", []), key=_edge_key)
    edges_b = sorted(graph_b.get("edges", []), key=_edge_key)
    added_edges = [e for e in edges_b if e not in edges_a]
    removed_edges = [e for e in edges_a if e not in edges_b]

    hash_changes = _hash_changes(meta_a, meta_b, sorted(names_a | names_b))
    command_deltas = _compdb_deltas(compdb_a, compdb_b, changed_targets)

    return {
        "a": label_a,
        "b": label_b,
        "added_targets": added_targets,
        "removed_targets": removed_targets,
        "changed_targets": changed_targets,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
        "hash_changes": hash_changes,
        "compile_command_deltas": command_deltas,
    }


def structural_diff(snapshot_a: Path, snapshot_b: Path) -> dict[str, Any]:
    graph_a = _load_json(snapshot_a / "graph.json")
    graph_b = _load_json(snapshot_b / "graph.json")
    compdb_a = _load_json(snapshot_a / "compdb.json") if (snapshot_a / "compdb.json").exists() else []
    compdb_b = _load_json(snapshot_b / "compdb.json") if (snapshot_b / "compdb.json").exists() else []
    meta_a = _load_json(snapshot_a / "meta.json")
    meta_b = _load_json(snapshot_b / "meta.json")
    return _structural_diff_core(graph_a, graph_b, compdb_a, compdb_b, meta_a, meta_b, snapshot_a.name, snapshot_b.name)


def structural_diff_from_payloads(
    graph_a: dict[str, Any],
    graph_b: dict[str, Any],
    compdb_a: list[dict[str, Any]] | None = None,
    compdb_b: list[dict[str, Any]] | None = None,
    meta_a: dict[str, Any] | None = None,
    meta_b: dict[str, Any] | None = None,
    label_a: str = "a",
    label_b: str = "b",
) -> dict[str, Any]:
    return _structural_diff_core(
        graph_a=graph_a,
        graph_b=graph_b,
        compdb_a=compdb_a or [],
        compdb_b=compdb_b or [],
        meta_a=meta_a or {},
        meta_b=meta_b or {},
        label_a=label_a,
        label_b=label_b,
    )


def summarize_diff(diff_obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "added_targets": diff_obj.get("added_targets", []),
        "removed_targets": diff_obj.get("removed_targets", []),
        "changed_targets": [v.get("name") for v in diff_obj.get("changed_targets", [])],
        "added_edges_count": len(diff_obj.get("added_edges", [])),
        "removed_edges_count": len(diff_obj.get("removed_edges", [])),
        "command_deltas_count": len(diff_obj.get("compile_command_deltas", [])),
    }


def diff_to_text(diff_obj: dict[str, Any]) -> str:
    lines = [
        f"Snapshots: {diff_obj.get('a')} -> {diff_obj.get('b')}",
        f"Added targets: {', '.join(diff_obj.get('added_targets', [])) or '<none>'}",
        f"Removed targets: {', '.join(diff_obj.get('removed_targets', [])) or '<none>'}",
        f"Changed targets: {', '.join(v.get('name','') for v in diff_obj.get('changed_targets', [])) or '<none>'}",
        f"Added edges: {len(diff_obj.get('added_edges', []))}",
        f"Removed edges: {len(diff_obj.get('removed_edges', []))}",
        f"Compile command deltas: {len(diff_obj.get('compile_command_deltas', []))}",
    ]
    if diff_obj.get("hash_changes"):
        lines.append("Hash changes:")
        for key in sorted(diff_obj["hash_changes"].keys()):
            if key == "closure_hashes":
                lines.append("  closure_hashes changed")
            else:
                lines.append(f"  {key}")
    return "\n".join(lines)


def stable_diff_json(diff_obj: dict[str, Any]) -> str:
    return stable_json_dumps(diff_obj)
