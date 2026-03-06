from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
import zipfile

from ngksgraph.build import configure_project
from ngksgraph.capsule import closure_hashes_from_graph, verify_capsule
from ngksgraph.config import Config, load_config
from ngksgraph.diff import analyze_field_root_cause, list_snapshots, resolve_snapshot, structural_diff, structural_diff_from_payloads
from ngksgraph.util import normalize_path


def _edge_attr(edge: dict[str, Any], key: str, default: str = "") -> str:
    if key == "frm":
        return str(edge.get("frm", edge.get("from", default)))
    return str(edge.get(key, default))


def _snapshot_root(out_dir: Path) -> Path:
    return out_dir / ".ngksgraph_snapshots"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_snapshot_payload(snapshot_dir: Path) -> dict[str, Any]:
    return {
        "graph": _load_json(snapshot_dir / "graph.json"),
        "compdb": _load_json(snapshot_dir / "compdb.json") if (snapshot_dir / "compdb.json").exists() else [],
        "meta": _load_json(snapshot_dir / "meta.json") if (snapshot_dir / "meta.json").exists() else {},
        "snapshot_id": snapshot_dir.name,
    }


def _load_capsule_payload(capsule_path: Path) -> dict[str, Any]:
    verified = verify_capsule(capsule_path)
    if not verified.get("ok"):
        raise ValueError(f"Capsule verification failed: {verified.get('mismatches', [])}")

    with zipfile.ZipFile(capsule_path, mode="r") as zf:
        graph = json.loads(zf.read("graph.json").decode("utf-8"))
        compdb = json.loads(zf.read("compdb.json").decode("utf-8"))
        hashes = json.loads(zf.read("hashes.json").decode("utf-8"))
        snapshot_ref = json.loads(zf.read("snapshot_ref.json").decode("utf-8")) if "snapshot_ref.json" in zf.namelist() else None

    return {
        "graph": graph,
        "compdb": compdb,
        "meta": {"hashes": hashes},
        "snapshot_id": "capsule",
        "snapshot_ref": snapshot_ref,
    }


def _all_paths(graph: dict[str, Any], start: str, end: str, limit: int = 32) -> list[list[str]]:
    targets = graph.get("targets", {})
    out: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        if len(out) >= limit:
            return
        if node == end:
            out.append(path[:])
            return
        for dep in targets.get(node, {}).get("links", []):
            if dep in path:
                continue
            dfs(dep, path + [dep])

    dfs(start, [start])
    return out


def _first_seen_snapshot_for_edge(snapshots_root: Path, frm: str, to: str) -> str | None:
    for snapshot in list_snapshots(snapshots_root):
        graph_file = snapshot / "graph.json"
        if not graph_file.exists():
            continue
        try:
            graph = _load_json(graph_file)
        except Exception:
            continue
        for edge in graph.get("edges", []):
            if _edge_attr(edge, "frm") == frm and _edge_attr(edge, "to") == to and _edge_attr(edge, "type") == "links_to":
                return snapshot.name
    return None


def _target_index(config: Config, target_name: str) -> int:
    for idx, target in enumerate(config.targets):
        if target.name == target_name:
            return idx
    return -1


def _current_payload(repo_root: Path, config_path: Path, target: str | None = None) -> tuple[dict[str, Any], Config, str, Path]:
    config = load_config(config_path)
    config.normalize()
    selected_target = target or config.default_target_name()
    out_dir = repo_root / config.out_dir

    snapshots = list_snapshots(_snapshot_root(out_dir))
    if snapshots:
        latest = _load_snapshot_payload(snapshots[-1])
        return latest, config, selected_target, out_dir

    configured = configure_project(repo_root, config_path, target=selected_target)
    payload = {
        "graph": configured["graph_payload"],
        "compdb": configured["compdb"],
        "meta": {"hashes": configured.get("snapshot_info", {}).get("hashes", {})},
        "snapshot_id": configured.get("snapshot_info", {}).get("snapshot_path") or "live",
    }
    return payload, config, selected_target, configured["paths"]["out_dir"]


