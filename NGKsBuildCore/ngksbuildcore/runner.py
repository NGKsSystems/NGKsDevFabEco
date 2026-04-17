from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .hashing import normalize_path
from .loggingx import EventLogger, utc_now_iso
from .plan import BuildPlan, PlanNode, load_plan
from .scheduler import build_graph, release_children, seed_ready
from .store import StateStore


# ---------------------------------------------------------------------------
# MSVC environment bootstrap
# ---------------------------------------------------------------------------

_VSWHERE = Path(
    r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
)
_VCVARS_CANDIDATES = [
    # VS 2026 (18.x)
    r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
    # VS 2022 (17.x)
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
    r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
]


def _find_vcvars64() -> Path | None:
    """Return the path to vcvars64.bat, using vswhere when available."""
    # 1. vswhere — authoritative, handles non-default install paths
    if _VSWHERE.exists():
        try:
            result = subprocess.run(
                [str(_VSWHERE), "-latest", "-property", "installationPath"],
                capture_output=True, text=True, timeout=10,
            )
            install = result.stdout.strip()
            if install:
                candidate = Path(install) / r"VC\Auxiliary\Build\vcvars64.bat"
                if candidate.exists():
                    return candidate
        except Exception:
            pass

    # 2. Well-known paths
    for path_str in _VCVARS_CANDIDATES:
        p = Path(path_str)
        if p.exists():
            return p

    return None


