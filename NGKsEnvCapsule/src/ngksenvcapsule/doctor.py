from __future__ import annotations

from pathlib import Path

from .core.engine import build_host_context, collect_candidates
from .core.registry import PROVIDER_ORDER, get_default_registry
from .config import load_config
from .proof import ProofSession, utc_now_iso
from .stablejson import write_stable_json


def run(config_path: str | None = None, proof_root: Path = Path("_proof")) -> int:
    proof = ProofSession("doctor", ["ngksenvcapsule", "doctor"], Path.cwd(), root=proof_root)
    try:
        cfg = load_config(config_path)
        host_ctx = build_host_context()
        registry = get_default_registry()
        candidates_map = collect_candidates(registry, host_ctx)
        host = {"os": host_ctx.os, "arch": host_ctx.arch}
        report = {
            "generated_utc": utc_now_iso(),
            "host": host,
            "providers": {},
        }
        for name in PROVIDER_ORDER:
            rows = []
            for c in candidates_map[name]:
                if name == "python" or name == "node":
                    rows.append({"version": c.version, "exe": c.meta.get("exe", "")})
                elif name == "msvc":
                    rows.append({"install_id": c.id, "toolset": c.version, "path": c.meta.get("path", "")})
                elif name == "windows_sdk":
                    rows.append({"version": c.version})
                else:
                    rows.append({"id": c.id, "version": c.version, **(c.meta or {})})
            report["providers"][name] = rows

        report_path = Path("toolchain_report.json")
        summary_path = Path("doctor_summary.txt")
        write_stable_json(report_path, report)
        summary = [
            f"host={host['os']}/{host['arch']}",
            f"python_candidates={len(report['providers']['python'])}",
            f"node_candidates={len(report['providers']['node'])}",
            f"msvc_candidates={len(report['providers']['msvc'])}",
            f"windows_sdk_candidates={len(report['providers']['windows_sdk'])}",
        ]
        summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8", newline="\n")

        proof.write_inputs([f"config_path={cfg.path}", f"config_exists={cfg.exists}"])
        proof.add_output(report_path)
        proof.add_output(summary_path)
        proof.copy_artifact(report_path)
        proof.copy_artifact(summary_path)
        proof.finalize()
        print(str(report_path))
        return 0
    except Exception as exc:
        proof.write_error("doctor failed", exc)
        proof.finalize()
        print(f"doctor failed: {exc}")
        return 10
