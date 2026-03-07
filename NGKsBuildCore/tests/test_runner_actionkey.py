from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from ngksbuildcore.runner import run_build


def _latest_run_dir(proof_root: Path) -> Path:
    return sorted((proof_root / "run_build").glob("run_build_*"))[-1]


def _write_graph_plan(plan_path: Path, cmd_body: str, input_name: str = "in.txt") -> None:
    payload = {
        "schema_version": "1.0",
        "actions": [
            {
                "id": "a",
                "deps": [],
                "inputs": [input_name],
                "outputs": ["out.txt"],
                "argv": [sys.executable, "-c", cmd_body],
            }
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")


def test_env_lock_hash_and_plan_hash_proof_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "plan.json"
    input_file = tmp_path / "in.txt"
    input_file.write_text("hello\n", encoding="utf-8")

    cmd = "from pathlib import Path; d=Path('in.txt').read_text(encoding='utf-8'); Path('out.txt').write_text(d, encoding='utf-8')"
    _write_graph_plan(plan_path, cmd)

    env_lock = tmp_path / "env_capsule.lock.json"
    env_bytes = b'{"python":"3.12"}\n'
    env_lock.write_bytes(env_bytes)

    proof_root = tmp_path / "proof"
    code = run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root), env_lock=str(env_lock))
    assert code == 0

    run_dir = _latest_run_dir(proof_root)
    env_record = (run_dir / "inputs_env_capsule.txt").read_text(encoding="utf-8")
    plan_record = (run_dir / "inputs_plan_hash.txt").read_text(encoding="utf-8")

    assert f"env_lock_path={env_lock.resolve()}" in env_record
    assert f"env_capsule_hash={hashlib.sha256(env_bytes).hexdigest()}" in env_record

    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    assert f"plan_path={plan_path.resolve()}" in plan_record
    assert f"plan_sha256={plan_hash}" in plan_record


def test_action_key_skip_and_rerun_on_cmd_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "plan.json"
    (tmp_path / "in.txt").write_text("v1\n", encoding="utf-8")
    proof_root = tmp_path / "proof"

    cmd_v1 = "from pathlib import Path; d=Path('in.txt').read_text(encoding='utf-8'); Path('out.txt').write_text('A:'+d, encoding='utf-8')"
    _write_graph_plan(plan_path, cmd_v1)

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    run1 = _latest_run_dir(proof_root)
    summary1 = json.loads((run1 / "summary.json").read_text(encoding="utf-8"))
    assert summary1["run_nodes"] == 1
    assert summary1["skipped_nodes"] == 0

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    run2 = _latest_run_dir(proof_root)
    summary2 = json.loads((run2 / "summary.json").read_text(encoding="utf-8"))
    assert summary2["run_nodes"] == 0
    assert summary2["skipped_nodes"] == 1

    cmd_v2 = "from pathlib import Path; d=Path('in.txt').read_text(encoding='utf-8'); Path('out.txt').write_text('B:'+d, encoding='utf-8')"
    _write_graph_plan(plan_path, cmd_v2)

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    run3 = _latest_run_dir(proof_root)
    summary3 = json.loads((run3 / "summary.json").read_text(encoding="utf-8"))
    assert summary3["run_nodes"] == 1
    assert summary3["skipped_nodes"] == 0


def test_run_build_accepts_nodes_schema_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "nodes_plan.json"
    proof_root = tmp_path / "proof"

    payload = {
        "version": 1,
        "base_dir": ".",
        "nodes": [
            {
                "id": "prep",
                "deps": [],
                "inputs": [],
                "outputs": ["in.txt"],
                "cmd": f'"{sys.executable}" -c "from pathlib import Path; Path(\'in.txt\').write_text(\'ok\\n\', encoding=\'utf-8\')"',
            },
            {
                "id": "build",
                "deps": ["prep"],
                "inputs": ["in.txt"],
                "outputs": ["out.txt"],
                "cmd": f'"{sys.executable}" -c "from pathlib import Path; Path(\'out.txt\').write_text(Path(\'in.txt\').read_text(encoding=\'utf-8\'), encoding=\'utf-8\')"',
            },
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    assert (tmp_path / "out.txt").exists()


def test_runner_creates_output_parent_dirs_before_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "plan_parent_dirs.json"
    proof_root = tmp_path / "proof"

    payload = {
        "schema_version": "1.0",
        "actions": [
            {
                "id": "a",
                "deps": [],
                "inputs": [],
                "outputs": ["build/debug/obj/engine/ui/check.obj"],
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; p=Path('build/debug/obj/engine/ui/check.obj'); "
                    "assert p.parent.exists(); p.write_text('ok', encoding='utf-8')",
                ],
            }
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    assert (tmp_path / "build" / "debug" / "obj" / "engine" / "ui" / "check.obj").exists()


def test_compile_style_obj_output_runs_without_precreated_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "plan_compile_style.json"
    proof_root = tmp_path / "proof"

    payload = {
        "version": 1,
        "base_dir": ".",
        "nodes": [
            {
                "id": "compile",
                "deps": [],
                "inputs": [],
                "outputs": ["build/debug/obj/engine/ui/button.obj"],
                "cmd": (
                    f'"{sys.executable}" -c "from pathlib import Path; '
                    "p=Path('build/debug/obj/engine/ui/button.obj'); "
                    "p.write_bytes(b'OBJ')\""
                ),
            }
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    assert run_build(plan_path=str(plan_path), jobs=1, proof=str(proof_root)) == 0
    assert (tmp_path / "build" / "debug" / "obj" / "engine" / "ui" / "button.obj").read_bytes() == b"OBJ"
