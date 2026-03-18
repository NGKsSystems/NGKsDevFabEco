from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import zipfile

from ngksgraph import cli as graph_cli
import ngksgraph.proof as proof_module
from ngksgraph.proof import activate_proof_run, clear_active_proof_run, new_proof_run, zip_run


class _FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 3, 18, 7, 0, 0, tzinfo=tz or timezone.utc)


def test_successful_proof_run_leaves_only_zip_in_app_local_proof(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    proof = new_proof_run(repo)
    (proof.run_dir / "artifact.txt").write_text("payload\n", encoding="utf-8")

    zip_run(proof.run_dir, proof.zip_path)

    proof_root = (repo / "_proof").resolve()
    assert proof.zip_path.parent == proof_root
    assert proof.zip_path.exists()
    assert not proof.run_dir.exists()
    assert [path.name for path in proof_root.iterdir() if path.is_dir()] == []
    with zipfile.ZipFile(proof.zip_path, mode="r") as zf:
        assert "artifact.txt" in zf.namelist()


def test_component_proof_dir_uses_active_work_dir_and_is_cleaned(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    proof = new_proof_run(repo)
    activate_proof_run(proof.run_dir)
    try:
        component_dir = graph_cli._new_component_proof_dir(repo)
    finally:
        clear_active_proof_run()

    (component_dir / "artifact.txt").write_text("payload\n", encoding="utf-8")
    zip_run(proof.run_dir, proof.zip_path)

    assert component_dir.parent == proof.run_dir
    assert not component_dir.exists()
    assert [path.name for path in ((repo / "_proof").resolve()).iterdir() if path.is_dir()] == []


def test_multiple_runs_create_multiple_zip_files_without_run_folders(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(proof_module, "datetime", _FixedDateTime)

    proof_one = new_proof_run(repo)
    (proof_one.run_dir / "one.txt").write_text("one\n", encoding="utf-8")
    zip_run(proof_one.run_dir, proof_one.zip_path)

    proof_two = new_proof_run(repo)
    (proof_two.run_dir / "two.txt").write_text("two\n", encoding="utf-8")
    zip_run(proof_two.run_dir, proof_two.zip_path)

    proof_root = (repo / "_proof").resolve()
    zip_names = sorted(path.name for path in proof_root.iterdir() if path.is_file())
    assert zip_names == ["run_20260318_070000.zip", "run_20260318_070000_01.zip"]
    assert [path.name for path in proof_root.iterdir() if path.is_dir()] == []