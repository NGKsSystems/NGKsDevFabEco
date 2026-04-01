from __future__ import annotations
"""Graph-native BuildPlan emitter contract.

Plan contract (lock-in):
- Emits deterministic IR to `build_graph/<profile>/ngksgraph_plan.json`.
- `plan` emission does not execute compile/link/toolchain commands.
- `plan` emission does not generate backend build scripts, compile_commands, snapshots, or build binaries.
- Hashing excludes timestamps (`generated_at`) and uses normalized paths.
- Missing target/profile errors are surfaced by CLI as clean non-traceback failures.

Determinism rules:
- Emitted JSON preserves logical pipeline order for readability.
- Hash inputs use normalized paths (`/` separators), with Windows drive-prefix lowercasing.
- Path arrays used in hashing are normalized and sorted.
"""

from datetime import datetime, timezone
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from ngksgraph.compdb import build_compile_command, build_link_command_for_graph
from ngksgraph.graph import BuildGraph, Target
from ngksgraph.hashutil import sha256_json, sha256_text, stable_json_dumps
from ngksgraph.log import write_json
from ngksgraph.util import normalize_path


def _obj_rel_path(target: Target, src: str) -> str:
    src_path = Path(src)
    no_suffix = src_path.with_suffix("")
    return normalize_path(Path(target.obj_dir) / f"{no_suffix}.obj")


def _target_output(target: Target) -> str:
    if target.kind == "staticlib":
        return normalize_path(Path(target.lib_dir) / f"{target.name}.lib")
    if target.kind == "shared":
        return normalize_path(Path(target.bin_dir) / f"{target.name}.dll")
    return normalize_path(Path(target.bin_dir) / f"{target.name}.exe")


def _toolchain_label(target: Target) -> str:
    compiler = str(target.toolchain.get("compiler", "cl"))
    linker = str(target.toolchain.get("linker", "link"))
    return f"{compiler}/{linker}"


def _normalize_hash_path(path: str) -> str:
    normalized = normalize_path(path)
    if re.match(r"^[A-Za-z]:/", normalized):
        return normalized.lower()
    return normalized


def _normalize_hash_list(values: list[str]) -> list[str]:
    return sorted(_normalize_hash_path(v) for v in values)


def _step_fingerprint(step: dict[str, Any], profile: str) -> str:
    payload = {
        "kind": str(step["kind"]),
        "inputs": _normalize_hash_list(list(step["inputs"])),
        "outputs": _normalize_hash_list(list(step["outputs"])),
        "defines": list(step["defines"]),
        "include_dirs": _normalize_hash_list(list(step["include_dirs"])),
        "cflags": list(step["cflags"]),
        "ldflags": list(step["ldflags"]),
        "libs": list(step["libs"]),
        "toolchain": str(step["toolchain"]),
        "profile": str(profile),
    }
    return sha256_json(payload)


def _step_id(step: dict[str, Any], profile: str) -> str:
    sid_payload = {
        "kind": str(step["kind"]),
        "inputs": _normalize_hash_list(list(step["inputs"])),
        "outputs": _normalize_hash_list(list(step["outputs"])),
        "toolchain": str(step["toolchain"]),
        "profile": str(profile),
    }
    sid_hash = sha256_json(sid_payload)[:12]
    return f"{step['kind']}_{sid_hash}"


def _compile_step(target: Target, src: str, profile: str) -> dict[str, Any]:
    obj = _obj_rel_path(target, src)
    toolchain = _toolchain_label(target)
    step = {
        "kind": "compile",
        "inputs": [normalize_path(src)],
        "outputs": [obj],
        "defines": list(target.defines),
        "include_dirs": [normalize_path(path) for path in target.include_dirs],
        "cflags": list(target.cflags),
        "ldflags": [],
        "libs": [],
        "toolchain": toolchain,
    }
    step["step_id"] = _step_id(step, profile)
    step["fingerprint"] = _step_fingerprint(step, profile)
    return step