def _load_baseline_pair(out_dir: Path, from_snapshot: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, tuple[str | None, str | None]]:
    root = _snapshot_root(out_dir)
    if from_snapshot:
        current_dir = resolve_snapshot(root, from_snapshot, -1)
        if current_dir is None:
            return None, None, (None, None)
        snapshots = list_snapshots(root)
        idx = snapshots.index(current_dir)
        previous_dir = snapshots[idx - 1] if idx > 0 else None
        current = _load_snapshot_payload(current_dir)
        previous = _load_snapshot_payload(previous_dir) if previous_dir else None
        return previous, current, (previous_dir.name if previous_dir else None, current_dir.name)

    snapshots = list_snapshots(root)
    if len(snapshots) < 2:
        return None, None, (None, None)
    previous = _load_snapshot_payload(snapshots[-2])
    current = _load_snapshot_payload(snapshots[-1])
    return previous, current, (snapshots[-2].name, snapshots[-1].name)


def _find_edge(graph: dict[str, Any], frm: str, to: str) -> dict[str, Any] | None:
    for edge in graph.get("edges", []):
        if _edge_attr(edge, "frm") == frm and _edge_attr(edge, "to") == to and _edge_attr(edge, "type") == "links_to":
            return edge
    return None


def _build_target_source_map(config: Config, repo_root: Path) -> dict[str, list[str]]:
    source_map: dict[str, list[str]] = {target.name: [] for target in config.targets}
    for target in config.targets:
        for src in target.src_glob:
            for path in sorted(repo_root.glob(src)):
                if path.is_file() and path.suffix.lower() in {".cpp", ".cc", ".cxx", ".c"}:
                    source_map[target.name].append(normalize_path(path.resolve().relative_to(repo_root.resolve())))
    return source_map


