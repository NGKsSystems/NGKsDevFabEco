from __future__ import annotations

from pathlib import Path

from ngksdevfabric.ngk_fabric import main as fabric_main
from ngksdevfabric.ngk_fabric.component_exec import ComponentResolutionError


def _latest_run_dir(project: Path) -> Path:
    roots = sorted((project / "_proof").glob("devfabric_run_run_*"))
    assert roots, "expected at least one run proof folder"
    return roots[-1]


def test_orchestrator_writes_stage_logs_when_component_missing(monkeypatch, tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name":"app","scripts":{"smoke":"node app.js"}}\n', encoding="utf-8")

    def _raise_missing(component_name: str, module_name: str):
        raise ComponentResolutionError(component_name=component_name, module_name=module_name)

    monkeypatch.setattr(fabric_main, "resolve_component_cmd", _raise_missing)

    code = fabric_main.main(["run", "--project", str(tmp_path), "--mode", "ecosystem"])

    assert code == 2
    run_dir = _latest_run_dir(tmp_path)
    env_stage = run_dir / "10_envcapsule"
    assert (env_stage / "00_resolve.txt").exists()
    assert (env_stage / "02_stderr.txt").exists()
    assert (env_stage / "03_exit_code.txt").exists()

    root_error = run_dir / "30_errors.txt"
    assert root_error.exists()
    text = root_error.read_text(encoding="utf-8")
    assert "class=tool_missing" in text
    assert "stage=10_envcapsule" in text
    assert "exit_code=2" in text
    assert "snippet_start" in text
    assert "snippet_end" in text

    summary = run_dir / "99_summary.txt"
    assert summary.exists()
    summary_text = summary.read_text(encoding="utf-8")
    assert "env_capsule_hash_reason=tool_missing" in summary_text
    assert "build_plan_hash_reason=skipped_due_to_precondition" in summary_text
