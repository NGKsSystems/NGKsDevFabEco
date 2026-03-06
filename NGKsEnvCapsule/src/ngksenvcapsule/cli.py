from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import doctor, lock, resolve, verify


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ngksenvcapsule")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--config", dest="config_path", default=None)
    p_doctor.add_argument("--pf", dest="pf", default=None)

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--config", dest="config_path", default=None)
    p_resolve.add_argument("--auto-install", action="store_true")
    p_resolve.add_argument("--pf", dest="pf", default=None)

    p_lock = sub.add_parser("lock")
    p_lock.add_argument("--in", dest="in_path", default="env_capsule.resolved.json")
    p_lock.add_argument("--out", dest="out_path", default="env_capsule.lock.json")
    p_lock.add_argument("--pf", dest="pf", default=None)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--lock", dest="lock_path", default="env_capsule.lock.json")
    p_verify.add_argument("--pf", dest="pf", default=None)

    p_print = sub.add_parser("print")
    p_print.add_argument("--lock", dest="lock_path", default="env_capsule.lock.json")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    proof_root = Path(args.pf).resolve() if getattr(args, "pf", None) else Path("_proof")
    if args.command == "doctor":
        return doctor.run(config_path=args.config_path, proof_root=proof_root)
    if args.command == "resolve":
        return resolve.run(config_path=args.config_path, auto_install=args.auto_install, proof_root=proof_root)
    if args.command == "lock":
        return lock.run(in_path=args.in_path, out_path=args.out_path, proof_root=proof_root)
    if args.command == "verify":
        return verify.run(lock_path=args.lock_path, proof_root=proof_root)
    if args.command == "print":
        print(Path(args.lock_path).read_text(encoding="utf-8"))
        return 0
    return 10


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
