from __future__ import annotations

from pathlib import Path

from .config import load_config
from .core.constraints import parse_constraints_from_config
from .core.engine import build_host_context, resolve_capsule
from .core.errors import ConfigError, InternalError, MissingRequiredError
from .core.registry import get_default_registry
from .hashing import sha256_file, write_hash_file
from .install import handle_python_missing
from .proof import ProofSession, utc_now_iso
from .stablejson import write_stable_json


def run(
    config_path: str | None = None,
    auto_install: bool = False,
    out_json: str = "env_capsule.resolved.json",
    out_hash: str = "env_capsule.resolved.hash.txt",
    proof_root: Path = Path("_proof"),
    provider_registry: dict[str, object] | None = None,
) -> int:
    proof = ProofSession("resolve", ["ngksenvcapsule", "resolve"], Path.cwd(), root=proof_root)
    try:
        cfg = load_config(config_path)
        registry = provider_registry or get_default_registry()
        constraints = parse_constraints_from_config(cfg.to_dict())
        host = build_host_context()
        payload, selections, errors = resolve_capsule(
            constraints,
            registry,
            host,
            auto_provision=auto_install,
            proof_dir=str(proof.path),
        )
        payload["generated_utc"] = utc_now_iso()

        py_constraint = constraints.get("python")
        py_selection = selections.get("python")
        if py_constraint and py_constraint.strategy == "require" and py_selection and py_selection.status == "missing_required":
            required = py_constraint.version or ""
            ok, install_msg = handle_python_missing(required, auto_install)
            if not ok and install_msg:
                errors = [install_msg if err.startswith("Required runtime missing: Python") else err for err in errors]

        write_stable_json(out_json, payload)
        digest = sha256_file(out_json)
        write_hash_file(out_hash, digest)

        proof.write_inputs([
            f"config_path={cfg.path}",
            f"config_exists={cfg.exists}",
            f"auto_install={auto_install}",
        ])
        proof.add_output(out_json)
        proof.add_output(out_hash)
        proof.copy_artifact(out_json)
        proof.copy_artifact(out_hash)
        if errors:
            proof.write_error("resolve policy failure", MissingRequiredError("; ".join(errors)))
            for err in errors:
                print(err)
        proof.finalize()
        print(str(out_json))
        return 3 if errors else 0
    except ValueError as exc:
        proof.write_error("config invalid", ConfigError(str(exc)))
        proof.finalize()
        print(f"config invalid: {exc}")
        return 2
    except Exception as exc:
        proof.write_error("resolve failed", InternalError(str(exc)))
        proof.finalize()
        print(f"resolve failed: {exc}")
        return 10
