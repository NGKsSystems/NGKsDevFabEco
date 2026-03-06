from __future__ import annotations

import argparse
from pathlib import Path

from ngkslibrary.docengine.proof_context import ProofContext
from ngkslibrary.docengine.report import render_report


def _resolve_run_id(run_pf: Path, run_id: str | None) -> str:
    if run_id and run_id.strip():
        return run_id.strip()
    name = run_pf.name
    marker = "devfabric_run_"
    if name.startswith(marker):
        return name[len(marker):]
    return name


def cmd_assemble(args: argparse.Namespace) -> int:
    run_pf = Path(args.run_proof).resolve()
    stage_pf = Path(args.pf).resolve() if args.pf else (run_pf / "40_library").resolve()
    context = ProofContext.from_paths(
        run_id=_resolve_run_id(run_pf, args.run_id),
        run_pf=run_pf,
        stage_pf=stage_pf,
        backup_root=Path(args.backup_root).resolve() if args.backup_root else None,
    )
    report_md, report_json = render_report(
        context=context,
        build_system=str(args.build_system or "unknown"),
        build_action=str(args.build_action or "attempted"),
        build_reason=str(args.build_reason or "build_completed"),
        exit_code=int(args.exit_code),
    )
    print(f"report_md={report_md}")
    print(f"report_json={report_json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ngkslibrary")
    sub = parser.add_subparsers(dest="cmd", required=True)

    assemble = sub.add_parser("assemble")
    assemble.add_argument("--run-proof", required=True)
    assemble.add_argument("--pf", required=False)
    assemble.add_argument("--run-id", required=False)
    assemble.add_argument("--backup-root", required=False)
    assemble.add_argument("--build-system", required=False, default="unknown")
    assemble.add_argument("--build-action", required=False, default="attempted")
    assemble.add_argument("--build-reason", required=False, default="build_completed")
    assemble.add_argument("--exit-code", required=False, type=int, default=0)
    assemble.set_defaults(func=cmd_assemble)

    render = sub.add_parser("render")
    render.add_argument("--pf", required=True)
    render.add_argument("--run-proof", required=False)
    render.add_argument("--run-id", required=False)
    render.add_argument("--build-system", required=False, default="unknown")
    render.add_argument("--build-action", required=False, default="attempted")
    render.add_argument("--build-reason", required=False, default="build_completed")
    render.add_argument("--exit-code", required=False, type=int, default=0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd in {"assemble", "render"}:
        if args.cmd == "render" and not getattr(args, "run_proof", None):
            setattr(args, "run_proof", args.pf)
        return int(cmd_assemble(args))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
