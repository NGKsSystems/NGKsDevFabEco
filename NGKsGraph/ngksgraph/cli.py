from __future__ import annotations

import argparse
import difflib
import importlib.resources as importlib_resources
import json
import hashlib
import re
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from ngksgraph.build import (
    build_project,
    clean_project,
    configure_project,
    emit_buildcore_plan,
    emit_build_plan,
    explain_link,
    explain_source,
    inspect_plan_cache,
    load_graph_payload,
    run_binary,
    trace_source,
    resolve_plan_context,
)
from ngksgraph.plan import create_buildcore_plan
from ngksgraph.plan import create_ecosystem_build_plan, write_ecosystem_build_plan
from ngksgraph import __version__
from ngksgraph.capsule import freeze_capsule, thaw_capsule, verify_capsule
from ngksgraph.binary_contract import inspect_binary_integrity
from ngksgraph.compdb_contract import load_compdb, validate_compdb
from ngksgraph.config import load_config
from ngksgraph.diff import diff_to_text, resolve_snapshot, stable_diff_json, structural_diff
from ngksgraph.forensics import rebuild_cause_target, rebuild_cause_to_text, why_target, why_to_text
from ngksgraph.graph_contract import validate_graph_integrity, validate_profile_parity
from ngksgraph.import_cmake import import_cmake_project
from ngksgraph.hashutil import stable_json_dumps
from ngksgraph.log import write_json
from ngksgraph.mode import get_mode, is_ecosystem
from ngksgraph.toolchain import doctor_report, doctor_toolchain_report
from ngksgraph.plan_cache import CACHE_SCHEMA_VERSION
from ngksgraph.msvc import bootstrap_msvc, resolve_msvc_toolchain_paths
from ngksgraph.proof import TeeTextIO, gather_git_metadata, new_proof_run, write_summary, zip_run, resolve_repo_root
from ngksgraph.repo_classifier import classify_repo, synthesize_init_toml
from ngksgraph.scan_pipeline import run_scan
from ngksgraph.targetspec import load_or_derive_target_spec
from ngksgraph.capability import build_capability_inventory
from ngksgraph.resolver import resolve_target_capabilities, write_resolution_artifacts


CONTRACTS_STAMP = "6G,6H,7,9"


def _resolve_git_commit(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            shell=False,
        )
        if proc.returncode == 0:
            text = (proc.stdout or "").strip()
            if text:
                return text
    except Exception:
        pass
    return "unknown"


def version_string(repo_root: Path | None = None) -> str:
    root = repo_root or Path.cwd()
    commit = _resolve_git_commit(root)
    return f"NGKsGraph {__version__} ({commit}) cache_schema={CACHE_SCHEMA_VERSION} contracts={CONTRACTS_STAMP}"


def _repo_root_from_cwd() -> Path:
    return Path.cwd()


def _resolve_project_root(raw_project: str | None) -> Path:
    if raw_project is None:
        return Path.cwd().resolve()
    p = Path(str(raw_project)).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if p.is_file():
        return p.parent.resolve()
    return p.resolve()


def _resolve_repo_and_config(raw_project: str | None, *, require_config: bool = True) -> tuple[Path | None, Path | None]:
    repo_root = _resolve_project_root(raw_project)
    config_path = _config_path(repo_root)
    if require_config and not config_path.exists():
        print(f"CONFIG_NOT_FOUND: expected ngksgraph.toml under {repo_root}")
        return None, None
    return repo_root, config_path


def _first_missing_tool(tools: dict[str, str]) -> tuple[str, str] | None:
    for key in ["cl", "link", "lib"]:
        p = str(tools.get(key, "") or "")
        if not p or not Path(p).exists():
            return key, p
    return None


def _config_path(repo_root: Path) -> Path:
    return repo_root / "ngksgraph.toml"


def _parse_seed_range(raw: str) -> range:
    text = str(raw).strip()
    if ".." in text:
        left, right = text.split("..", 1)
        start = int(left.strip())
        end = int(right.strip())
    else:
        start = int(text)
        end = int(text)
    if end < start:
        raise ValueError("seeds must be in ascending order, e.g. 1..5")
    return range(start, end + 1)


