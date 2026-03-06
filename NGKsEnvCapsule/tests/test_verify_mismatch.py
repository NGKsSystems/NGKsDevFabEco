from pathlib import Path

from ngksenvcapsule.core.types import Candidate
from ngksenvcapsule.stablejson import write_stable_json
from ngksenvcapsule.verify import run as verify_run


class _Provider:
    def __init__(self, candidates):
        self._candidates = candidates

    def detect(self, host):
        return list(self._candidates)

    def verify(self, lock_facts, host):
        return False, "python version mismatch: expected 3.10.13"


def test_verify_mismatch_exit_code(tmp_path: Path) -> None:
    lock_payload = {
        "capsule_version": 1,
        "generated_utc": "2026-03-04T00:00:00Z",
        "host": {"os": "windows", "arch": "x64"},
        "toolchains": {},
        "runtimes": {"python": {"version": "3.10.13", "exe": "C:/Python310/python.exe"}},
    }
    lock_path = tmp_path / "env_capsule.lock.json"
    write_stable_json(lock_path, lock_payload)
    registry = {
        "python": _Provider([Candidate(id="python", version="3.13.5", meta={})]),
        "node": _Provider([]),
        "msvc": _Provider([]),
        "windows_sdk": _Provider([]),
    }
    rc = verify_run(str(lock_path), proof_root=tmp_path / "_proof", provider_registry=registry)
    assert rc == 4