def _link_step(graph: BuildGraph, target_name: str, profile: str) -> dict[str, Any]:
    target = graph.targets[target_name]
    obj_inputs = [_obj_rel_path(target, src) for src in sorted(target.sources)]

    dep_libs: list[str] = []
    for dep_name in graph.link_closure(target_name):
        dep = graph.targets[dep_name]
        if dep.kind == "staticlib":
            dep_libs.append(_target_output(dep))

    out = _target_output(target)
    inputs = obj_inputs + dep_libs

    toolchain = _toolchain_label(target)
    step = {
        "kind": "link",
        "inputs": inputs,
        "outputs": [out],
        "defines": [],
        "include_dirs": [],
        "cflags": [],
        "ldflags": list(target.ldflags),
        "libs": [f"{lib}.lib" for lib in target.libs],
        "toolchain": toolchain,
    }
    step["step_id"] = _step_id(step, profile)
    step["fingerprint"] = _step_fingerprint(step, profile)
    return step


def create_build_plan(
    repo_root: Path,
    *,
    project_name: str,
    profile: str,
    selected_target: str,
    graph: BuildGraph,
    graph_version: str,
    generator: str = "buildcore",
) -> dict[str, Any]:
    closure = set(graph.link_closure(selected_target))
    closure.add(selected_target)
    ordered_targets = [name for name in graph.build_order() if name in closure]

    plan_targets: list[dict[str, Any]] = []
    for target_name in ordered_targets:
        target = graph.targets[target_name]

        steps: list[dict[str, Any]] = []
        for src in sorted(target.sources):
            steps.append(_compile_step(target, src, profile))
        steps.append(_link_step(graph, target_name, profile))

        target_type = "shared" if target.kind == "shared" else target.kind
        plan_targets.append(
            {
                "name": target.name,
                "type": target_type,
                "output_path": _target_output(target),
                "steps": steps,
            }
        )

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    base = {
        "schema_version": 1,
        "project_root": normalize_path(repo_root.resolve()),
        "project": str(project_name),
        "profile": str(profile),
        "target": str(selected_target),
        "graph_version": str(graph_version),
        "generated_at": timestamp,
        "targets": plan_targets,
    }

    plan_id_payload = dict(base)
    plan_id_payload.pop("generated_at", None)
    plan_id = sha256_json(plan_id_payload)
    return {
        "plan_id": plan_id,
        **base,
    }


def write_build_plan_json(repo_root: Path, profile: str, plan: dict[str, Any]) -> Path:
    out_path = repo_root / "build_graph" / str(profile) / "ngksgraph_plan.json"
    write_json(out_path, plan)
    return out_path


def _buildcore_target_output(target: Target) -> str:
    if target.kind == "staticlib":
        return normalize_path(Path(target.lib_dir) / f"{target.name}.lib")
    if target.kind == "shared":
        return normalize_path(Path(target.bin_dir) / f"{target.name}.dll")
    return normalize_path(Path(target.bin_dir) / f"{target.name}.exe")


def _buildcore_obj_rel_path(target: Target, src: str) -> str:
    src_path = Path(src)
    no_suffix = src_path.with_suffix("")
    return normalize_path(Path(target.obj_dir) / f"{no_suffix}.obj")


def _stable_node_id(tool: str, target: str, action: str, cmd: str) -> str:
    digest = sha256_json({"cmd": cmd})[:12]
    return f"{tool}:{target}:{action}:{digest}"


def _staticlib_command(target: Target) -> str:
    obj_inputs = " ".join(_quote(_buildcore_obj_rel_path(target, src)) for src in sorted(target.sources))
    out_lib = _buildcore_target_output(target)
    return f"lib /nologo /OUT:{_quote(out_lib)} {obj_inputs}".strip()


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def _target_uses_qt(target: Target) -> bool:
    if bool(target.toolchain.get("qt_enabled", False)):
        return True
    return any(str(lib).startswith("Qt") for lib in target.libs)


def _target_windeployqt(target: Target) -> str:
    return str(target.toolchain.get("qt_windeployqt", "") or "").strip()


def _target_windeployqt_qmldir(target: Target) -> str:
    return str(target.toolchain.get("qt_windeployqt_qmldir", "") or "").strip()