def _default_selftest_out(repo_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return repo_root / "artifacts" / "selftest" / stamp


def _new_component_proof_dir(repo_root: Path, explicit_pf: str | None = None) -> Path:
    if explicit_pf:
        proof_dir = Path(explicit_pf).resolve()
        proof_dir.mkdir(parents=True, exist_ok=True)
        return proof_dir
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    proof_dir = (repo_root / "_proof" / f"graph_ecosystem_{stamp}").resolve()
    suffix = 1
    while proof_dir.exists():
        proof_dir = (repo_root / "_proof" / f"graph_ecosystem_{stamp}_{suffix:02d}").resolve()
        suffix += 1
    proof_dir.mkdir(parents=True, exist_ok=False)
    return proof_dir


def _hash_lock_file(lock_path: Path) -> str:
    raw = lock_path.read_bytes()
    try:
        parsed = json.loads(raw.decode("utf-8"))
        canonical = stable_json_dumps(parsed)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(raw).hexdigest()


def _read_capsule_hash_file(hash_path: Path) -> str:
    text = hash_path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", text):
        raise ValueError(f"INVALID_ENV_CAPSULE_HASH: {hash_path}")
    return text.lower()


def _resolve_env_capsule_binding(args: argparse.Namespace, repo_root: Path) -> tuple[str, str, Path]:
    lock_raw = getattr(args, "env_capsule_lock", None)
    hash_raw = getattr(args, "env_capsule_hash", None)
    if lock_raw:
        lock_path = Path(str(lock_raw))
        if not lock_path.is_absolute():
            lock_path = (repo_root / lock_path).resolve()
        if not lock_path.exists():
            raise ValueError(f"ENV_CAPSULE_LOCK_NOT_FOUND: {lock_path}")
        digest = _hash_lock_file(lock_path)
        return digest, "lock", lock_path

    if hash_raw:
        hash_path = Path(str(hash_raw))
        if not hash_path.is_absolute():
            hash_path = (repo_root / hash_path).resolve()
        if not hash_path.exists():
            raise ValueError(f"ENV_CAPSULE_HASH_NOT_FOUND: {hash_path}")
        digest = _read_capsule_hash_file(hash_path)
        return digest, "hash", hash_path

    raise ValueError("ECOSYSTEM_MODE_REQUIRES_ENV_CAPSULE_BINDING")


def _write_ecosystem_inputs(
    proof_dir: Path,
    *,
    profile: str | None,
    target: str | None,
    binding_kind: str,
    binding_path: Path,
    env_capsule_hash: str,
) -> None:
    lines = [
        f"mode=ecosystem",
        f"profile={profile or '<default>'}",
        f"target={target or '<default>'}",
        f"env_capsule_binding={binding_kind}",
        f"env_capsule_path={binding_path}",
        f"env_capsule_hash={env_capsule_hash}",
    ]
    (proof_dir / "10_inputs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (proof_dir / "inputs_env_capsule.txt").write_text("\n".join(lines[3:]) + "\n", encoding="utf-8")


def _write_ecosystem_outputs(
    proof_dir: Path,
    *,
    plan_path: Path,
    plan_hash_path: Path,
    digest: str,
    backend: str,
    build_artifact: Path | None = None,
) -> None:
    lines = [
        f"build_plan={plan_path}",
        f"build_plan_hash_file={plan_hash_path}",
        f"build_plan_sha256={digest}",
        f"backend={backend}",
    ]
    if build_artifact is not None:
        lines.append(f"build_artifact={build_artifact}")
    (proof_dir / "20_outputs.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ecosystem_error(proof_dir: Path, message: str) -> None:
    (proof_dir / "30_errors.txt").write_text(str(message).strip() + "\n", encoding="utf-8")


def _run_target_resolution(
    *,
    repo_root: Path,
    configured: dict[str, Any],
    resolution_out_dir: Path,
) -> tuple[bool, dict[str, str], dict[str, Any]]:
    config = configured["config"]
    graph = configured["graph"]
    selected_target = str(configured["selected_target"])
    profile = str(configured.get("profile", "debug"))

    target_spec, spec_source, spec_path = load_or_derive_target_spec(
        repo_root=repo_root,
        config=config,
        graph=graph,
        selected_target=selected_target,
        profile=profile,
    )
    target = graph.targets[selected_target]
    inventory = build_capability_inventory(config=config, target=target)
    report = resolve_target_capabilities(target_spec=target_spec, inventory=inventory)
    artifact_map = write_resolution_artifacts(
        output_dir=resolution_out_dir,
        target_spec=target_spec,
        inventory=inventory,
        report=report,
        spec_source=spec_source,
        spec_path=spec_path,
    )
    resolution_payload = report.to_dict()
    resolution_payload["artifact_map"] = artifact_map
    resolution_payload["spec_source"] = spec_source
    resolution_payload["spec_path"] = spec_path
    return bool(report.build_allowed), artifact_map, resolution_payload


def _read_init_template_text(template_name: str, repo_root: Path) -> str | None:
    repo_template = repo_root / "templates" / template_name
    if repo_template.exists():
        return repo_template.read_text(encoding="utf-8")

    try:
        package_template = importlib_resources.files("ngksgraph").joinpath("templates", template_name)
        return package_template.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return None


def cmd_init(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    dest = _config_path(repo_root)
    if dest.exists() and not args.force:
        print("ngksgraph.toml already exists. Use --force to overwrite.")
        return 1
    template_map = {
        "default": "default_ngksgraph.toml",
        "basic": "default_ngksgraph.toml",
        "qt-app": "qt_app_ngksgraph.toml",
        "multi-target": "multi_target_ngksgraph.toml",
    }
    selected = str(args.template or "default").strip().lower()
    template_name = template_map.get(selected)
    if not template_name:
        print(f"Unknown template '{args.template}'. Available: default, basic, qt-app, multi-target")
        return 1

    template_text = _read_init_template_text(template_name, repo_root)
    if selected in {"default", "basic"}:
        try:
            classification = classify_repo(repo_root)
            template_text = synthesize_init_toml(classification)
            print(
                f"Auto-detected repo family: {classification.family} "
                f"(qt_signals={classification.qt_signal_count}, entrypoints={classification.entrypoint_count})"
            )
        except Exception as exc:
            print(f"INIT_CLASSIFIER_ERROR: {exc}")
            return 1
    if template_text is None:
        print("Template not found.")
        return 1
    dest.write_text(template_text, encoding="utf-8")
    print(f"Created {dest}")
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1
    configured = resolve_plan_context(
        repo_root,
        config_path,
        target=args.target,
        profile=args.profile,
    )
    out_path = emit_build_plan(repo_root, configured)
    print(f"Configured plan: {out_path}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1

    mode = get_mode(args)
    if is_ecosystem(mode):
        proof_dir = _new_component_proof_dir(repo_root, getattr(args, "pf", None))
        try:
            env_capsule_hash, binding_kind, binding_path = _resolve_env_capsule_binding(args, repo_root)
            configured = resolve_plan_context(
                repo_root,
                config_path,
                target=args.target,
                profile=args.profile,
            )
            profile_name = str(configured.get("profile", args.profile or "debug"))
            resolution_out_dir = (proof_dir / "graph_resolution").resolve()
            build_allowed, _artifact_map, resolution_payload = _run_target_resolution(
                repo_root=repo_root,
                configured=configured,
                resolution_out_dir=resolution_out_dir,
            )
            if not build_allowed:
                _write_ecosystem_error(
                    proof_dir,
                    "TARGET_RESOLUTION_BLOCKED: required capabilities missing/conflicting/downgraded."
                    f" resolution_report={resolution_out_dir / '14_resolution_report.json'}",
                )
                print(
                    "TARGET_RESOLUTION_BLOCKED: "
                    f"missing={len(resolution_payload.get('missing', []))} "
                    f"conflicting={len(resolution_payload.get('conflicting', []))} "
                    f"downgraded={len(resolution_payload.get('downgraded', []))}",
                    file=sys.stderr,
                )
                print(f"Resolution report: {resolution_out_dir / '14_resolution_report.json'}", file=sys.stderr)
                return 2
            plan = create_ecosystem_build_plan(
                repo_root,
                profile=profile_name,
                selected_target=str(configured["selected_target"]),
                graph=configured["graph"],
                env_capsule_hash=env_capsule_hash,
            )
            plan_path, plan_hash_path, digest = write_ecosystem_build_plan(repo_root, plan)

            backend = "none"

            _write_ecosystem_inputs(
                proof_dir,
                profile=args.profile,
                target=args.target,
                binding_kind=binding_kind,
                binding_path=binding_path,
                env_capsule_hash=env_capsule_hash,
            )
            _write_ecosystem_outputs(
                proof_dir,
                plan_path=plan_path,
                plan_hash_path=plan_hash_path,
                digest=digest,
                backend=backend,
            )
            print(f"Plan file: {plan_path}")
            print(f"Plan hash: {plan_hash_path}")
            print(f"Proof dir: {proof_dir}")
            return 0
        except KeyError as exc:
            missing = str(exc).strip("'\"")
            message = f"TARGET_NOT_FOUND: {missing}"
            _write_ecosystem_error(proof_dir, message)
            print(message, file=sys.stderr)
            return 2
        except ValueError as exc:
            message = str(exc)
            _write_ecosystem_error(proof_dir, message)
            print(message, file=sys.stderr)
            return 2
        except Exception as exc:
            message = f"ERROR: {exc}"
            _write_ecosystem_error(proof_dir, message)
            print(message, file=sys.stderr)
            return 1

    configured = resolve_plan_context(
        repo_root,
        config_path,
        target=args.target,
        profile=args.profile,
    )
    selected_profile = str(configured.get("profile", args.profile or "debug"))
    resolution_out_dir = (repo_root / "build_graph" / selected_profile / "resolution").resolve()
    build_allowed, _artifact_map, resolution_payload = _run_target_resolution(
        repo_root=repo_root,
        configured=configured,
        resolution_out_dir=resolution_out_dir,
    )
    if not build_allowed:
        print(
            "TARGET_RESOLUTION_WARNING: "
            f"missing={len(resolution_payload.get('missing', []))} "
            f"conflicting={len(resolution_payload.get('conflicting', []))} "
            f"downgraded={len(resolution_payload.get('downgraded', []))}",
            file=sys.stderr,
        )
        print(f"Resolution report: {resolution_out_dir / '14_resolution_report.json'}", file=sys.stderr)

    out_path = repo_root / "build_graph" / selected_profile / "ngksbuildcore_plan.json"
    written, warnings = emit_buildcore_plan(repo_root, configured, out_path)
    print(f"BuildCore plan: {written}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    if args.freeze:
        print("freeze skipped: runtime build execution removed; use explicit capsule workflow")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1

    if getattr(args, "binary_only", False):
        print("RUN_BINARY_UNSUPPORTED: runtime build path removed; use external runner for binary execution")
        return 2

    selected_profile = str(args.profile or "debug")
    active_env = dict(os.environ)
    boot = bootstrap_msvc()
    if boot.success and boot.env:
        active_env = dict(boot.env)

    tool = resolve_msvc_toolchain_paths(active_env)
    tools = {"cl": tool.cl_path, "link": tool.link_path, "lib": tool.lib_path, "rc": tool.rc_path}
    missing = _first_missing_tool(tools)

    if missing is not None:
        name, path = missing
        print(f"MSVC_TOOL_MISSING: {name}.exe not found at {path or '<none>'}")
        return 1

    configured = resolve_plan_context(
        repo_root,
        config_path,
        target=args.target,
        profile=selected_profile,
    )
    out_path = repo_root / "build_graph" / selected_profile / "ngksbuildcore_plan.json"
    written, warnings = emit_buildcore_plan(repo_root, configured, out_path)
    print(f"BuildCore plan: {written}")
    if warnings:
        for warning in warnings:
            print(f"WARNING: {warning}")

    doctor_cmds = [
        [sys.executable, "-m", "ngksgraph", "doctor", "--project", str(repo_root), "--compdb", "--profile", selected_profile],
        [sys.executable, "-m", "ngksgraph", "doctor", "--project", str(repo_root), "--graph", "--profile", selected_profile],
        [sys.executable, "-m", "ngksgraph", "doctor", "--project", str(repo_root), "--profiles"],
    ]
    for cmd in doctor_cmds:
        dr = subprocess.run(cmd, cwd=repo_root, env=active_env, shell=False)
        if dr.returncode != 0:
            return dr.returncode

    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1
    clean_project(repo_root, config_path)
    print("Cleaned build directory.")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    mode = get_mode(args)
    if is_ecosystem(mode):
        repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None), require_config=False)
        if repo_root is None:
            return 1
        try:
            env_capsule_hash, _binding_kind, _binding_path = _resolve_env_capsule_binding(args, repo_root)
            configured = None
            if config_path is not None and config_path.exists():
                configured = resolve_plan_context(
                    repo_root,
                    config_path,
                    target=args.target,
                    profile=args.profile,
                )
        except KeyError as exc:
            missing = str(exc).strip("'\"")
            print(f"TARGET_NOT_FOUND: {missing}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        profile_name = str(configured.get("profile", args.profile or "debug")) if configured else str(args.profile or "debug")
        selected_target = str(configured["selected_target"]) if configured else str(args.target or "build")
        selected_graph = configured["graph"] if configured else None

        if configured is not None:
            if getattr(args, "pf", None):
                resolution_out_dir = (Path(str(args.pf)).resolve() / "graph_resolution").resolve()
            else:
                resolution_out_dir = (repo_root / "build_graph" / profile_name / "resolution").resolve()
            build_allowed, _artifact_map, resolution_payload = _run_target_resolution(
                repo_root=repo_root,
                configured=configured,
                resolution_out_dir=resolution_out_dir,
            )
            if not build_allowed:
                print(
                    "TARGET_RESOLUTION_BLOCKED: "
                    f"missing={len(resolution_payload.get('missing', []))} "
                    f"conflicting={len(resolution_payload.get('conflicting', []))} "
                    f"downgraded={len(resolution_payload.get('downgraded', []))}",
                    file=sys.stderr,
                )
                print(f"Resolution report: {resolution_out_dir / '14_resolution_report.json'}", file=sys.stderr)
                return 2

        plan = create_ecosystem_build_plan(
            repo_root,
            profile=profile_name,
            selected_target=selected_target,
            graph=selected_graph,
            env_capsule_hash=env_capsule_hash,
        )
        out_path, hash_path, _ = write_ecosystem_build_plan(repo_root, plan)
        print(f"Plan file: {out_path}")
        print(f"Plan hash: {hash_path}")
        return 0

    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1

    try:
        configured = resolve_plan_context(
            repo_root,
            config_path,
            target=args.target,
            profile=args.profile,
        )
    except KeyError as exc:
        missing = str(exc).strip("'\"")
        print(f"TARGET_NOT_FOUND: {missing}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if str(args.format).lower() != "json":
        print(f"Unsupported format: {args.format}", file=sys.stderr)
        return 2

    resolution_out_dir = (repo_root / "build_graph" / str(configured.get("profile", args.profile or "debug")) / "resolution").resolve()
    build_allowed, _artifact_map, resolution_payload = _run_target_resolution(
        repo_root=repo_root,
        configured=configured,
        resolution_out_dir=resolution_out_dir,
    )
    if not build_allowed:
        print(
            "TARGET_RESOLUTION_WARNING: "
            f"missing={len(resolution_payload.get('missing', []))} "
            f"conflicting={len(resolution_payload.get('conflicting', []))} "
            f"downgraded={len(resolution_payload.get('downgraded', []))}",
            file=sys.stderr,
        )
        print(f"Resolution report: {resolution_out_dir / '14_resolution_report.json'}", file=sys.stderr)

    out_path = emit_build_plan(repo_root, configured)
    print(f"Plan file: {out_path}")
    return 0


def cmd_buildplan(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1

    try:
        configured = resolve_plan_context(
            repo_root,
            config_path,
            target=args.target,
            profile=args.profile,
        )
    except KeyError as exc:
        missing = str(exc).strip("'\"")
        print(f"TARGET_NOT_FOUND: {missing}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    profile_name = str(configured.get("profile", args.profile or "debug"))
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
    else:
        out_path = (repo_root / "build_graph" / profile_name / "ngksbuildcore_plan.json").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    resolution_out_dir = (out_path.parent / "resolution").resolve()
    build_allowed, _artifact_map, resolution_payload = _run_target_resolution(
        repo_root=repo_root,
        configured=configured,
        resolution_out_dir=resolution_out_dir,
    )
    if not build_allowed:
        print(
            "TARGET_RESOLUTION_WARNING: "
            f"missing={len(resolution_payload.get('missing', []))} "
            f"conflicting={len(resolution_payload.get('conflicting', []))} "
            f"downgraded={len(resolution_payload.get('downgraded', []))}",
            file=sys.stderr,
        )
        print(f"Resolution report: {resolution_out_dir / '14_resolution_report.json'}", file=sys.stderr)

    written, warnings = emit_buildcore_plan(repo_root, configured, out_path)
    print(f"BuildCore plan file: {written}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


def cmd_planaudit(args: argparse.Namespace) -> int:
    repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
    if repo_root is None or config_path is None:
        return 1

    try:
        configured = resolve_plan_context(
            repo_root,
            config_path,
            target=args.target,
            profile=args.profile,
        )
    except KeyError as exc:
        missing = str(exc).strip("'\"")
        print(f"TARGET_NOT_FOUND: {missing}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload, warnings = create_buildcore_plan(
        repo_root,
        selected_target=str(configured["selected_target"]),
        graph=configured["graph"],
    )
    nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
    if not isinstance(nodes, list):
        print("ERROR: buildplan returned invalid nodes", file=sys.stderr)
        return 2

    node_ids = {str(n.get("id", "")) for n in nodes if isinstance(n, dict)}
    nodes_with_inputs = 0
    nodes_with_outputs = 0
    nodes_missing_outputs = 0
    nodes_with_no_deps = 0
    orphan_deps = 0

    output_owners: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        inputs = node.get("inputs", []) or []
        outputs = node.get("outputs", []) or []
        deps = node.get("deps", []) or []

        if isinstance(inputs, list) and len(inputs) > 0:
            nodes_with_inputs += 1
        if isinstance(outputs, list) and len(outputs) > 0:
            nodes_with_outputs += 1
        else:
            nodes_missing_outputs += 1
        if isinstance(deps, list) and len(deps) == 0:
            nodes_with_no_deps += 1

        if isinstance(deps, list):
            for dep in deps:
                if str(dep) not in node_ids:
                    orphan_deps += 1

        if isinstance(outputs, list):
            for out in outputs:
                output_owners.setdefault(str(out), []).append(node_id)

    duplicate_output_paths = sum(1 for owners in output_owners.values() if len(set(owners)) > 1)

    out_dir = (repo_root / "artifacts").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "plan_audit_report.json"
    txt_path = out_dir / "plan_audit_report.txt"

    report = {
        "total_nodes": len(nodes),
        "nodes_with_inputs": nodes_with_inputs,
        "nodes_with_outputs": nodes_with_outputs,
        "nodes_missing_outputs": nodes_missing_outputs,
        "duplicate_output_paths": duplicate_output_paths,
        "nodes_with_no_deps": nodes_with_no_deps,
        "orphan_deps": orphan_deps,
        "warnings": warnings,
        "target": str(configured["selected_target"]),
        "profile": str(configured.get("profile", args.profile or "debug")),
    }
    write_json(json_path, report)
    lines = [
        f"total_nodes={report['total_nodes']}",
        f"nodes_with_inputs={report['nodes_with_inputs']}",
        f"nodes_with_outputs={report['nodes_with_outputs']}",
        f"nodes_missing_outputs={report['nodes_missing_outputs']}",
        f"duplicate_output_paths={report['duplicate_output_paths']}",
        f"nodes_with_no_deps={report['nodes_with_no_deps']}",
        f"orphan_deps={report['orphan_deps']}",
    ]
    if warnings:
        lines.append("warnings=")
        lines.extend([f"- {w}" for w in warnings])
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Plan audit json: {json_path}")
    print(f"Plan audit txt: {txt_path}")
    print(f"duplicate_output_paths={duplicate_output_paths}")
    print(f"orphan_deps={orphan_deps}")

    if orphan_deps > 0 or duplicate_output_paths > 0:
        return 2
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    repo_root: Path | None = None
    config_path: Path | None = None
    needs_project_config = bool(args.toolchain or args.cache or args.profiles or args.compdb or args.graph)
    if needs_project_config:
        repo_root, config_path = _resolve_repo_and_config(getattr(args, "project", None))
        if repo_root is None or config_path is None:
            return 1

    if args.toolchain:
        try:
            ok, lines, corrupt = doctor_toolchain_report(config_path=config_path, profile=args.profile)
            for line in lines:
                print(line)
            if ok:
                print("PASS")
                return 0
            print("FAIL")
            return 2 if not corrupt else 2
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    if args.binary:
        try:
            exe_context = Path(sys.executable).resolve().parent
            result = inspect_binary_integrity(version_output=version_string(exe_context))
            if result.get("ok"):
                print("PASS")
                if result.get("note"):
                    print(f"NOTE={result.get('note')}")
                if result.get("exe_path"):
                    print(f"EXE={result.get('exe_path')}")
                return 0

            print("FAIL")
            print(f"ERROR={result.get('error', 'UNKNOWN')}")
            if result.get("exe_path"):
                print(f"EXE={result.get('exe_path')}")
            if result.get("manifest_path"):
                print(f"MANIFEST={result.get('manifest_path')}")
            if result.get("expected_hash"):
                print(f"EXPECTED_HASH={result.get('expected_hash')}")
            if result.get("actual_hash"):
                print(f"ACTUAL_HASH={result.get('actual_hash')}")
            if result.get("expected_version"):
                print(f"EXPECTED_VERSION={result.get('expected_version')}")
            if result.get("actual_version"):
                print(f"ACTUAL_VERSION={result.get('actual_version')}")
            return 2
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    if args.cache:
        try:
            cache = inspect_plan_cache(repo_root, config_path, profile=args.profile, target=None)
            print(f"CACHE={cache.get('cache', 'MISS')}")
            print(f"REASON={cache.get('reason', 'UNKNOWN')}")
            print(f"KEY_SHA={cache.get('key_sha', '')}")
            print(f"FINGERPRINT_SHA={cache.get('fingerprint_sha', '')}")
            if cache.get("corrupt"):
                return 2
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    if args.profiles:
        try:
            cfg = load_config(config_path)
            if not cfg.has_profiles():
                print("ERROR: No [profiles] configured in ngksgraph.toml")
                return 1

            profile_graphs: dict[str, object] = {}
            all_violations: list[dict[str, object]] = []

            for profile in cfg.profile_names():
                configured = configure_project(repo_root, config_path, msvc_auto=False, target=None, profile=profile)
                entries = load_compdb(configured["paths"]["compdb"])
                compdb_violations = validate_compdb(entries, configured["graph"], configured["config"])
                graph_violations = validate_graph_integrity(configured["graph"], configured["config"], configured["paths"]["out_dir"])

                for v in compdb_violations + graph_violations:
                    all_violations.append({"profile": profile, **v})
                profile_graphs[profile] = configured["graph"]

            profile_names = cfg.profile_names()
            if len(profile_names) >= 2:
                baseline = profile_names[0]
                base_graph = profile_graphs[baseline]
                for profile in profile_names[1:]:
                    for v in validate_profile_parity(base_graph, profile_graphs[profile]):
                        all_violations.append({"profile": f"{baseline} vs {profile}", **v})

            if all_violations:
                print("FAIL")
                for v in all_violations:
                    profile_part = f" profile={v.get('profile')}" if v.get("profile") else ""
                    target_part = f" target={v.get('target')}" if v.get("target") else ""
                    file_part = f" file={v.get('file')}" if v.get("file") else ""
                    path_part = f" path={v.get('path')}" if v.get("path") else ""
                    hint_part = f" hint={v.get('hint')}" if v.get("hint") else ""
                    print(f"- {v.get('code')}: {v.get('detail')}{profile_part}{target_part}{file_part}{path_part}{hint_part}")
                return 2

            print("PASS")
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    if args.compdb or args.graph:
        try:
            configured = configure_project(repo_root, config_path, msvc_auto=False, target=None, profile=args.profile)
            violations: list[dict[str, object]] = []

            if args.compdb:
                entries = load_compdb(configured["paths"]["compdb"])
                violations.extend(validate_compdb(entries, configured["graph"], configured["config"]))

            if args.graph:
                violations.extend(
                    validate_graph_integrity(
                        configured["graph"],
                        configured["config"],
                        configured["paths"]["out_dir"],
                    )
                )

            if violations:
                print("FAIL")
                for v in violations:
                    file_part = f" file={v.get('file')}" if v.get("file") else ""
                    path_part = f" path={v.get('path')}" if v.get("path") else ""
                    hint_part = f" hint={v.get('hint')}" if v.get("hint") else ""
                    target_part = f" target={v.get('target')}" if v.get("target") else ""
                    print(f"- {v.get('code')}: {v.get('detail')}{target_part}{file_part}{path_part}{hint_part}")
                return 2
            print("PASS")
            return 0
        except Exception as exc:
            print(f"ERROR: {exc}")
            return 1

    ok, lines = doctor_report(msvc_auto=args.msvc_auto)
    for line in lines:
        print(line)
    return 0 if ok else 1


def cmd_graph(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)
    payload, paths = load_graph_payload(repo_root, config_path, msvc_auto=False)

    out_path = Path(args.out) if args.out else paths["graph"]
    write_json(out_path, payload)

    if args.json:
        if args.pretty:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))

    if not args.quiet:
        targets_count = len(payload.get("targets", {}))
        edges_count = len(payload.get("edges", []))
        print(f"Graph targets: {targets_count}")
        print(f"Graph edges: {edges_count}")
        print(f"Graph file: {out_path}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)

    if args.link:
        result = explain_link(repo_root, config_path, target=args.target)
        if result.get("status") != "OK":
            print(result.get("status", "NO_TARGETS"))
            return 1
        print(f"Target: {result['target']}")
        print(f"Link Closure: {', '.join(result['link_closure'])}")
        print(f"Link Command: {result['link_command']}")
        return 0

    if not args.path:
        print("Path is required unless --link is used.")
        return 1

    result = explain_source(repo_root, config_path, args.path)
    if result.get("status") == "NOT_IN_GRAPH":
        print("NOT_IN_GRAPH")
        all_candidates = result.get("candidates", [])
        nearest = difflib.get_close_matches(args.path, all_candidates, n=5, cutoff=0.2)
        candidates = nearest if nearest else all_candidates[:5]
        if candidates:
            print("Nearest matches:")
            for item in candidates:
                print(f"  - {item}")
        return 1

    print(f"Target: {result['target']}")
    print(f"Object Path: {result['object_path']}")
    print(f"Compile Command: {result['compile_command']}")
    print(f"Includes: {', '.join(result['include_dirs'])}")
    print(f"Defines: {', '.join(result['defines'])}")
    print(f"Link Closure: {', '.join(result['link_closure'])}")
    print(f"Libs: {', '.join(result['libs'])}")
    repairs = result.get("repairs", [])
    print(f"Repairs Applied: {len(repairs)}")
    for repair in repairs:
        print(f"  - {repair}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)
    configured = configure_project(repo_root, config_path, msvc_auto=False, target=args.target)
    snapshots_root = configured["paths"]["out_dir"] / ".ngksgraph_snapshots"

    left = resolve_snapshot(snapshots_root, args.a, -2)
    right = resolve_snapshot(snapshots_root, args.b, -1)
    if left is None or right is None:
        print("Not enough snapshots. Run configure/build at least twice.")
        return 1

    diff_obj = structural_diff(left, right)

    if args.json:
        body = stable_diff_json(diff_obj)
        if args.out:
            Path(args.out).write_text(body, encoding="utf-8")
        print(body)
        return 0

    text = diff_to_text(diff_obj)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)

    if args.timing:
        cfg = load_config(config_path)
        selected_profile = cfg.apply_profile(args.profile)
        report_path = repo_root / cfg.out_dir / "ngksgraph_build_report.json"
        if not report_path.exists():
            print(f"Timing report not found: {report_path}")
            return 1
        report = json.loads(report_path.read_text(encoding="utf-8"))
        durations = report.get("durations", {}) if isinstance(report.get("durations", {}), dict) else {}
        order = [
            "load_config_ms",
            "scan_tree_ms",
            "qt_detect_ms",
            "plan_build_ms",
            "emit_plan_ms",
            "emit_compdb_ms",
            "validate_contracts_ms",
            "total_configure_ms",
            "build_handoff_ms",
            "total_build_ms",
        ]
        print(f"profile: {selected_profile}")
        print(f"cache_hit: {report.get('cache_hit', False)}")
        print(f"cache_reason: {report.get('cache_reason', '')}")
        for key in order:
            print(f"{key}: {durations.get(key)}")
        return 0

    if not args.path:
        print("Path is required unless --timing is used.")
        return 1

    result = trace_source(repo_root, config_path, args.path, profile=args.profile)

    if result.get("status") != "OK":
        print("NOT_IN_GRAPH")
        for candidate in result.get("candidates", [])[:5]:
            print(f"  - {candidate}")
        return 1

    if args.json:
        if args.pretty:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0

    print(f"Source: {result['source']}")
    print(f"Owners: {', '.join(result['owners'])}")
    print(f"Impacted targets: {', '.join(result['impacted_targets'])}")
    print(f"Impacted executables: {', '.join(result['impacted_executables'])}")
    for key in [
        "qt.moc.generated",
        "qt.moc.skipped",
        "qt.uic.generated",
        "qt.uic.skipped",
        "qt.rcc.generated",
        "qt.rcc.skipped",
        "qt.generator.reason",
        "qt.generator.tool_hash",
        "qt.include.injected",
        "qt.lib.injected",
    ]:
        if key in result:
            print(f"{key}: {result[key]}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)
    frozen = freeze_capsule(
        repo_root=repo_root,
        config_path=config_path,
        target=args.target,
        from_snapshot=args.from_snapshot,
        out=Path(args.out) if args.out else None,
        msvc_auto=args.msvc_auto,
        verify=args.verify,
        profile=args.profile,
    )
    print(f"Capsule: {frozen['capsule_path']}")
    return 0


def cmd_thaw(args: argparse.Namespace) -> int:
    capsule = Path(args.capsule)
    out_dir = Path(args.out_dir) if args.out_dir else (_repo_root_from_cwd() / "thawed_build")
    thawed = thaw_capsule(capsule_path=capsule, out_dir=out_dir, verify=args.verify, force=args.force)
    print(f"Thawed: {thawed['out_dir']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    capsule = Path(args.capsule)
    result = verify_capsule(capsule)
    if result["ok"]:
        print("PASS")
        return 0

    print("FAIL")
    for mismatch in result["mismatches"]:
        print(f"- {mismatch['component']}: expected={mismatch['expected']} actual={mismatch['actual']}")
    return 1


def cmd_why(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)
    result = why_target(
        repo_root=repo_root,
        config_path=config_path,
        target_name=args.target,
        from_snapshot=args.from_snapshot,
        from_capsule=Path(args.from_capsule) if args.from_capsule else None,
        profile=args.profile,
    )
    if args.json:
        if args.pretty:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        print(why_to_text(result))
    return 0


def cmd_rebuild_cause(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_cwd()
    config_path = _config_path(repo_root)
    result = rebuild_cause_target(
        repo_root=repo_root,
        config_path=config_path,
        target_name=args.target,
        from_snapshot=args.from_snapshot,
        from_capsule=Path(args.from_capsule) if args.from_capsule else None,
        profile=args.profile,
    )
    if args.json:
        if args.pretty:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    else:
        print(rebuild_cause_to_text(result))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    from ngksgraph.selftest import print_summary, run_selftest, write_report

    repo_root = _repo_root_from_cwd()
    if not bool(args.torture):
        print("Selftest currently supports only --torture mode.")
        return 1

    out_dir = Path(args.out) if args.out else _default_selftest_out(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        seeds = _parse_seed_range(args.seeds)
    except Exception as exc:
        print(f"Invalid --seeds value: {exc}")
        return 1

    if args.pytest:
        env = dict(os.environ)
        env["NGK_TORTURE_SCALE"] = str(args.scale)
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_qt_torture_abuse.py::test_qt_torture_scale_moc_many_headers",
            "tests/test_qt_torture_abuse.py::test_qt_torture_paths_with_spaces_and_mixed_slashes",
            "tests/test_qt_torture_abuse.py::test_qt_torture_tool_corruption_detected_by_capsule_verify",
            "tests/test_qt_torture_abuse.py::test_qt_torture_concurrency_parallel_configure_isolated",
        ]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, env=env, shell=False)
        report = {
            "phase": "6F",
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scale": int(args.scale),
            "seeds": list(seeds),
            "results": [
                {
                    "name": "pytest.curated_torture_subset",
                    "seed": list(seeds)[0] if list(seeds) else 0,
                    "pass": proc.returncode == 0,
                    "ms": 0,
                }
            ],
            "pass": proc.returncode == 0,
            "failures": [] if proc.returncode == 0 else [{"name": "pytest.curated_torture_subset", "seed": 0, "error": "pytest failure", "repro_path": ""}],
            "artifacts_dir": str(out_dir.resolve()),
            "version": {"ngksgraph": __version__, "python": sys.version.split()[0]},
        }
        logs_dir = out_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "pytest_stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (logs_dir / "pytest_stderr.log").write_text(proc.stderr or "", encoding="utf-8")
        report_path = write_report(report, out_dir)
        print_summary(report, json_only=bool(args.json_only), report_path=report_path)
        return 0 if proc.returncode == 0 else 2

    try:
        report = run_selftest(
            scale=int(args.scale),
            seeds=seeds,
            out_dir=out_dir,
            fail_fast=bool(args.fail_fast),
            timeout=int(args.timeout),
            keep=bool(args.keep),
            inject_corruption_failure=bool(args._inject_corruption_failure),
            profiles_mode=bool(args.profiles),
        )
        report_path = write_report(report, out_dir)
        print_summary(report, json_only=bool(args.json_only), report_path=report_path)
        return 0 if report.get("pass") else 2
    except Exception as exc:
        print(f"Selftest internal error: {exc}")
        return 1


def cmd_import(args: argparse.Namespace) -> int:
    if not args.cmake:
        print("import currently requires --cmake <path>")
        return 1

    repo_root = _repo_root_from_cwd()
    cmake_input = Path(args.cmake)
    cmake_path = cmake_input if cmake_input.is_absolute() else (repo_root / cmake_input)
    if cmake_path.is_dir():
        cmake_path = cmake_path / "CMakeLists.txt"
    if not cmake_path.exists():
        print(f"CMake file not found: {cmake_path}")
        return 1

    out_path = Path(args.out) if args.out else _config_path(repo_root)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    if out_path.exists() and not args.force:
        print(f"{out_path.name} already exists. Use --force to overwrite.")
        return 1

    written = import_cmake_project(cmake_path=cmake_path, out_path=out_path)
    print(f"Imported CMake project -> {written}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    repo_root = _resolve_project_root(getattr(args, "project", None))
    out_arg = getattr(args, "out", None)
    if out_arg:
        out_dir = Path(str(out_arg))
        if not out_dir.is_absolute():
            out_dir = (repo_root / out_dir).resolve()
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = (repo_root / "_artifacts" / "graph_scan" / stamp).resolve()

    result = run_scan(
        repo_root=repo_root,
        out_dir=out_dir,
        authority_mode=str(getattr(args, "authority_mode", "native_ngks") or "native_ngks"),
        bootstrap_venv=bool(getattr(args, "bootstrap_venv", False)),
        bootstrap_msvc_env=bool(getattr(args, "bootstrap_msvc_env", False)),
    )

    payload = {
        "status": result.status,
        "out_dir": str(result.out_dir),
        "blockers": list(result.blockers),
    }
    if bool(getattr(args, "json", False)):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Graph scan status: {result.status}")
        print(f"Graph scan output: {result.out_dir}")
        if result.blockers:
            for blocker in result.blockers:
                print(f"BLOCKER: {blocker}")

    return 2 if result.status == "FAIL_CLOSED" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ngksgraph")
    parser.add_argument("--version", action=_VersionAction, help="Print version stamp and exit")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create ngksgraph.toml from template")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--template", default="default", choices=["default", "basic", "qt-app", "multi-target"])
    p_init.set_defaults(func=cmd_init)

    p_import = sub.add_parser("import", help="Import project metadata into ngksgraph.toml")
    p_import.add_argument("--cmake", default=None)
    p_import.add_argument("--out", default=None)
    p_import.add_argument("--force", action="store_true", default=False)
    p_import.set_defaults(func=cmd_import)

    p_scan = sub.add_parser("scan", help="Run NGKsGraph repository intelligence scan and emit phase artifacts")
    p_scan.add_argument("--project", default=None)
    p_scan.add_argument("--out", default=None)
    p_scan.add_argument("--authority-mode", default="native_ngks", choices=["native_ngks", "import_foreign", "compatibility_only", "foreign_authoritative"])
    p_scan.add_argument("--bootstrap-venv", action="store_true", default=False)
    p_scan.add_argument("--bootstrap-msvc", dest="bootstrap_msvc_env", action="store_true", default=False)
    p_scan.add_argument("--json", action="store_true", default=False)
    p_scan.set_defaults(func=cmd_scan)

    p_cfg = sub.add_parser("configure", help="Scan and emit deterministic plan artifacts")
    p_cfg.add_argument("--msvc-auto", action="store_true", default=False)
    p_cfg.add_argument("--project", default=None)
    p_cfg.add_argument("--target", default=None)
    p_cfg.add_argument("--profile", default=None)
    p_cfg.add_argument("--no-cache", action="store_true", default=False)
    p_cfg.add_argument("--clear-cache", action="store_true", default=False)
    p_cfg.set_defaults(func=cmd_configure)

    p_build = sub.add_parser("build", help="Emit BuildCore-compatible plan artifacts")
    p_build.add_argument("--max-attempts", type=int, default=5)
    p_build.add_argument("--msvc-auto", action="store_true", default=False)
    p_build.add_argument("--project", default=None)
    p_build.add_argument("--target", default=None)
    p_build.add_argument("--profile", default=None)
    p_build.add_argument("--pf", default=None)
    p_build.add_argument("--mode", default=None, choices=["standalone", "ecosystem"])
    p_build.add_argument("--env-capsule-lock", default=None)
    p_build.add_argument("--env-capsule-hash", default=None)
    p_build.add_argument("--backend", default="none", choices=["none"])
    p_build.add_argument("--no-cache", action="store_true", default=False)
    p_build.add_argument("--clear-cache", action="store_true", default=False)
    p_build.add_argument("--freeze", action="store_true", default=False)
    p_build.add_argument("--freeze-out", default=None)
    p_build.add_argument("--freeze-verify", action="store_true", default=True)
    p_build.add_argument("--no-freeze-verify", dest="freeze_verify", action="store_false")
    p_build.set_defaults(func=cmd_build)

    p_plan = sub.add_parser("plan", help="Emit graph-native build plan JSON")
    p_plan.add_argument("--project", default=None)
    p_plan.add_argument("--target", default=None)
    p_plan.add_argument("--profile", default=None)
    p_plan.add_argument("--pf", default=None)
    p_plan.add_argument("--mode", default=None, choices=["standalone", "ecosystem"])
    p_plan.add_argument("--env-capsule-lock", default=None)
    p_plan.add_argument("--env-capsule-hash", default=None)
    p_plan.add_argument("--format", default="json", choices=["json"])
    p_plan.set_defaults(func=cmd_plan)

    p_buildplan = sub.add_parser("buildplan", help="Emit NGKsBuildCore-compatible plan JSON")
    p_buildplan.add_argument("--project", default=None)
    p_buildplan.add_argument("--target", default=None)
    p_buildplan.add_argument("--profile", default=None)
    p_buildplan.add_argument("--out", required=False, help="Output path for BuildCore plan (default: build_graph/<profile>/ngksbuildcore_plan.json)")
    p_buildplan.set_defaults(func=cmd_buildplan)

    p_planaudit = sub.add_parser("planaudit", help="Audit BuildCore plan I/O completeness and dependency validity")
    p_planaudit.add_argument("--project", default=None)
    p_planaudit.add_argument("--target", default=None)
    p_planaudit.add_argument("--profile", default=None)
    p_planaudit.set_defaults(func=cmd_planaudit)

    p_run = sub.add_parser("run", help="One-command plan emission + doctor runner")
    p_run.add_argument("--project", default=None)
    p_run.add_argument("--clear-cache", action="store_true", default=False)
    p_run.add_argument("--build-first", action="store_true", default=False)
    p_run.add_argument("--max-attempts", type=int, default=5)
    p_run.add_argument("--target", default=None)
    p_run.add_argument("--profile", default=None)
    p_run.add_argument("--binary-only", action="store_true", default=False)
    p_run.set_defaults(func=cmd_run)

    p_clean = sub.add_parser("clean", help="Remove output directory")
    p_clean.add_argument("--project", default=None)
    p_clean.set_defaults(func=cmd_clean)

    p_doctor = sub.add_parser("doctor", help="Check toolchain prerequisites")
    p_doctor.add_argument("--project", default=None)
    p_doctor.add_argument("--msvc-auto", action="store_true", default=False)
    p_doctor.add_argument("--compdb", action="store_true", default=False)
    p_doctor.add_argument("--graph", action="store_true", default=False)
    p_doctor.add_argument("--cache", action="store_true", default=False)
    p_doctor.add_argument("--binary", action="store_true", default=False)
    p_doctor.add_argument("--toolchain", action="store_true", default=False)
    p_doctor.add_argument("--profile", default=None)
    p_doctor.add_argument("--profiles", action="store_true", default=False)
    p_doctor.set_defaults(func=cmd_doctor)

    p_graph = sub.add_parser("graph", help="Export build graph as JSON")
    p_graph.add_argument("--json", action="store_true", default=True)
    p_graph.add_argument("--out", default=None)
    p_graph.add_argument("--pretty", action="store_true", default=True)
    p_graph.add_argument("--quiet", action="store_true", default=False)
    p_graph.set_defaults(func=cmd_graph)

    p_explain = sub.add_parser("explain", help="Explain source or link command")
    p_explain.add_argument("path", nargs="?")
    p_explain.add_argument("--link", action="store_true", default=False)
    p_explain.add_argument("--target", default=None)
    p_explain.set_defaults(func=cmd_explain)

    p_diff = sub.add_parser("diff", help="Diff two graph snapshots")
    p_diff.add_argument("--a", default=None)
    p_diff.add_argument("--b", default=None)
    p_diff.add_argument("--json", action="store_true", default=False)
    p_diff.add_argument("--out", default=None)
    p_diff.add_argument("--target", default=None)
    p_diff.set_defaults(func=cmd_diff)

    p_trace = sub.add_parser("trace", help="Trace impacted targets for a source file")
    p_trace.add_argument("path", nargs="?")
    p_trace.add_argument("--json", action="store_true", default=False)
    p_trace.add_argument("--pretty", action="store_true", default=True)
    p_trace.add_argument("--profile", choices=["debug", "release"], default=None)
    p_trace.add_argument("--timing", action="store_true", default=False)
    p_trace.set_defaults(func=cmd_trace)

    p_freeze = sub.add_parser("freeze", help="Create deterministic reproducibility capsule")
    p_freeze.add_argument("--target", default=None)
    p_freeze.add_argument("--from-snapshot", default=None)
    p_freeze.add_argument("--out", default=None)
    p_freeze.add_argument("--profile", choices=["debug", "release"], default=None)
    p_freeze.add_argument("--msvc-auto", action="store_true", default=False)
    p_freeze.add_argument("--verify", action="store_true", default=True)
    p_freeze.add_argument("--no-verify", dest="verify", action="store_false")
    p_freeze.set_defaults(func=cmd_freeze)

    p_thaw = sub.add_parser("thaw", help="Extract capsule outputs into a build directory")
    p_thaw.add_argument("capsule")
    p_thaw.add_argument("--out-dir", default=None)
    p_thaw.add_argument("--verify", action="store_true", default=True)
    p_thaw.add_argument("--no-verify", dest="verify", action="store_false")
    p_thaw.add_argument("--force", action="store_true", default=False)
    p_thaw.set_defaults(func=cmd_thaw)

    p_verify = sub.add_parser("verify", help="Verify capsule hashes")
    p_verify.add_argument("capsule")
    p_verify.set_defaults(func=cmd_verify)

    p_why = sub.add_parser("why", help="Explain target dependency/rebuild attribution")
    p_why.add_argument("target")
    p_why.add_argument("--json", action="store_true", default=False)
    p_why.add_argument("--pretty", action="store_true", default=True)
    p_why.add_argument("--from-snapshot", default=None)
    p_why.add_argument("--from-capsule", default=None)
    p_why.add_argument("--profile", choices=["debug", "release"], default=None)
    p_why.set_defaults(func=cmd_why)

    p_rc = sub.add_parser("rebuild-cause", help="Explain why target rebuilds")
    p_rc.add_argument("target")
    p_rc.add_argument("--json", action="store_true", default=False)
    p_rc.add_argument("--pretty", action="store_true", default=True)
    p_rc.add_argument("--from-snapshot", default=None)
    p_rc.add_argument("--from-capsule", default=None)
    p_rc.add_argument("--profile", choices=["debug", "release"], default=None)
    p_rc.set_defaults(func=cmd_rebuild_cause)

    p_selftest = sub.add_parser("selftest", help="Run curated deterministic torture selftest")
    p_selftest.set_defaults(torture=True)
    p_selftest.add_argument("--torture", action="store_true")
    p_selftest.add_argument("--no-torture", dest="torture", action="store_false")
    p_selftest.add_argument("--scale", type=int, default=200)
    p_selftest.add_argument("--seeds", default="1..5")
    p_selftest.add_argument("--out", default=None)
    p_selftest.add_argument("--json-only", action="store_true", default=False)
    p_selftest.add_argument("--fail-fast", action="store_true", default=False)
    p_selftest.add_argument("--pytest", action="store_true", default=False)
    p_selftest.add_argument("--profiles", action="store_true", default=False)
    p_selftest.add_argument("--timeout", type=int, default=300)
    p_selftest.add_argument("--keep", action="store_true", default=False)
    p_selftest.add_argument("--_inject-corruption-failure", dest="_inject_corruption_failure", action="store_true", default=False, help=argparse.SUPPRESS)
    p_selftest.set_defaults(func=cmd_selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else list(sys.argv[1:])
    repo_root = resolve_repo_root()
    proof = new_proof_run(repo_root)

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    command_text = "ngksgraph " + " ".join(args_list)

    (proof.run_dir / "command_line.txt").write_text(command_text + "\n", encoding="utf-8")
    (proof.run_dir / "python_path.txt").write_text((sys.executable or "") + "\n", encoding="utf-8")
    (proof.run_dir / "cwd.txt").write_text(str(Path.cwd().resolve()) + "\n", encoding="utf-8")

    stdout_log = proof.run_dir / "stdout.txt"
    stderr_log = proof.run_dir / "stderr.txt"

    exit_code = 1
    pending_exception: BaseException | None = None
    parser = build_parser()

    with stdout_log.open("w", encoding="utf-8") as stdout_file, stderr_log.open("w", encoding="utf-8") as stderr_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = TeeTextIO(original_stdout, stdout_file)
        sys.stderr = TeeTextIO(original_stderr, stderr_file)
        try:
            args = parser.parse_args(args_list)
            exit_code = int(args.func(args))
        except BaseException as exc:
            pending_exception = exc
            if isinstance(exc, SystemExit):
                if isinstance(exc.code, int):
                    exit_code = int(exc.code)
                elif exc.code is None:
                    exit_code = 0
                else:
                    exit_code = 1
            else:
                exit_code = 1
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr

    git_commit, _ = gather_git_metadata(repo_root, proof.run_dir)
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_summary(
        proof.run_dir,
        command=command_text,
        exit_code=exit_code,
        started_at=started,
        finished_at=finished,
        python_path=sys.executable or "",
        cwd=str(Path.cwd().resolve()),
        git_commit=git_commit,
    )
    zip_run(proof.run_dir, proof.zip_path)
    print(f"PROOF_ZIP={proof.zip_path}", file=sys.stderr)
    if pending_exception is not None:
        raise pending_exception
    return exit_code


class _VersionAction(argparse.Action):
    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(version_string(Path.cwd()))
        parser.exit()
