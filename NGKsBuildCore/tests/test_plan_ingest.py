from __future__ import annotations

import json
from pathlib import Path

from ngksbuildcore.plan import load_plan


def test_loads_graph_actions_schema(tmp_path: Path) -> None:
    plan_path = tmp_path / "graph_plan.json"
    payload = {
        "schema_version": "1.0",
        "actions": [
            {
                "id": "build",
                "deps": ["prep"],
                "inputs": ["src.txt"],
                "outputs": ["out.txt"],
                "argv": ["python", "-c", "print('ok')"],
                "cwd": ".",
                "type": "exec",
            },
            {
                "id": "prep",
                "deps": [],
                "inputs": [],
                "outputs": ["src.txt"],
                "argv": ["python", "-c", "print('prep')"],
            },
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    plan = load_plan(plan_path)

    assert len(plan.nodes) == 2
    node_by_id = {n.id: n for n in plan.nodes}
    assert node_by_id["build"].deps == ["prep"]
    assert node_by_id["build"].inputs == ["src.txt"]
    assert node_by_id["build"].outputs == ["out.txt"]
    assert node_by_id["build"].cmd == ["python", "-c", "print('ok')"]
    assert node_by_id["build"].cwd == "."


def test_loads_nodes_schema(tmp_path: Path) -> None:
    plan_path = tmp_path / "nodes_plan.json"
    payload = {
        "version": 1,
        "base_dir": ".",
        "nodes": [
            {
                "id": "prep",
                "deps": [],
                "inputs": [],
                "outputs": ["in.txt"],
                "cmd": "python -c \"from pathlib import Path; Path('in.txt').write_text('ok', encoding='utf-8')\"",
            },
            {
                "id": "build",
                "deps": ["prep"],
                "inputs": ["in.txt"],
                "outputs": ["out.txt"],
                "cmd": "python -c \"from pathlib import Path; Path('out.txt').write_text(Path('in.txt').read_text(encoding='utf-8'), encoding='utf-8')\"",
            },
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    plan = load_plan(plan_path)

    assert len(plan.nodes) == 2
    assert {n.id for n in plan.nodes} == {"prep", "build"}


def test_graph_native_plan_error_has_buildplan_hint(tmp_path: Path) -> None:
    plan_path = tmp_path / "graph_native_plan.json"
    payload = {
        "schema_version": 1,
        "targets": [
            {
                "name": "app",
                "steps": [],
            }
        ],
    }
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_plan(plan_path)
    except ValueError as exc:
        assert "ngksgraph buildplan" in str(exc)
    else:
        raise AssertionError("expected ValueError for graph-native plan payload")


