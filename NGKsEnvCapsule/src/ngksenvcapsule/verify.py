from __future__ import annotations

import json
from pathlib import Path

from .core.engine import build_host_context, verify_capsule
from .core.errors import ConfigError, InternalError, VerifyFailedError
from .core.registry import get_default_registry
from .capsule_schema import validate_capsule
from .proof import ProofSession


def verify_payload(lock_payload: dict, provider_registry: dict[str, object] | None = None) -> tuple[bool, list[str]]:
    registry = provider_registry or get_default_registry()
    host = build_host_context()
    return verify_capsule(lock_payload, registry, host)


def run(
    lock_path: str = "env_capsule.lock.json",
    proof_root: Path = Path("_proof"),
    provider_registry: dict[str, object] | None = None,
) -> int:
    proof = ProofSession("verify", ["ngksenvcapsule", "verify"], Path.cwd(), root=proof_root)
    try:
        lock_payload = json.loads(Path(lock_path).read_text(encoding="utf-8"))
        validate_capsule(lock_payload)
        ok, errors = verify_payload(lock_payload, provider_registry=provider_registry)

        proof.write_inputs([f"lock_path={lock_path}"])
        if ok:
            proof.add_output("verify=ok")
            proof.finalize()
            print("verify ok")
            return 0

        proof.write_error("verify failed", VerifyFailedError("; ".join(errors)))
        proof.finalize()
        for err in errors:
            print(err)
        return 4
    except ValueError as exc:
        proof.write_error("config invalid", ConfigError(str(exc)))
        proof.finalize()
        print(f"verify input invalid: {exc}")
        return 2
    except Exception as exc:
        proof.write_error("verify failed", InternalError(str(exc)))
        proof.finalize()
        print(f"verify failed: {exc}")
        return 10
