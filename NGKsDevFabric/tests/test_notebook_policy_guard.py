from __future__ import annotations

from pathlib import Path

from ngksdevfabric.ngk_fabric import main as fabric_main


def test_notebook_policy_blocks_core_command(tmp_path: Path):
    code = fabric_main.main(
        [
            "explain",
            "rebuild",
            "--project-path",
            str(tmp_path),
            "--pf",
            "forbidden_notebook.ipynb",
        ]
    )

    assert code == 2
    violations = list((tmp_path / "_proof" / "policy_violations").glob("notebook_policy_violation_*.json"))
    assert violations
