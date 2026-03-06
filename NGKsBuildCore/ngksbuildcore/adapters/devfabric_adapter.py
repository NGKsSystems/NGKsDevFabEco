from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..loggingx import EventLogger
from ..runner import make_proof_dir
from .graph_adapter import run_graph_plan


def build_from_manifest(manifest_path: str, jobs: int = 1, proof_dir: str | None = None) -> int:
    manifest_file = Path(manifest_path).resolve()
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))

    proof = make_proof_dir(proof_dir)
    logger = EventLogger(proof)
    try:
        logger.emit("DEVFABRIC_MANIFEST_LOAD_OK", manifest=str(manifest_file))
        plan_path = payload.get("plan_path")
        if plan_path:
            return run_graph_plan(plan_path=plan_path, jobs=jobs, proof_dir=proof_dir, extra_env={"NGKS_DEVFABRIC_MODE": "1"})

        graph_exe = os.environ.get("NGKS_GRAPH_EXE")
        if not graph_exe:
            logger.emit("GRAPH_NOT_FOUND", reason="NGKS_GRAPH_EXE not set and manifest has no plan_path")
            return 2

        graph_args = payload.get("graph_args", [])
        out_plan = payload.get("plan_out", str((manifest_file.parent / "generated_plan.json").resolve()))
        cmd = [graph_exe, *graph_args, "--out", out_plan]
        logger.emit("GRAPH_GENERATE_START", cmd=cmd)
        proc = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace")
        logger.emit("GRAPH_GENERATE_END", exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        if proc.returncode != 0:
            return proc.returncode

        return run_graph_plan(plan_path=out_plan, jobs=jobs, proof_dir=proof_dir, extra_env={"NGKS_DEVFABRIC_MODE": "1"})
    finally:
        logger.close()