def _extract_missing_symbols(log_text: str) -> list[str]:
    symbols: list[str] = []
    patterns = [
        re.compile(r"unresolved external symbol\s+(.+?)\s+referenced", re.IGNORECASE),
        re.compile(r"undefined reference to\s+['\"]?(.+?)['\"]?$", re.IGNORECASE),
    ]
    for line in log_text.splitlines():
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            raw = match.group(1).strip()
            token_match = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", raw)
            if token_match:
                symbols.append(token_match[-1])
            else:
                symbols.append(raw)
    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def symbol_forensics(log_text: str, repo_root: Path, config: Config, target_name: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
    symbols = _extract_missing_symbols(log_text)
    if not symbols:
        return []

    source_map = _build_target_source_map(config, repo_root)
    closure: set[str] = set()
    visited: set[str] = set()

    def walk(name: str) -> None:
        for dep in graph.get("targets", {}).get(name, {}).get("links", []):
            if dep in visited:
                continue
            visited.add(dep)
            closure.add(dep)
            walk(dep)

    walk(target_name)
    out: list[dict[str, Any]] = []

    for symbol in symbols:
        likely_target = None
        likely_source = None
        for owner, sources in source_map.items():
            for src in sources:
                file_path = repo_root / src
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if symbol in text:
                    likely_target = owner
                    likely_source = src
                    break
            if likely_target:
                break

        suggestion = None
        if likely_target and likely_target != target_name and likely_target not in closure:
            suggestion = {
                "missing_link_edge": f"{target_name} -> {likely_target}",
                "reason": "symbol appears in non-closure target",
            }

        out.append(
            {
                "symbol": symbol,
                "likely_target": likely_target,
                "likely_source": likely_source,
                "current_closure": sorted(closure),
                "suggestion": suggestion,
            }
        )

    return out


def why_target(
    repo_root: Path,
    config_path: Path,
    target_name: str,
    from_snapshot: str | None = None,
    from_capsule: Path | None = None,
) -> dict[str, Any]:
    current, config, selected_target, out_dir = _current_payload(repo_root, config_path, target=target_name)
    selected = target_name or selected_target

    if from_capsule is not None:
        current = _load_capsule_payload(from_capsule)

    graph = current["graph"]
    targets = graph.get("targets", {})
    if selected not in targets:
        raise KeyError(selected)

    closure_hashes = current.get("meta", {}).get("hashes", {}).get("closure_hashes", {})
    if not closure_hashes:
        closure_hashes = closure_hashes_from_graph(graph)

    direct_links = list(targets[selected].get("links", []))
    closure = []
    visited: set[str] = set()

    def dfs(name: str) -> None:
        for dep in targets.get(name, {}).get("links", []):
            if dep not in visited:
                visited.add(dep)
                dfs(dep)

    dfs(selected)
    for name in graph.get("build_order", sorted(targets.keys())):
        if name in visited:
            closure.append(name)

    snapshots_root = _snapshot_root(out_dir)
    edge_attribution: list[dict[str, Any]] = []
    target_idx = _target_index(config, selected)
    for dep in direct_links:
        edge = _find_edge(graph, selected, dep)
        origin = (edge or {}).get(
            "origin",
            {
                "type": "config_field",
                "field": "links",
                "target_index": target_idx,
            },
        )
        edge_attribution.append(
            {
                "link": dep,
                "origin": origin,
                "declared_in": "ngksgraph.toml",
                "snapshot_first_seen": _first_seen_snapshot_for_edge(snapshots_root, selected, dep),
            }
        )

    closure_attribution: list[dict[str, Any]] = []
    for dep in closure:
        paths = _all_paths(graph, selected, dep)
        if not paths:
            continue
        closure_attribution.append(
            {
                "dependency": dep,
                "paths": [" -> ".join(p) for p in paths],
                "direct_link": dep in direct_links,
                "indirect_link": dep not in direct_links,
                "duplicate_link": len(paths) > 1,
            }
        )

    previous, baseline_current, snapshot_ids = _load_baseline_pair(out_dir, from_snapshot=from_snapshot)
    rebuild = {
        "snapshot_previous": snapshot_ids[0],
        "snapshot_current": snapshot_ids[1],
        "triggered": False,
        "reasons": [],
        "field_root_cause": {},
        "compile_command_deltas": [],
        "plan_rule_change": False,
    }

    if previous and baseline_current:
        diff_obj = structural_diff(snapshots_root / snapshot_ids[0], snapshots_root / snapshot_ids[1])
        field_rc = analyze_field_root_cause(diff_obj, selected)
        hash_changes = diff_obj.get("hash_changes", {})
        closure_delta = selected in (hash_changes.get("closure_hashes", {}) or {})
        compdb_delta = "compdb_hash" in hash_changes
        plan_delta = "graph_hash" in hash_changes

        reasons: list[str] = []
        if closure_delta:
            reasons.append("closure_hash changed")
        if compdb_delta:
            reasons.append("compile_commands changed")
        if plan_delta:
            reasons.append("graph_hash changed")

        for key in ["defines_added", "include_dirs_added", "libs_added", "links_added", "srcs_added"]:
            values = field_rc.get(key, [])
            if values:
                reasons.append(f"{key.replace('_', ' ')}: {', '.join(values)}")

        rebuild = {
            "snapshot_previous": snapshot_ids[0],
            "snapshot_current": snapshot_ids[1],
            "triggered": bool(reasons),
            "reasons": reasons,
            "field_root_cause": field_rc,
            "compile_command_deltas": [item for item in diff_obj.get("compile_command_deltas", []) if selected in item.get("why", "") or item.get("why") == "unknown"],
            "plan_rule_change": plan_delta,
        }

    log_text = ""
    last_log = out_dir / "ngksgraph_last_log.txt"
    if last_log.exists():
        log_text = last_log.read_text(encoding="utf-8", errors="ignore")

    symbols = symbol_forensics(log_text, repo_root, config, selected, graph)

    return {
        "target": selected,
        "target_overview": {
            "type": targets[selected].get("kind"),
            "direct_links": direct_links,
            "full_closure": closure,
            "closure_hash": closure_hashes.get(selected),
        },
        "edge_attribution": edge_attribution,
        "closure_attribution": closure_attribution,
        "rebuild_reasoning": rebuild,
        "symbol_forensics": symbols,
        "from_capsule": normalize_path(from_capsule.resolve()) if from_capsule else None,
    }


def rebuild_cause_target(
    repo_root: Path,
    config_path: Path,
    target_name: str,
    from_snapshot: str | None = None,
    from_capsule: Path | None = None,
) -> dict[str, Any]:
    current, _, selected_target, out_dir = _current_payload(repo_root, config_path, target=target_name)
    selected = target_name or selected_target

    snapshot_root = _snapshot_root(out_dir)
    baseline_previous_payload: dict[str, Any] | None = None
    previous_id: str | None = None
    current_id: str | None = None

    if from_capsule is not None:
        current = _load_capsule_payload(from_capsule)
        snaps = list_snapshots(snapshot_root)
        if snaps:
            baseline_previous_payload = _load_snapshot_payload(snaps[-1])
            previous_id = snaps[-1].name
        current_id = f"capsule:{from_capsule.name}"
    else:
        previous, _, snapshot_ids = _load_baseline_pair(out_dir, from_snapshot=from_snapshot)
        baseline_previous_payload = previous
        previous_id = snapshot_ids[0]
        current_id = snapshot_ids[1]

    if not baseline_previous_payload or not previous_id or not current_id:
        return {
            "target": selected,
            "baseline": {"previous": None, "current": None},
            "message": "no baseline available",
            "structural_change": {},
            "command_change": {},
            "no_change": True,
        }

    if from_capsule is not None:
        diff_obj = structural_diff_from_payloads(
            graph_a=baseline_previous_payload.get("graph", {}),
            graph_b=current.get("graph", {}),
            compdb_a=baseline_previous_payload.get("compdb", []),
            compdb_b=current.get("compdb", []),
            meta_a={"hashes": baseline_previous_payload.get("meta", {}).get("hashes", {})},
            meta_b={"hashes": current.get("meta", {}).get("hashes", {})},
            label_a=previous_id,
            label_b=current_id,
        )

        hash_changes = diff_obj.get("hash_changes", {})
        if not hash_changes:
            prev_hashes = baseline_previous_payload.get("meta", {}).get("hashes", {})
            curr_hashes = current.get("meta", {}).get("hashes", {})
            hash_changes = {}
            for key in ["compdb_hash", "graph_hash", "config_hash"]:
                if prev_hashes.get(key) != curr_hashes.get(key):
                    hash_changes[key] = {"from": prev_hashes.get(key), "to": curr_hashes.get(key)}
            prev_closure = prev_hashes.get("closure_hashes", {}) or {}
            curr_closure = curr_hashes.get("closure_hashes", {}) or {}
            closure_delta: dict[str, Any] = {}
            for name in sorted(set(prev_closure.keys()) | set(curr_closure.keys())):
                if prev_closure.get(name) != curr_closure.get(name):
                    closure_delta[name] = {"from": prev_closure.get(name), "to": curr_closure.get(name)}
            if closure_delta:
                hash_changes["closure_hashes"] = closure_delta
            diff_obj["hash_changes"] = hash_changes
    else:
        diff_obj = structural_diff(snapshot_root / previous_id, snapshot_root / current_id)
    field_rc = analyze_field_root_cause(diff_obj, selected)
    hash_changes = diff_obj.get("hash_changes", {})
    closure_delta = selected in (hash_changes.get("closure_hashes", {}) or {})
    compdb_delta = "compdb_hash" in hash_changes
    plan_delta = "graph_hash" in hash_changes

    command_deltas = diff_obj.get("compile_command_deltas", [])
    changed_files = [item.get("file") for item in command_deltas]
    reason_tokens: set[str] = set()
    for item in command_deltas:
        reason_tokens.update([v for v in str(item.get("why", "")).split(",") if v])

    token_map = {
        "defines": "targets[].defines",
        "include_dirs": "targets[].include_dirs",
        "libs": "targets[].libs",
        "lib_dirs": "targets[].lib_dirs",
        "ldflags": "targets[].ldflags",
        "cflags": "targets[].cflags",
        "links": "targets[].links",
        "srcs": "targets[].src_glob",
    }
    token_attribution = {token: token_map.get(token, "unknown") for token in sorted(reason_tokens)}

    structural = {
        "closure_hash_changed": closure_delta,
        "field_root_cause": field_rc,
        "hash_changes": hash_changes,
    }
    command = {
        "compdb_hash_changed": compdb_delta,
        "graph_hash_changed": plan_delta,
        "changed_sources": changed_files,
        "command_delta_fields": sorted(reason_tokens),
        "field_mapping": token_attribution,
    }

    no_change = not closure_delta and not compdb_delta and not plan_delta and not any(field_rc.values())

    return {
        "target": selected,
        "baseline": {"previous": previous_id, "current": current_id},
        "message": "ok",
        "structural_change": structural,
        "command_change": command,
        "no_change": no_change,
    }


def why_to_text(result: dict[str, Any]) -> str:
    overview = result.get("target_overview", {})
    rebuild = result.get("rebuild_reasoning", {})

    lines = [
        f"Target: {result.get('target')}",
        f"Type: {overview.get('type')}",
        f"Direct Links: {', '.join(overview.get('direct_links', [])) or '<none>'}",
        f"Full Closure: {', '.join(overview.get('full_closure', [])) or '<none>'}",
        f"Closure Hash: {overview.get('closure_hash') or '<none>'}",
        "Edge Attribution:",
    ]

    for item in result.get("edge_attribution", []):
        lines.append(f"  - link: {item.get('link')}")
        lines.append(f"    origin: {item.get('origin')}")
        lines.append(f"    declared_in: {item.get('declared_in')}")
        lines.append(f"    snapshot_first_seen: {item.get('snapshot_first_seen')}")

    lines.append("Closure Attribution:")
    for item in result.get("closure_attribution", []):
        lines.append(f"  - dependency: {item.get('dependency')}")
        for chain in item.get("paths", []):
            lines.append(f"    path: {chain}")
        lines.append(f"    direct_link: {item.get('direct_link')}")
        lines.append(f"    indirect_link: {item.get('indirect_link')}")
        lines.append(f"    duplicate_link: {item.get('duplicate_link')}")

    lines.append(f"Rebuild Triggered: {'YES' if rebuild.get('triggered') else 'NO'}")
    lines.append("Reason:")
    for reason in rebuild.get("reasons", []):
        lines.append(f"  - {reason}")

    symbol_items = result.get("symbol_forensics", [])
    if symbol_items:
        lines.append("Symbol Forensics:")
        for item in symbol_items:
            lines.append(f"  - Symbol: {item.get('symbol')}")
            lines.append(f"    Likely defined in: {item.get('likely_target')} ({item.get('likely_source')})")
            if item.get("suggestion"):
                lines.append(f"    Missing link edge: {item['suggestion'].get('missing_link_edge')}")

    return "\n".join(lines)


def rebuild_cause_to_text(result: dict[str, Any]) -> str:
    lines = [
        f"Target: {result.get('target')}",
        f"Baseline: {result.get('baseline', {}).get('previous')} -> {result.get('baseline', {}).get('current')}",
        f"Message: {result.get('message')}",
        "STRUCTURAL CHANGE:",
    ]

    structural = result.get("structural_change", {})
    for key, value in structural.items():
        lines.append(f"  - {key}: {value}")

    lines.append("COMMAND CHANGE:")
    command = result.get("command_change", {})
    for key, value in command.items():
        lines.append(f"  - {key}: {value}")

    lines.append(f"NO CHANGE: {result.get('no_change')}")
    return "\n".join(lines)
