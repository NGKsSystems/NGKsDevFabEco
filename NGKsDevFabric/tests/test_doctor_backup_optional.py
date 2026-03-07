from __future__ import annotations

from pathlib import Path

from ngksdevfabric.ngk_fabric import main as fabric_main


def test_doctor_does_not_prompt_for_missing_backup(monkeypatch, tmp_path: Path) -> None:
    observed: dict[str, bool] = {}

    monkeypatch.setattr(fabric_main, "_resolve_project_root", lambda project_path: tmp_path)

    def _fake_resolve_backup_root(args, project_root, allow_prompt=False):
        del args, project_root
        observed["allow_prompt"] = bool(allow_prompt)
        return None

    monkeypatch.setattr(fabric_main, "_resolve_backup_root", _fake_resolve_backup_root)
    monkeypatch.setattr(fabric_main, "_resolve_pf", lambda args, project_root, prefix: tmp_path / "_proof" / "doctor_test")
    monkeypatch.setattr(fabric_main, "doctor_toolchain", lambda project_root, pf: 0)
    monkeypatch.setattr(fabric_main, "_mirror_docs_to_backup", lambda project_root, backup_root, pf: (_ for _ in ()).throw(AssertionError("mirror should not be called")))

    code = fabric_main.main(["doctor", str(tmp_path)])

    assert code == 0
    assert observed.get("allow_prompt") is False