def create_buildcore_plan(
    repo_root: Path,
    *,
    selected_target: str,
    graph: BuildGraph,
    profile: str = "",
) -> tuple[dict[str, Any], list[str]]:
    closure = set(graph.link_closure(selected_target))
    closure.add(selected_target)
    ordered_targets = [name for name in graph.build_order() if name in closure]

    nodes: list[dict[str, Any]] = []
    warnings: list[str] = []
    compile_ids_by_target: dict[str, list[str]] = {}
    link_id_by_target: dict[str, str] = {}

    for target_name in ordered_targets:
        target = graph.targets[target_name]
        compile_ids: list[str] = []

        for src in sorted(target.sources):
            cmd = build_compile_command(target, src)
            action = f"compile:{Path(src).name}"
            node_id = _stable_node_id("cl", target_name, action, cmd)
            outputs = [_buildcore_obj_rel_path(target, src)]
            node = {
                "id": node_id,
                "desc": f"Compile {src} for {target_name}",
                "cwd": normalize_path(repo_root.resolve()),
                "cmd": cmd,
                "deps": [],
                "inputs": [normalize_path(src)],
                "outputs": outputs,
                "env": {},
            }
            if not node["inputs"] or not node["outputs"]:
                warnings.append(f"NODE_IO_UNKNOWN: {node_id}")
            nodes.append(node)
            compile_ids.append(node_id)

        compile_ids_by_target[target_name] = sorted(compile_ids)

    for target_name in ordered_targets:
        target = graph.targets[target_name]
        if target.kind in ("staticlib", "lib"):
            cmd = _staticlib_command(target)
            tool_name = "lib"
            output = _buildcore_target_output(target)
        else:
            cmd = build_link_command_for_graph(graph, target_name)
            tool_name = "link"
            output = _buildcore_target_output(target)

        node_id = _stable_node_id(tool_name, target_name, "link", cmd)
        link_id_by_target[target_name] = node_id

        dep_ids = list(compile_ids_by_target.get(target_name, []))
        for dep_target in sorted(target.links):
            dep_node = link_id_by_target.get(dep_target)
            if dep_node:
                dep_ids.append(dep_node)

        if target.kind in ("staticlib", "lib"):
            inputs = [_buildcore_obj_rel_path(target, src) for src in sorted(target.sources)]
        else:
            dep_libs = []
            for dep_name in sorted(graph.link_closure(target_name)):
                dep = graph.targets[dep_name]
                if dep.kind in ("staticlib", "lib", "sharedlib"):
                    dep_libs.append(_buildcore_target_output(dep))
            inputs = [_buildcore_obj_rel_path(target, src) for src in sorted(target.sources)] + dep_libs

        node = {
            "id": node_id,
            "desc": f"Link {target_name}",
            "cwd": normalize_path(repo_root.resolve()),
            "cmd": cmd,
            "deps": sorted(set(dep_ids)),
            "inputs": sorted(set(inputs)),
            "outputs": [output],
            "env": {},
        }
        if not node["inputs"] or not node["outputs"]:
            warnings.append(f"NODE_IO_UNKNOWN: {node_id}")
        nodes.append(node)

        if target.kind == "exe" and _target_uses_qt(target):
            windeployqt_path = _target_windeployqt(target)
            if not windeployqt_path:
                warnings.append(f"QT_WINDEPLOYQT_MISSING: {target_name}")
            else:
                qmldir = _target_windeployqt_qmldir(target)
                profile_flag = "--release" if str(profile).lower() == "release" else "--debug" if str(profile).lower() == "debug" else ""
                flags = ["--compiler-runtime"]
                if profile_flag:
                    flags.insert(0, profile_flag)
                if qmldir:
                    flags.append(f"--qmldir {_quote(qmldir)}")
                flags_str = " ".join(flags)
                deploy_cmd = f"{_quote(windeployqt_path)} {flags_str} {_quote(output)}"
                deploy_id = _stable_node_id("windeployqt", target_name, "deploy", deploy_cmd)
                nodes.append(
                    {
                        "id": deploy_id,
                        "desc": f"Deploy Qt runtime for {target_name}",
                        "cwd": normalize_path(repo_root.resolve()),
                        "cmd": deploy_cmd,
                        "deps": [node_id],
                        "inputs": [output],
                        "outputs": [],
                        "env": {},
                    }
                )

    sorted_nodes = sorted(nodes, key=lambda n: str(n["id"]))
    for node in sorted_nodes:
        node["deps"] = sorted(set(str(x) for x in node.get("deps", [])))

    output_owners: dict[str, list[str]] = {}
    for node in sorted_nodes:
        node_id = str(node.get("id", ""))
        for out in node.get("outputs", []):
            key = normalize_path(str(out))
            output_owners.setdefault(key, []).append(node_id)
    for out_path, owners in sorted(output_owners.items()):
        unique_owners = sorted(set(owners))
        if len(unique_owners) > 1:
            warnings.append(f"DUPLICATE_OUTPUT: {out_path} :: {', '.join(unique_owners)}")

    payload = {
        "version": 1,
        "base_dir": normalize_path(repo_root.resolve()),
        "nodes": sorted_nodes,
    }
    return payload, warnings


