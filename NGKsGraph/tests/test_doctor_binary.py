from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ngksgraph.cli import main, version_string


def _write_fake_exe(path: Path, content: bytes = b"ngksgraph-binary") -> str:
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def test_doctor_binary_pass_without_manifest(tmp_path: Path, monkeypatch, capsys):
    fake_exe = tmp_path / "ngksgraph.exe"
    _write_fake_exe(fake_exe)

    monkeypatch.setattr("sys.executable", str(fake_exe))
    rc = main(["doctor", "--binary"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "PASS" in out
    assert "NOTE=MANIFEST_MISSING" in out


def test_doctor_binary_fail_on_hash_mismatch(tmp_path: Path, monkeypatch, capsys):
    fake_exe = tmp_path / "ngksgraph.exe"
    _write_fake_exe(fake_exe, b"binary-A")

    manifest = {
        "sha256_ngksgraph_exe": "0" * 64,
        "version_output": version_string(tmp_path),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr("sys.executable", str(fake_exe))
    rc = main(["doctor", "--binary"])
    out = capsys.readouterr().out

    assert rc == 2
    assert "FAIL" in out
    assert "ERROR=BINARY_HASH_MISMATCH" in out


def test_doctor_binary_pass_with_manifest(tmp_path: Path, monkeypatch, capsys):
    fake_exe = tmp_path / "ngksgraph.exe"
    actual_sha = _write_fake_exe(fake_exe, b"binary-B")

    manifest = {
        "sha256_ngksgraph_exe": actual_sha,
        "version_output": version_string(tmp_path),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr("sys.executable", str(fake_exe))
    rc = main(["doctor", "--binary"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "PASS" in out
    assert "NOTE=MANIFEST_VERIFIED" in out
