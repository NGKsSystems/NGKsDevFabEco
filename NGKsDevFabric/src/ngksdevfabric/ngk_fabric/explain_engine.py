from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _latest_run_by_prefix(runs_dir: Path, prefix: str) -> Path | None:
    candidates = [p for p in runs_dir.glob(f"{prefix}*") if p.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _load_context(project_root: Path) -> dict[str, Any]:
    proof_root = (project_root / "_proof").resolve()
    latest_run = proof_root / "latest" / "run"
    runs_dir = proof_root / "runs"

    component_graph_path = latest_run / "component_graph.json"
    if not component_graph_path.is_file():
        graph_run = _latest_run_by_prefix(runs_dir, "devfab_component_graph_")
        if graph_run is not None:
            component_graph_path = graph_run / "component_graph.json"

    impact_run = _latest_run_by_prefix(runs_dir, "devfab_impact_analysis_")
    rebuild_run = _latest_run_by_prefix(runs_dir, "devfab_incremental_rebuild_")
    runtime_run = _latest_run_by_prefix(runs_dir, "devfab_runtime_resolution_")
    provisioning_run = _latest_run_by_prefix(runs_dir, "devfab_toolchain_provisioning_")

    component_graph = _read_json(component_graph_path) if component_graph_path.is_file() else {}
    impact_cases = _read_json(impact_run / "06_impact_analysis.json") if impact_run else []
    rebuild_cases = _read_json(rebuild_run / "04_rebuild_cases.json") if rebuild_run else []
    runtime_resolution = _read_json(runtime_run / "05_runtime_resolution.json") if runtime_run else []
    provisioning_plan = _read_json(provisioning_run / "environment_bootstrap_plan.json") if provisioning_run else []
    route_readiness = _read_json(provisioning_run / "11_route_readiness_matrix.json") if provisioning_run else []

    return {
        "proof_root": str(proof_root),
        "component_graph_path": str(component_graph_path),
        "impact_run": str(impact_run) if impact_run else "",
        "rebuild_run": str(rebuild_run) if rebuild_run else "",
        "runtime_run": str(runtime_run) if runtime_run else "",
        "provisioning_run": str(provisioning_run) if provisioning_run else "",
        "component_graph": component_graph if isinstance(component_graph, dict) else {},
        "impact_cases": impact_cases if isinstance(impact_cases, list) else [],
        "rebuild_cases": rebuild_cases if isinstance(rebuild_cases, list) else [],
        "runtime_resolution": runtime_resolution if isinstance(runtime_resolution, list) else [],
        "provisioning_plan": provisioning_plan if isinstance(provisioning_plan, list) else [],
        "route_readiness": route_readiness if isinstance(route_readiness, list) else [],
    }


def _component_sets(ctx: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    graph = ctx.get("component_graph", {})
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    node_list = [n for n in nodes if isinstance(n, dict)]
    edge_list = [e for e in edges if isinstance(e, dict)]
    comps = [str(n.get("component_id", "")).strip() for n in node_list if str(n.get("component_id", "")).strip()]
    return node_list, edge_list, comps


def _owner_for_file(file_path: str, nodes: list[dict[str, Any]]) -> tuple[str, str]:
    rel = file_path.replace("\\", "/")
    prefix_map = {
        "app/python_workers/": "python_workers",
        "app/sql/": "sql_schema",
        "app/ts_panel/": "ts_panel",
        "app/reports/": "reporting_templates",
        "app/python_host/": "python_host",
        "app/cpp_host/": "cpp_host",
        "certification/": "validation_harness",
    }
    for prefix, comp in prefix_map.items():
        if rel.startswith(prefix):
            return comp, "prefix_map"

    for node in nodes:
        comp_id = str(node.get("component_id", "")).strip()
        for ev in node.get("evidence_files", []) or []:
            ev_str = str(ev).replace("\\", "/")
            if rel == ev_str:
                return comp_id, "exact_evidence"
    return "unknown", "unresolved"


def _neighbors(component: str, edges: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    deps: list[str] = []
    dependents: list[str] = []
    for e in edges:
        frm = str(e.get("from", "")).strip()
        to = str(e.get("to", "")).strip()
        if frm == component and to:
            deps.append(to)
        if to == component and frm:
            dependents.append(frm)
    return sorted(set(deps)), sorted(set(dependents))


def _route_map_for_components(components: list[str]) -> list[str]:
    route_map = {
        "python_workers": ["python_worker_orchestration_route"],
        "legacy_worker": ["python_worker_orchestration_route"],
        "modern_worker": ["python_worker_orchestration_route"],
        "reporting_templates": ["report_generation_route"],
        "sql_schema": ["schema_validation_route"],
        "ts_panel": ["node_ts_build_route", "node_package_manager_route"],
        "host_runtime_layer": ["host_backend_route"],
    }
    routes: list[str] = []
    for comp in components:
        routes.extend(route_map.get(comp, []))
    return sorted(set(routes))


def _component_environments(component: str, provisioning_plan: list[dict[str, Any]]) -> list[str]:
    envs: list[str] = []
    for scenario in provisioning_plan:
        for env in scenario.get("reusable_environments", []) or []:
            if component in (env.get("assigned_components", []) or []):
                envs.append(str(env.get("environment_id", "")))
        for env in scenario.get("environments_to_create", []) or []:
            if component in (env.get("assigned_components", []) or []):
                envs.append(str(env.get("environment_id", "")))
    return sorted(set([e for e in envs if e]))


def _component_toolchains(component: str, provisioning_plan: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for scenario in provisioning_plan:
        for tool in scenario.get("required_toolchains", []) or []:
            if component in (tool.get("used_by_components", []) or []):
                name = str(tool.get("toolchain_name", "")).strip()
                if name:
                    tools.append(name)
    return sorted(set(tools))


def _graph_edges_for_components(components: list[str], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comp_set = set(components)
    out: list[dict[str, Any]] = []
    for e in edges:
        frm = str(e.get("from", "")).strip()
        to = str(e.get("to", "")).strip()
        if frm in comp_set or to in comp_set:
            out.append(
                {
                    "from": frm,
                    "to": to,
                    "edge_type": str(e.get("edge_type", "")),
                    "evidence_files": e.get("evidence_files", []) or [],
                }
            )
    return out


def _explain_file(query: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, all_components = _component_sets(ctx)
    file_path = str(query.get("path", "")).strip()
    owner, owner_mode = _owner_for_file(file_path, nodes)
    deps, dependents = _neighbors(owner, edges) if owner != "unknown" else ([], [])
    affected = sorted(set([owner] + deps + dependents)) if owner != "unknown" else []
    skipped = sorted(set(all_components) - set(affected))
    routes = _route_map_for_components(affected)

    rebuild_case = None
    for case in ctx.get("rebuild_cases", []):
        if str(case.get("mutated_file", "")).replace("\\", "/") == file_path.replace("\\", "/"):
            rebuild_case = case
            break
    rebuild_steps = rebuild_case.get("rebuild_order", []) if isinstance(rebuild_case, dict) else []

    referencing_files: list[str] = []
    for edge in _graph_edges_for_components([owner], edges):
        for ev in edge.get("evidence_files", []):
            referencing_files.append(str(ev))

    runtime_env = _component_environments(owner, ctx.get("provisioning_plan", []))
    toolchains = _component_toolchains(owner, ctx.get("provisioning_plan", []))
    graph_edges = _graph_edges_for_components(affected, edges)

    confidence = "high" if owner != "unknown" else "low"
    confidence_reason = "owner resolved from graph/path evidence" if owner != "unknown" else "owner could not be resolved from graph evidence"
    reason_chain = [
        f"{file_path} maps to owning component {owner}",
        f"direct dependencies: {', '.join(deps) if deps else 'none'}",
        f"dependent components: {', '.join(dependents) if dependents else 'none'}",
        f"affected routes: {', '.join(routes) if routes else 'none'}",
    ]

    return {
        "entity": file_path,
        "entity_type": "file",
        "owning_component": owner,
        "referencing_files": sorted(set(referencing_files)),
        "reason_chain": reason_chain,
        "affected_components": affected,
        "skipped_components": skipped,
        "routes_affected": routes,
        "rebuild_steps_triggered": rebuild_steps,
        "runtime_environment": runtime_env,
        "toolchain_requirements": toolchains,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "evidence_files": sorted(set([file_path, ctx.get("component_graph_path", "")])) + sorted(set(referencing_files)),
        "graph_edges_used": graph_edges,
        "rationale": f"Resolved with owner mode={owner_mode}; used component graph edges and latest rebuild/provisioning artifacts.",
    }


def _explain_rebuild(ctx: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, all_components = _component_sets(ctx)
    rebuild_cases = [c for c in ctx.get("rebuild_cases", []) if isinstance(c, dict)]
    trigger_files = [str(c.get("mutated_file", "")) for c in rebuild_cases if str(c.get("mutated_file", "")).strip()]
    affected: list[str] = []
    skipped: list[str] = []
    rebuild_plan: list[dict[str, Any]] = []
    for case in rebuild_cases:
        affected.extend(case.get("rebuild_required_components", []) or [])
        skipped.extend(case.get("rebuild_skippable_components", []) or [])
        rebuild_plan.append(
            {
                "case_id": case.get("case_id", ""),
                "rebuild_order": case.get("rebuild_order", []) or [],
            }
        )
    affected = sorted(set([a for a in affected if isinstance(a, str) and a]))
    skipped = sorted(set([s for s in skipped if isinstance(s, str) and s]))

    runtime_envs: list[str] = []
    toolchains: list[str] = []
    provisioning_requirements: list[str] = []
    for scenario in ctx.get("provisioning_plan", []):
        for env in scenario.get("reusable_environments", []) or []:
            runtime_envs.append(str(env.get("environment_id", "")))
        for env in scenario.get("environments_to_create", []) or []:
            runtime_envs.append(str(env.get("environment_id", "")))
        for tool in scenario.get("required_toolchains", []) or []:
            name = str(tool.get("toolchain_name", "")).strip()
            if name:
                toolchains.append(name)
        provisioning_requirements.extend(scenario.get("missing_installations", []) or [])

    graph_edges = _graph_edges_for_components(affected, edges)
    reason_chain = [
        f"trigger files: {', '.join(trigger_files) if trigger_files else 'none'}",
        f"affected components from latest rebuild plan: {', '.join(affected) if affected else 'none'}",
        f"rebuild order extracted from rebuild artifacts: {len(rebuild_plan)} case(s)",
    ]

    confidence = "high" if rebuild_cases else "medium"
    confidence_reason = "latest incremental rebuild artifacts found" if rebuild_cases else "rebuild artifacts not found; explanation degraded"
    return {
        "entity": "latest_rebuild",
        "entity_type": "rebuild",
        "trigger_files": trigger_files,
        "reason_chain": reason_chain,
        "affected_components": affected,
        "skipped_components": skipped if skipped else sorted(set(all_components) - set(affected)),
        "rebuild_plan": rebuild_plan,
        "runtime_environment": sorted(set([e for e in runtime_envs if e])),
        "toolchain_requirements": sorted(set(toolchains)),
        "provisioning_requirements": sorted(set([p for p in provisioning_requirements if p])),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "evidence_files": [ctx.get("rebuild_run", ""), ctx.get("provisioning_run", ""), ctx.get("component_graph_path", "")],
        "graph_edges_used": graph_edges,
        "rationale": "Joined latest rebuild, provisioning, and component graph artifacts to explain current rebuild decision path.",
    }


def _explain_route(query: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, all_components = _component_sets(ctx)
    route = str(query.get("route_id", "")).strip()
    owners_by_route = {
        "python_worker_orchestration_route": ["python_workers", "legacy_worker", "modern_worker"],
        "report_generation_route": ["reporting_templates", "python_workers"],
        "node_ts_build_route": ["ts_panel"],
        "node_package_manager_route": ["ts_panel"],
        "schema_validation_route": ["sql_schema", "python_workers"],
        "host_backend_route": ["host_runtime_layer", "cpp_host", "python_host"],
    }
    owners = owners_by_route.get(route, [])
    deps: list[str] = []
    for owner in owners:
        owner_deps, _ = _neighbors(owner, edges)
        deps.extend(owner_deps)
    affected = sorted(set(owners + deps))
    skipped = sorted(set(all_components) - set(affected))

    runtime_env: list[str] = []
    required_tools: list[str] = []
    provisioning_reqs: list[str] = []
    for rr in ctx.get("route_readiness", []):
        if str(rr.get("route_id", "")) == route:
            runtime_env.extend(rr.get("required_environments", []) or [])
            required_tools.extend(rr.get("required_toolchains", []) or [])
            provisioning_reqs.extend(rr.get("blocked_by", []) or [])

    validations: list[str] = []
    for case in ctx.get("rebuild_cases", []):
        if route in (case.get("affected_routes", []) or []):
            validations.extend(case.get("validation_required", []) or [])

    graph_edges = _graph_edges_for_components(affected, edges)
    confidence = "high" if owners else "medium"
    confidence_reason = "route mapped to known owner components" if owners else "route ownership inferred from static route map only"
    reason_chain = [
        f"route {route} owners: {', '.join(owners) if owners else 'unknown'}",
        f"owner dependencies: {', '.join(sorted(set(deps))) if deps else 'none'}",
        f"runtime environments: {', '.join(sorted(set(runtime_env))) if runtime_env else 'not mapped'}",
    ]
    return {
        "entity": route,
        "entity_type": "route",
        "owning_component": owners,
        "reason_chain": reason_chain,
        "affected_components": affected,
        "skipped_components": skipped,
        "runtime_environment": sorted(set(runtime_env)),
        "toolchain_requirements": sorted(set(required_tools)),
        "dependencies": sorted(set(deps)),
        "validations_triggered": sorted(set(validations)),
        "provisioning_requirements": sorted(set(provisioning_reqs)),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "evidence_files": [ctx.get("component_graph_path", ""), ctx.get("provisioning_run", ""), ctx.get("rebuild_run", "")],
        "graph_edges_used": graph_edges,
        "rationale": "Route explanation combines owner mapping, component graph edges, provisioning route matrix, and rebuild validation mapping.",
    }


def _explain_dependency(query: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, all_components = _component_sets(ctx)
    component = str(query.get("component", "")).strip()
    direct, _ = _neighbors(component, edges)
    visited = set([component])
    frontier = list(direct)
    indirect: set[str] = set()
    while frontier:
        cur = frontier.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        if cur not in direct:
            indirect.add(cur)
        nxt, _ = _neighbors(cur, edges)
        for n in nxt:
            if n not in visited:
                frontier.append(n)

    why: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    for e in edges:
        frm = str(e.get("from", "")).strip()
        to = str(e.get("to", "")).strip()
        if frm == component and to:
            reason = f"{frm} depends on {to} via {str(e.get('edge_type', 'dependency'))}"
            why.append(
                {
                    "dependency": to,
                    "why": reason,
                    "evidence_files": e.get("evidence_files", []) or [],
                }
            )
            graph_edges.append(
                {
                    "from": frm,
                    "to": to,
                    "edge_type": str(e.get("edge_type", "")),
                    "evidence_files": e.get("evidence_files", []) or [],
                }
            )

    affected = sorted(set([component] + direct + list(indirect)))
    skipped = sorted(set(all_components) - set(affected))
    runtime_env = _component_environments(component, ctx.get("provisioning_plan", []))
    tools = _component_toolchains(component, ctx.get("provisioning_plan", []))

    confidence = "high" if direct else "medium"
    confidence_reason = "direct dependency edges found in component graph" if direct else "no direct edges found; dependency explanation limited"
    reason_chain = [f"direct dependencies: {', '.join(direct) if direct else 'none'}", f"indirect dependencies: {', '.join(sorted(indirect)) if indirect else 'none'}"]
    return {
        "entity": component,
        "entity_type": "dependency",
        "direct_dependencies": direct,
        "indirect_dependencies": sorted(indirect),
        "dependency_reasons": why,
        "reason_chain": reason_chain,
        "affected_components": affected,
        "skipped_components": skipped,
        "runtime_environment": runtime_env,
        "toolchain_requirements": tools,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "evidence_files": [ctx.get("component_graph_path", "")],
        "graph_edges_used": graph_edges,
        "rationale": "Dependency explanation is derived from directed graph edges and edge evidence metadata.",
    }


def run_explain_query(query: dict[str, Any], project_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    ctx = _load_context(project_root)
    mode = str(query.get("mode", "")).strip()
    if mode == "file":
        result = _explain_file(query, ctx)
    elif mode == "rebuild":
        result = _explain_rebuild(ctx)
    elif mode == "route":
        result = _explain_route(query, ctx)
    elif mode == "dependency":
        result = _explain_dependency(query, ctx)
    else:
        result = {
            "entity": mode,
            "entity_type": "unknown",
            "reason_chain": ["unsupported explain mode"],
            "affected_components": [],
            "skipped_components": [],
            "runtime_environment": [],
            "toolchain_requirements": [],
            "confidence": "low",
            "confidence_reason": "unsupported mode",
            "evidence_files": [],
            "graph_edges_used": [],
            "rationale": "Explain mode is not recognized.",
        }
    return result, ctx


def _load_list(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    data = _read_json(path)
    return data if isinstance(data, list) else []


def persist_explain_bundle(
    *,
    pf: Path,
    project_root: Path,
    query: dict[str, Any],
    result: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    pf.mkdir(parents=True, exist_ok=True)

    manifest = {
        "app": "NGKsDevFabEco",
        "objective": "explain_my_build_reasoning_engine",
        "run_id": pf.name,
        "timestamp": _now_iso(),
        "project_root": str(project_root),
        "proof_dir": str(pf),
    }
    _write_json(pf / "00_run_manifest.json", manifest)
    (pf / "01_environment.txt").write_text(
        "\n".join(
            [
                f"timestamp_utc={_now_iso()}",
                f"project_root={project_root}",
                "engine=devfab_explain",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (pf / "02_target_paths.txt").write_text(
        "\n".join(
            [
                f"proof_root={ctx.get('proof_root', '')}",
                f"component_graph_path={ctx.get('component_graph_path', '')}",
                f"impact_run={ctx.get('impact_run', '')}",
                f"rebuild_run={ctx.get('rebuild_run', '')}",
                f"runtime_run={ctx.get('runtime_run', '')}",
                f"provisioning_run={ctx.get('provisioning_run', '')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    queries_path = pf / "explain_queries.json"
    results_path = pf / "explain_results.json"
    chains_path = pf / "explain_reason_chains.json"
    edges_path = pf / "explain_graph_edges.json"

    queries = _load_list(queries_path)
    results = _load_list(results_path)
    chains = _load_list(chains_path)
    edge_rows = _load_list(edges_path)

    query_record = {
        "timestamp": _now_iso(),
        "mode": query.get("mode", ""),
        "path": query.get("path", ""),
        "route_id": query.get("route_id", ""),
        "component": query.get("component", ""),
    }
    queries.append(query_record)
    results.append(result)
    chains.append(
        {
            "entity": result.get("entity", ""),
            "entity_type": result.get("entity_type", ""),
            "reason_chain": result.get("reason_chain", []),
            "confidence": result.get("confidence", ""),
        }
    )
    edge_rows.append(
        {
            "entity": result.get("entity", ""),
            "entity_type": result.get("entity_type", ""),
            "graph_edges_used": result.get("graph_edges_used", []),
        }
    )

    _write_json(queries_path, queries)
    _write_json(results_path, results)
    _write_json(chains_path, chains)
    _write_json(edges_path, edge_rows)

    _write_json(pf / "03_explain_queries.json", queries)
    _write_json(pf / "04_explain_results.json", results)
    _write_json(pf / "05_reason_chains.json", chains)
    _write_json(pf / "06_explain_graph_edges.json", edge_rows)

    low_conf = [r for r in results if str(r.get("confidence", "")).lower() == "low"]
    gate = "PASS" if not low_conf else "PARTIAL"
    summary_lines = [
        "# Explain Engine Summary",
        "",
        f"- run_id: {pf.name}",
        f"- queries_executed: {len(queries)}",
        f"- latest_entity: {result.get('entity', '')}",
        f"- latest_entity_type: {result.get('entity_type', '')}",
        f"- latest_confidence: {result.get('confidence', '')}",
        f"- evidence_backed: {'true' if bool(result.get('graph_edges_used')) else 'false'}",
        f"- final_gate: {gate}",
    ]
    summary_text = "\n".join(summary_lines) + "\n"
    (pf / "explain_summary.md").write_text(summary_text, encoding="utf-8")
    (pf / "07_explain_summary.md").write_text(summary_text, encoding="utf-8")
    (pf / "13_summary.md").write_text(summary_text, encoding="utf-8")
    (pf / "18_summary.md").write_text(
        "\n".join(
            [
                "# Explain Engine Final Summary",
                "",
                f"- Queries executed: {len(queries)}",
                f"- Evidence-backed: {'yes' if bool(result.get('graph_edges_used')) else 'no'}",
                f"- Final gate: {gate}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    dot_lines = ["digraph explain {", "  rankdir=LR;"]
    entity = str(result.get("entity", "")).replace('"', "")
    dot_lines.append(f'  "{entity}" [shape=box];')
    for edge in result.get("graph_edges_used", []):
        frm = str(edge.get("from", "")).replace('"', "")
        to = str(edge.get("to", "")).replace('"', "")
        label = str(edge.get("edge_type", "dependency")).replace('"', "")
        if frm and to:
            dot_lines.append(f'  "{frm}" -> "{to}" [label="{label}"];')
    dot_lines.append("}")
    (pf / "explain_visualization.dot").write_text("\n".join(dot_lines) + "\n", encoding="utf-8")

    return {
        "queries_executed": len(queries),
        "final_gate": gate,
        "summary_path": str(pf / "07_explain_summary.md"),
        "results_path": str(results_path),
    }