def write_buildcore_plan_json(out_path: Path, payload: dict[str, Any]) -> Path:
    write_json(out_path, payload)
    return out_path


def _action_type_from_node_id(node_id: str) -> str:
    parts = str(node_id).split(":")
    tool = parts[0].strip().lower() if parts else ""
    if tool == "cl":
        return "compile"
    if tool in {"link", "lib"}:
        return "link"
    return "custom"


def _to_rel_or_norm(path_text: str, repo_root: Path) -> str:
    raw = normalize_path(path_text)
    path_obj = Path(raw)
    if not path_obj.is_absolute():
        return raw
    try:
        return normalize_path(path_obj.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return raw


def _parse_argv(cmd: str) -> list[str]:
    text = str(cmd or "").strip()
    if not text:
        return []
    try:
        return [str(part) for part in shlex.split(text, posix=False)]
    except Exception:
        return [text]


def _create_node_ecosystem_plan(
    repo_root: Path,
    *,
    profile: str,
    selected_target: str,
    env_capsule_hash: str,
) -> dict[str, Any] | None:
    pkg_path = (repo_root / "package.json").resolve()
    if not pkg_path.is_file():
        return None

    try:
        payload = json.loads(pkg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    scripts_raw = payload.get("scripts", {}) if isinstance(payload, dict) else {}
    scripts = scripts_raw if isinstance(scripts_raw, dict) else {}
    script_names = [str(k).strip() for k in scripts.keys() if str(k).strip()]
    if not script_names:
        return None

    requested = str(selected_target or "").strip()
    if requested and requested in scripts:
        script_name = requested
    elif "build" in scripts:
        script_name = "build"
    elif "dev" in scripts:
        script_name = "dev"
    else:
        script_name = sorted(script_names)[0]

    if (repo_root / "pnpm-lock.yaml").is_file():
        argv = ["pnpm", "run", script_name]
        package_manager = "pnpm"
    elif (repo_root / "yarn.lock").is_file():
        argv = ["yarn", script_name]
        package_manager = "yarn"
    else:
        argv = ["npm", "run", script_name]
        package_manager = "npm"

    inputs = ["package.json"]
    for lock_name in ("pnpm-lock.yaml", "yarn.lock", "package-lock.json"):
        if (repo_root / lock_name).is_file():
            inputs.append(lock_name)
            break

    return {
        "schema_version": 1,
        "project_root": ".",
        "profile": str(profile),
        "target": script_name,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "env_capsule_hash": str(env_capsule_hash),
        "requirements": {
            "language": "node",
            "package_manager": package_manager,
        },
        "toolchains": {},
        "runtimes": {
            "python": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
            },
            "node": {
                "script": script_name,
            },
        },
        "actions": [
            {
                "id": f"node:script:{script_name}",
                "type": "custom",
                "inputs": sorted(inputs),
                "outputs": [],
                "deps": [],
                "argv": argv,
                "cwd": ".",
            }
        ],
        "artifacts": [],
    }


def _create_flutter_ecosystem_plan(
    repo_root: Path,
    *,
    profile: str,
    selected_target: str,
    env_capsule_hash: str,
) -> dict[str, Any] | None:
    pubspec_path = (repo_root / "pubspec.yaml").resolve()
    if not pubspec_path.is_file():
        return None

    target = str(selected_target or "").strip().lower()
    if target in {"run", "dev"}:
        argv = ["flutter", "run"]
        action_name = "run"
    elif target in {"test", "check"}:
        argv = ["flutter", "test"]
        action_name = "test"
    else:
        if (repo_root / "windows").is_dir():
            argv = ["flutter", "build", "windows"]
            action_name = "build_windows"
        else:
            argv = ["flutter", "build"]
            action_name = "build"

    inputs = ["pubspec.yaml"]
    for maybe_file in ("pubspec.lock", "analysis_options.yaml"):
        if (repo_root / maybe_file).is_file():
            inputs.append(maybe_file)

    return {
        "schema_version": 1,
        "project_root": ".",
        "profile": str(profile),
        "target": str(selected_target or "build"),
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "env_capsule_hash": str(env_capsule_hash),
        "requirements": {
            "language": "flutter",
            "package_manager": "pub",
        },
        "toolchains": {},
        "runtimes": {
            "python": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
            },
            "dart": {
                "entry": "flutter",
            },
        },
        "actions": [
            {
                "id": f"flutter:{action_name}",
                "type": "custom",
                "inputs": sorted(inputs),
                "outputs": [],
                "deps": [],
                "argv": argv,
                "cwd": ".",
            }
        ],
        "artifacts": [],
    }