def _load_vcvars_into_env(vcvars: Path) -> bool:
    """
    Run vcvars64.bat in a cmd subprocess, capture the resulting environment,
    and merge all new/changed variables into the current process os.environ.
    Returns True on success.
    """
    try:
        # cmd.exe /c "vcvars64.bat && set" — captures the env after activation
        result = subprocess.run(
            ["cmd.exe", "/c", f'call "{vcvars}" > nul 2>&1 && set'],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()
        return True
    except Exception:
        return False


def _ensure_msvc_environment() -> None:
    """
    Guarantee cl.exe is on PATH before the DAG executor runs any compile task.

    Resolution order:
      1. cl.exe already on PATH (vcvars was called externally) — no-op.
      2. Auto-locate vcvars64.bat via vswhere / known paths and load it into
         the current process environment.
      3. If cl.exe still cannot be found, raise RuntimeError with a clear
         remediation message rather than letting task 1/N fail cryptically.
    """
    if shutil.which("cl") or shutil.which("cl.exe"):
        return  # already configured

    vcvars = _find_vcvars64()
    if vcvars and _load_vcvars_into_env(vcvars):
        if shutil.which("cl") or shutil.which("cl.exe"):
            print(f"[ngksbuildcore] MSVC environment loaded from: {vcvars}", flush=True)
            return

    # Still not found — fail fast with an actionable message
    raise RuntimeError(
        "cl.exe not found on PATH and ngksbuildcore could not auto-load the MSVC "
        "environment.\n\n"
        "Remediation options:\n"
        "  1. Run vcvars64.bat before invoking ngksbuildcore:\n"
        '     call "C:\\Program Files\\Microsoft Visual Studio\\<ver>\\<edition>\\'
        'VC\\Auxiliary\\Build\\vcvars64.bat"\n'
        "  2. Install Visual Studio with the 'Desktop development with C++' workload.\n"
        "  3. Ensure vswhere.exe is present at:\n"
        f"     {_VSWHERE}\n"
    )


@dataclass(slots=True)
class NodeResult:
    node_id: str
    status: str
    reason: str
    exit_code: int
    start_ts: str
    end_ts: str


def _resolve_paths(plan: BuildPlan, node: PlanNode) -> tuple[list[Path], list[Path], Path]:
    base_dir = plan.base_dir
    inputs = [normalize_path(p, base_dir) for p in node.inputs]
    outputs = [normalize_path(p, base_dir) for p in node.outputs]
    node_cwd = normalize_path(node.cwd, base_dir) if node.cwd else base_dir
    return inputs, outputs, node_cwd


def compute_action_key(plan: BuildPlan, node: PlanNode, env_capsule_hash: str) -> str:
    inputs, outputs, _ = _resolve_paths(plan, node)
    del outputs
    _, _, node_cwd = _resolve_paths(plan, node)

    missing = [str(p) for p in inputs if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing input file(s): {', '.join(missing)}")

    normalized_cmd = node.cmd if isinstance(node.cmd, list) else [node.cmd]
    cmd_joined = "\0".join(str(x) for x in normalized_cmd)
    env_rows = [f"{k}={v}" for k, v in sorted(node.env.items())]
    input_rows: list[str] = []
    for path in sorted(inputs, key=lambda p: str(p)):
        stat = path.stat()
        input_rows.append(f"{path}|{stat.st_mtime_ns}|{stat.st_size}")

    payload = {
        "env_capsule_hash": env_capsule_hash or "none",
        "cmd": cmd_joined,
        "cwd": str(node_cwd) if node.cwd else "",
        "env": env_rows,
        "inputs": input_rows,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def should_run(plan: BuildPlan, node: PlanNode, store: StateStore, env_capsule_hash: str) -> tuple[bool, str, str]:
    inputs, outputs, _ = _resolve_paths(plan, node)
    action_key = compute_action_key(plan, node, env_capsule_hash)
    prev_action_key = store.get_action_key(node.id)

    if outputs and any(not p.exists() for p in outputs):
        return True, "missing_output", action_key

    del inputs

    if outputs and prev_action_key and prev_action_key == action_key:
        return False, "action_key_match", action_key

    if outputs:
        return True, "action_key_miss", action_key

    return True, "no_outputs_declared", action_key


def _stream_pipe(pipe, logger: EventLogger, node_id: str, stream_type: str) -> None:
    for line in iter(pipe.readline, ""):
        text = line.rstrip("\r\n")
        logger.emit("NODE_STDOUT" if stream_type == "stdout" else "NODE_STDERR", node_id=node_id, line=text)
        if stream_type == "stderr":
            logger.print(f"[{node_id}][err] {text}")
        else:
            logger.print(f"[{node_id}] {text}")
    pipe.close()


def _ensure_output_parent_dirs(outputs: list[Path]) -> list[Path]:
    parents = {output.parent for output in outputs}
    created: list[Path] = []
    for parent in sorted(parents, key=lambda p: str(p)):
        if parent.exists():
            continue
        parent.mkdir(parents=True, exist_ok=True)
        created.append(parent)
    return created


def execute_node(plan: BuildPlan, node: PlanNode, logger: EventLogger) -> tuple[int, str, str]:
    inputs, outputs, node_cwd = _resolve_paths(plan, node)
    env = os.environ.copy()
    env.update(node.env)
    
    # Workaround for Qt license prompt hangs during compilation
    env["QTFRAMEWORK_BYPASS_LICENSE_CHECK"] = "1"

    start_ts = utc_now_iso()
    resolved_cmd = node.cmd
    if os.name == "nt" and isinstance(node.cmd, list) and node.cmd:
        # On Windows, CreateProcess may fail for list-form commands that rely on
        # PATHEXT resolution (e.g., flutter -> flutter.bat). Resolve explicitly.
        candidate = shutil.which(str(node.cmd[0]), path=env.get("PATH"))
        if candidate:
            resolved_cmd = [candidate, *node.cmd[1:]]
    logger.emit(
        "NODE_START",
        node_id=node.id,
        cwd=str(node_cwd),
        cmd=resolved_cmd,
        inputs=[str(p) for p in inputs],
        outputs=[str(p) for p in outputs],
        env_overrides=node.env,
    )
    logger.command(node_id=node.id, stage="start", start=start_ts, cwd=str(node_cwd), cmd=resolved_cmd)

    created_dirs = _ensure_output_parent_dirs(outputs)
    if created_dirs:
        logger.emit("NODE_OUTPUT_DIRS_READY", node_id=node.id, dirs=[str(path) for path in created_dirs])

    popen_kwargs = {
        "cwd": str(node_cwd),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }

    try:
        if isinstance(resolved_cmd, str):
            proc = subprocess.Popen(resolved_cmd, shell=True, **popen_kwargs)
        else:
            proc = subprocess.Popen(resolved_cmd, shell=False, **popen_kwargs)
    except OSError as exc:
        end_ts = utc_now_iso()
        logger.emit("NODE_EXEC_ERROR", node_id=node.id, error=str(exc), errno=getattr(exc, "errno", None))
        logger.print(f"[{node.id}][err] {exc}")
        logger.emit("NODE_END", node_id=node.id, exit_code=1, start=start_ts, end=end_ts)
        logger.command(node_id=node.id, stage="end", end=end_ts, exit_code=1)
        return 1, start_ts, end_ts

    t_out = threading.Thread(target=_stream_pipe, args=(proc.stdout, logger, node.id, "stdout"), daemon=True)
    t_err = threading.Thread(target=_stream_pipe, args=(proc.stderr, logger, node.id, "stderr"), daemon=True)
    t_out.start()
    t_err.start()
    exit_code = proc.wait()
    t_out.join()
    t_err.join()

    end_ts = utc_now_iso()
    logger.emit("NODE_END", node_id=node.id, exit_code=exit_code, start=start_ts, end=end_ts)
    logger.command(node_id=node.id, stage="end", end=end_ts, exit_code=exit_code)
    return exit_code, start_ts, end_ts


def make_proof_dir(requested_proof: str | None, env: dict[str, str] | None = None) -> Path:
    env_map = env or os.environ
    proof_root = requested_proof or env_map.get("NGKS_PROOF_ROOT") or "_proof"
    root = Path(proof_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    proof_dir = root / "run_build" / f"run_build_{ts}"
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir


def _write_summary(proof_dir: Path, payload: dict) -> None:
    (proof_dir / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    lines = [
        f"status: {payload['status']}",
        f"total_nodes: {payload['total_nodes']}",
        f"run_nodes: {payload['run_nodes']}",
        f"skipped_nodes: {payload['skipped_nodes']}",
        f"failed_nodes: {payload['failed_nodes']}",
        f"proof_dir: {proof_dir}",
    ]
    (proof_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_env_snapshot(proof_dir: Path) -> None:
    env_lines = [f"{k}={v}" for k, v in sorted(os.environ.items())]
    (proof_dir / "environment.txt").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    versions = []
    for cmd in (["python", "--version"], ["git", "--version"]):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            versions.append(f"{' '.join(cmd)} => {out.strip()}")
        except Exception as exc:
            versions.append(f"{' '.join(cmd)} => ERROR: {exc}")
    (proof_dir / "tool_versions.txt").write_text("\n".join(versions) + "\n", encoding="utf-8")
    try:
        status = subprocess.check_output(["git", "status", "--short", "--branch"], stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        status = f"ERROR: {exc}\n"
    (proof_dir / "git_status.txt").write_text(status, encoding="utf-8")
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        head = f"ERROR: {exc}\n"
    (proof_dir / "git_head.txt").write_text(head, encoding="utf-8")


def _write_input_records(
    proof_dir: Path,
    plan_path: Path,
    plan_sha256: str,
    env_lock_path: str,
    env_capsule_hash: str,
) -> None:
    (proof_dir / "inputs_env_capsule.txt").write_text(
        f"env_lock_path={env_lock_path}\nenv_capsule_hash={env_capsule_hash}\n",
        encoding="utf-8",
    )
    (proof_dir / "inputs_plan_hash.txt").write_text(
        f"plan_path={plan_path}\nplan_sha256={plan_sha256}\n",
        encoding="utf-8",
    )


def _mirror_easy_access(proof_dir: Path) -> None:
    try:
        easy_root = (Path.cwd().resolve() / "proofs").resolve()
        easy_root.mkdir(parents=True, exist_ok=True)
        latest_dir = easy_root / "latest_ngksbuildcore_run"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(proof_dir, latest_dir)
        (easy_root / "LATEST_NGKSBUILDCORE_PROOF_DIR.txt").write_text(str(proof_dir) + "\n", encoding="utf-8")
    except Exception:
        # Easy-access mirroring is best-effort only.
        pass


def run_build(
    plan_path: str,
    jobs: int = 1,
    proof: str | None = None,
    extra_env: dict[str, str] | None = None,
    env_lock: str | None = None,
) -> int:
    plan_file = Path(plan_path).resolve()
    plan_bytes = plan_file.read_bytes()
    plan_sha256 = hashlib.sha256(plan_bytes).hexdigest()

    if env_lock:
        env_lock_file = Path(env_lock).resolve()
        env_capsule_hash = hashlib.sha256(env_lock_file.read_bytes()).hexdigest()
        env_lock_record = str(env_lock_file)
    else:
        env_capsule_hash = "none"
        env_lock_record = "none"

    plan = load_plan(plan_file)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    _ensure_msvc_environment()
    env = os.environ.copy()  # re-snapshot after potential vcvars load
    if extra_env:
        env.update(extra_env)

    proof_dir = make_proof_dir(proof, env)
    console_verbose = env.get("NGKS_DEVFABRIC_MODE") != "1"
    logger = EventLogger(proof_dir, console_verbose=console_verbose)

    try:
        _write_env_snapshot(proof_dir)
        _write_input_records(proof_dir, plan_file, plan_sha256, env_lock_record, env_capsule_hash)
        logger.emit("PLAN_LOAD_OK", plan=str(plan.plan_path), base_dir=str(plan.base_dir), node_count=len(plan.nodes))

        store = StateStore(Path(".ngksbuildcore").resolve())
        graph = build_graph(plan.nodes)
        ready = seed_ready(graph.indegree)
        total_nodes = len(plan.nodes)

        in_flight: dict[Future[NodeResult], str] = {}
        completed: set[str] = set()
        failures: list[str] = []
        results: list[NodeResult] = []
        fail_fast = False

        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            logger.emit("BUILD_START", total_nodes=total_nodes, jobs=jobs)
            while len(completed) < total_nodes:
                # Report progress at key milestones
                progress_pct = int((len(completed) / total_nodes) * 100)
                if len(completed) % max(1, total_nodes // 20) == 0 or len(completed) == total_nodes:  # Every 5% or at completion
                    logger.emit("BUILD_PROGRESS", completed=len(completed), total=total_nodes, progress_pct=progress_pct)
                    logger.print(f"Build progress: {progress_pct}% ({len(completed)}/{total_nodes} tasks)")

                while ready and len(in_flight) < max(1, jobs) and not fail_fast:
                    node_id = ready.pop(0)
                    node = graph.nodes_by_id[node_id]
                    logger.emit("NODE_READY", node_id=node_id)

                    try:
                        will_run, reason, action_key = should_run(plan, node, store, env_capsule_hash)
                    except FileNotFoundError as exc:
                        now = utc_now_iso()
                        logger.emit("NODE_END", node_id=node_id, exit_code=1, start=now, end=now)
                        logger.print(f"[{node_id}][err] {exc}")
                        results.append(
                            NodeResult(node_id=node_id, status="FAIL", reason="missing_input", exit_code=1, start_ts=now, end_ts=now)
                        )
                        completed.add(node_id)
                        failures.append(node_id)
                        fail_fast = True
                        continue

                    if not will_run:
                        now = utc_now_iso()
                        logger.emit("NODE_SKIP", node_id=node_id, reason=reason)
                        results.append(NodeResult(node_id=node_id, status="SKIP", reason=reason, exit_code=0, start_ts=now, end_ts=now))
                        completed.add(node_id)
                        for child in release_children(node_id, graph.indegree, graph.children):
                            ready.append(child)
                        ready.sort()
                        continue

                    def _work(n: PlanNode = node, node_reason: str = reason, key: str = action_key) -> NodeResult:
                        exit_code, start_ts, end_ts = execute_node(plan, n, logger)
                        if exit_code == 0:
                            store.set_action_key(n.id, key, end_ts)
                        return NodeResult(
                            node_id=n.id,
                            status="RUN" if exit_code == 0 else "FAIL",
                            reason=node_reason,
                            exit_code=exit_code,
                            start_ts=start_ts,
                            end_ts=end_ts,
                        )

                    future = pool.submit(_work)
                    in_flight[future] = node_id

                if not in_flight:
                    if fail_fast:
                        break
                    if ready:
                        continue
                    break

                done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    node_id = in_flight.pop(future)
                    result = future.result()
                    results.append(result)
                    completed.add(node_id)
                    if result.exit_code != 0:
                        failures.append(node_id)
                        fail_fast = True
                    else:
                        for child in release_children(node_id, graph.indegree, graph.children):
                            ready.append(child)
                    ready.sort()

                    # Report progress after each node completion
                    progress_pct = int((len(completed) / total_nodes) * 100)
                    logger.emit("NODE_COMPLETE", node_id=node_id, completed=len(completed), total=total_nodes, progress_pct=progress_pct)

            if in_flight:
                done, _ = wait(in_flight.keys())
                for future in done:
                    result = future.result()
                    results.append(result)
                    completed.add(result.node_id)
                    if result.exit_code != 0:
                        failures.append(result.node_id)

                    # Report progress for final completions
                    progress_pct = int((len(completed) / total_nodes) * 100)
                    logger.emit("NODE_COMPLETE", node_id=result.node_id, completed=len(completed), total=total_nodes, progress_pct=progress_pct)

        status = "FAILED" if failures else "SUCCESS"
        final_progress_pct = 100 if not failures else int((len(completed) / total_nodes) * 100)
        summary = {
            "status": status,
            "plan": str(plan.plan_path),
            "proof_dir": str(proof_dir),
            "total_nodes": total_nodes,
            "run_nodes": sum(1 for r in results if r.status == "RUN"),
            "skipped_nodes": sum(1 for r in results if r.status == "SKIP"),
            "failed_nodes": sum(1 for r in results if r.status == "FAIL"),
            "progress_pct": final_progress_pct,
            "failures": failures,
            "results": [asdict(r) for r in sorted(results, key=lambda x: x.node_id)],
        }
        logger.emit("BUILD_END", status=status, progress_pct=final_progress_pct, failures=failures, summary=summary)
        logger.print(f"Build {status.lower()}: {final_progress_pct}% ({len(completed)}/{total_nodes} tasks)")
        _write_summary(proof_dir, summary)
        _mirror_easy_access(proof_dir)
        store.close()
        return 1 if failures else 0
    finally:
        logger.close()
