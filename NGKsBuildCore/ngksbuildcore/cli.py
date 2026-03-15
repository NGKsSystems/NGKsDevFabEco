from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .plan import load_plan
from .runner import make_proof_dir, run_build


def _allow_direct_buildcore() -> bool:
    return os.environ.get("NGKS_ALLOW_DIRECT_BUILDCORE", "").strip() == "1"


def _route_to_devfabeco_pipeline(plan_path: str, proof_root: str | None) -> int:
    plan = Path(plan_path).resolve()
    project_root = plan.parent.resolve()
    command = [
        sys.executable,
        "-m",
        "ngksdevfabric",
        "build",
        str(project_root),
    ]
    if proof_root:
        command.extend(["--pf", str(proof_root)])
    print("BuildCore direct run intercepted: delegating to DevFabEco orchestrator")
    proc = subprocess.run(command, check=False)
    return int(proc.returncode)


def _default_jobs(value: int | None) -> int:
    if value is not None:
        return value
    env_value = os.environ.get("NGKS_BUILD_JOBS")
    if env_value and env_value.isdigit():
        return max(1, int(env_value))
    return 1


def _doctor(proof: str | None) -> int:
    proof_dir = make_proof_dir(proof)
    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 9)
    checks.append(("python_version", py_ok, sys.version.split()[0]))

    state_dir = Path(".ngksbuildcore")
    proof_root = Path("_proof")
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        test_file = state_dir / "_write_test.tmp"
        test_file.write_text("ok\n", encoding="utf-8")
        test_file.unlink()
        state_ok = True
        state_msg = "writable"
    except Exception as exc:
        state_ok = False
        state_msg = str(exc)
    checks.append(("state_dir_write", state_ok, state_msg))

    try:
        proof_root.mkdir(parents=True, exist_ok=True)
        test_file = proof_root / "_write_test.tmp"
        test_file.write_text("ok\n", encoding="utf-8")
        test_file.unlink()
        proof_ok = True
        proof_msg = "writable"
    except Exception as exc:
        proof_ok = False
        proof_msg = str(exc)
    checks.append(("proof_root_write", proof_ok, proof_msg))

    try:
        proc = subprocess.run(
            [sys.executable, "-c", "print('SPAWN_OK')"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        spawn_ok = "SPAWN_OK" in proc.stdout
        spawn_msg = proc.stdout.strip()
    except Exception as exc:
        spawn_ok = False
        spawn_msg = str(exc)
    checks.append(("process_spawn", spawn_ok, spawn_msg))

    passed = all(item[1] for item in checks)
    result = {
        "status": "PASS" if passed else "FAIL",
        "proof_dir": str(proof_dir),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }
    (proof_dir / "doctor.json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    report_lines = [f"doctor: {result['status']}"] + [f"- {n}: {'PASS' if ok else 'FAIL'} ({d})" for n, ok, d in checks]
    text = "\n".join(report_lines) + "\n"
    (proof_dir / "doctor.txt").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if passed else 1


def _explain(plan_path: str, node_id: str | None) -> int:
    plan = load_plan(plan_path)
    if node_id is None:
        print(f"plan: {plan.plan_path}")
        print(f"base_dir: {plan.base_dir}")
        print(f"nodes: {len(plan.nodes)}")
        for n in sorted(plan.nodes, key=lambda x: x.id):
            print(f"- {n.id}: deps={n.deps} inputs={len(n.inputs)} outputs={len(n.outputs)}")
        return 0

    found = None
    for n in plan.nodes:
        if n.id == node_id:
            found = n
            break
    if not found:
        print(f"node not found: {node_id}")
        return 1

    print(json.dumps(
        {
            "id": found.id,
            "desc": found.desc,
            "cwd": found.cwd,
            "cmd": found.cmd,
            "deps": found.deps,
            "inputs": found.inputs,
            "outputs": found.outputs,
            "env": found.env,
        },
        indent=2,
        ensure_ascii=True,
    ))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ngksbuildcore", description="NGKsBuildCore MVP build runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run a build plan DAG")
    run_cmd.add_argument("--plan", required=True, help="Path to plan json")
    run_cmd.add_argument("--env-lock", default=None, help="Path to env_capsule.lock.json")
    run_cmd.add_argument("-j", "--jobs", type=int, default=None, help="Parallel jobs")
    run_cmd.add_argument("--proof", default=None, help="Proof root directory override")
    run_cmd.add_argument("--pf", default=None, help="Proof root directory override (alias of --proof)")

    doctor_cmd = sub.add_parser("doctor", help="Environment diagnostics")
    doctor_cmd.add_argument("--proof", default=None, help="Proof root directory override")
    doctor_cmd.add_argument("--pf", default=None, help="Proof root directory override (alias of --proof)")

    explain_cmd = sub.add_parser("explain", help="Explain plan or node")
    explain_cmd.add_argument("--plan", required=True, help="Path to plan json")
    explain_cmd.add_argument("--node", default=None, help="Optional node id")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if not _allow_direct_buildcore():
            proof_root = args.pf or args.proof
            return _route_to_devfabeco_pipeline(args.plan, proof_root)
        jobs = _default_jobs(args.jobs)
        proof_root = args.pf or args.proof
        return run_build(plan_path=args.plan, jobs=jobs, proof=proof_root, env_lock=args.env_lock)
    if args.command == "doctor":
        proof_root = args.pf or args.proof
        return _doctor(proof_root)
    if args.command == "explain":
        return _explain(args.plan, args.node)

    parser.print_help()
    return 1