def create_ecosystem_build_plan(
    repo_root: Path,
    *,
    profile: str,
    selected_target: str,
    graph: BuildGraph | None,
    env_capsule_hash: str,
) -> dict[str, Any]:
    if graph is not None:
        buildcore_payload, _warnings = create_buildcore_plan(
            repo_root,
            selected_target=selected_target,
            graph=graph,
            profile=profile,
        )
        raw_nodes = buildcore_payload.get("nodes", []) if isinstance(buildcore_payload, dict) else []
        nodes = [node for node in raw_nodes if isinstance(node, dict)]

        actions: list[dict[str, Any]] = []
        for node in sorted(nodes, key=lambda item: str(item.get("id", ""))):
            node_id = str(node.get("id", ""))
            inputs = sorted({_to_rel_or_norm(str(v), repo_root) for v in (node.get("inputs", []) or []) if str(v).strip()})
            outputs = sorted({_to_rel_or_norm(str(v), repo_root) for v in (node.get("outputs", []) or []) if str(v).strip()})
            deps = sorted({str(v) for v in (node.get("deps", []) or []) if str(v).strip()})
            cwd_value = str(node.get("cwd", "") or "").strip()
            cwd = _to_rel_or_norm(cwd_value, repo_root) if cwd_value else "."

            actions.append(
                {
                    "id": node_id,
                    "type": _action_type_from_node_id(node_id),
                    "inputs": inputs,
                    "outputs": outputs,
                    "deps": deps,
                    "argv": _parse_argv(str(node.get("cmd", "") or "")),
                    "cwd": cwd,
                }
            )

        artifacts: set[str] = set()
        for action in actions:
            if str(action.get("type", "")) == "link":
                for output in action.get("outputs", []) or []:
                    if str(output).strip():
                        artifacts.add(str(output))

        compilers: set[str] = set()
        linkers: set[str] = set()
        cxx_stds: set[str] = set()
        for target in graph.targets.values():
            compilers.add(str(target.toolchain.get("compiler", "cl")))
            linkers.add(str(target.toolchain.get("linker", "link")))
            cxx_stds.add(str(target.cxx_std))

        return {
            "schema_version": 1,
            "project_root": ".",
            "profile": str(profile),
            "target": str(selected_target),
            "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "env_capsule_hash": str(env_capsule_hash),
            "requirements": {
                "language": "c++",
                "cxx_std": sorted(cxx_stds),
            },
            "toolchains": {
                "msvc": {
                    "compiler": sorted(compilers),
                    "linker": sorted(linkers),
                }
            },
            "runtimes": {
                "python": {
                    "major": sys.version_info.major,
                    "minor": sys.version_info.minor,
                }
            },
            "actions": actions,
            "artifacts": sorted(artifacts),
        }

    node_plan = _create_node_ecosystem_plan(
        repo_root,
        profile=profile,
        selected_target=selected_target,
        env_capsule_hash=env_capsule_hash,
    )
    if node_plan is not None:
        return node_plan

    flutter_plan = _create_flutter_ecosystem_plan(
        repo_root,
        profile=profile,
        selected_target=selected_target,
        env_capsule_hash=env_capsule_hash,
    )
    if flutter_plan is not None:
        return flutter_plan
    raise ValueError("ECOSYSTEM_GRAPH_REQUIRED_FOR_NON_NODE_PLANS")


def write_ecosystem_build_plan(repo_root: Path, plan: dict[str, Any]) -> tuple[Path, Path, str]:
    out_json = (repo_root / "build_plan.json").resolve()
    write_json(out_json, plan)

    canonical = stable_json_dumps(plan)
    digest = sha256_text(canonical)
    out_hash = (repo_root / "build_plan.hash.txt").resolve()
    out_hash.write_text(digest + "\n", encoding="utf-8")
    return out_json, out_hash, digest
