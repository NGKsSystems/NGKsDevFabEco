from __future__ import annotations

from typing import Mapping

from ..runner import run_build


def run_graph_plan(plan_path: str, jobs: int = 1, proof_dir: str | None = None, extra_env: Mapping[str, str] | None = None) -> int:
    env = dict(extra_env or {})
    return run_build(plan_path=plan_path, jobs=jobs, proof=proof_dir, extra_env=env)
