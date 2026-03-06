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


