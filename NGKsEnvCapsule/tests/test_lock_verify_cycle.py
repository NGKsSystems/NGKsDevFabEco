import json
from pathlib import Path

from ngksenvcapsule.core.types import Candidate
from ngksenvcapsule.lock import run as lock_run
from ngksenvcapsule.stablejson import write_stable_json
from ngksenvcapsule.verify import verify_payload


class _Provider:
    def __init__(self, candidates):
        self._candidates = candidates

    def detect(self, host):
        return list(self._candidates)

    def verify(self, lock_facts, host):
        for c in self._candidates:
            if c.version == lock_facts.get("version"):
                return True, ""
        return False, "mismatch"


def test_lock_and_verify_cycle(tmp_path: Path) -> None:
    resolved = {
        "capsule_version": 1,
        "generated_utc": "2026-03-04T00:00:00Z",
        "host": {"os": "windows", "arch": "x64"},
        "toolchains": {},
        "runtimes": {"python": {"version": "3.10.13", "exe": "C:/Python310/python.exe"}},
    }
    resolved_path = tmp_path / "env_capsule.resolved.json"
    write_stable_json(resolved_path, resolved)
    rc = lock_run(str(resolved_path), str(tmp_path / "env_capsule.lock.json"), str(tmp_path / "env_capsule.hash.txt"), proof_root=tmp_path / "_proof")
    assert rc == 0

    lock_payload = json.loads((tmp_path / "env_capsule.lock.json").read_text(encoding="utf-8"))
    registry = {
        "python": _Provider([Candidate(id="python", version="3.10.13", meta={})]),
        "node": _Provider([]),
        "msvc": _Provider([]),
        "windows_sdk": _Provider([]),
    }
    ok, errors = verify_payload(lock_payload, provider_registry=registry)
    assert ok
    assert errors == []
