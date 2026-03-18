from __future__ import annotations

import zipfile
from pathlib import Path

import ngksgraph.proof as proof_module
from ngksgraph.proof import new_proof_run, resolve_repo_root, zip_run


def test_resolve_repo_root_prefers_cwd_project_root(tmp_path, monkeypatch):
    repo = Path(tmp_path) / "repo"
    nested = repo / "a" / "b"
    nested.mkdir(parents=True, exist_ok=True)
    (repo / "ngksgraph.toml").write_text("name = \"app\"\n", encoding="utf-8")

    monkeypatch.chdir(nested)
    assert resolve_repo_root() == repo.resolve()


def test_proof_location_ignores_package_install_path(tmp_path, monkeypatch):
    repo = Path(tmp_path) / "repo"
    nested = repo / "src" / "ui"
    nested.mkdir(parents=True, exist_ok=True)
    (repo / "ngksgraph.toml").write_text("name = \"app\"\n", encoding="utf-8")

    fake_site_packages = tmp_path / "venv" / "Lib" / "site-packages" / "ngksgraph" / "proof.py"
    monkeypatch.setattr(proof_module, "__file__", str(fake_site_packages))
    monkeypatch.chdir(nested)

    proof = new_proof_run(resolve_repo_root())
    (proof.run_dir / "marker.txt").write_text("ok\n", encoding="utf-8")
    zip_run(proof.run_dir, proof.zip_path)

    assert proof.zip_path.parent == (repo / "_proof").resolve()
    with zipfile.ZipFile(proof.zip_path, mode="r") as zf:
        assert "marker.txt" in zf.namelist()
