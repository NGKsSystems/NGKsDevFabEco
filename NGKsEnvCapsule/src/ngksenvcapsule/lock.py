from __future__ import annotations

import json
from pathlib import Path

from .capsule_schema import validate_capsule
from .hashing import sha256_file, write_hash_file
from .proof import ProofSession
from .stablejson import write_stable_json


def run(
    in_path: str = "env_capsule.resolved.json",
    out_path: str = "env_capsule.lock.json",
    out_hash: str = "env_capsule.hash.txt",
    proof_root: Path = Path("_proof"),
) -> int:
    proof = ProofSession("lock", ["ngksenvcapsule", "lock"], Path.cwd(), root=proof_root)
    try:
        resolved = json.loads(Path(in_path).read_text(encoding="utf-8"))
        validate_capsule(resolved)
        write_stable_json(out_path, resolved)
        digest = sha256_file(out_path)
        write_hash_file(out_hash, digest)

        proof.write_inputs([f"resolved_in={in_path}"])
        proof.add_output(out_path)
        proof.add_output(out_hash)
        proof.copy_artifact(out_path)
        proof.copy_artifact(out_hash)
        proof.finalize()
        print(str(out_path))
        return 0
    except ValueError as exc:
        proof.write_error("config invalid", exc)
        proof.finalize()
        print(f"lock input invalid: {exc}")
        return 2
    except Exception as exc:
        proof.write_error("lock failed", exc)
        proof.finalize()
        print(f"lock failed: {exc}")
        return 10
