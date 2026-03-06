from __future__ import annotations

import os
import shutil
import subprocess
import hashlib
import json
from pathlib import Path
from typing import Any

from .receipts import write_json, write_text


def _safe_run(command: list[str]) -> tuple[int, str, str]:
    try:
        out = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return int(out.returncode), out.stdout or "", out.stderr or ""
    except Exception as exc:  # pragma: no cover
        return 126, "", str(exc)


def _vswhere_candidates() -> list[Path]:
    candidates: list[Path] = []
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    pf = os.environ.get("ProgramFiles", "")
    if pf86:
        candidates.append(Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe")
    if pf:
        candidates.append(Path(pf) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe")
    return candidates


def _detect_dotnet(stdout_lines: list[str], stderr_lines: list[str]) -> dict[str, Any]:
    direct = shutil.which("dotnet")
    if not direct:
        return {"path": "", "method": "missing", "version": "tool missing"}
    code, out, err = _safe_run([direct, "--version"])
    if out.strip():
        stdout_lines.append("dotnet --version=" + out.strip())
    if err.strip():
        stderr_lines.append(err.strip())
    version = out.strip() if code == 0 and out.strip() else "unknown"
    return {"path": str(Path(direct).resolve()), "method": "direct", "version": version}


def resolve_tools(pf: Path) -> dict[str, Any]:
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    dotnet = _detect_dotnet(stdout_lines, stderr_lines)
    graph_cli = os.environ.get("NGKSGRAPH_CLI", "").strip()
    graph_cli_path = str(Path(graph_cli).resolve()) if graph_cli else ""
    graph_cli_ready = bool(graph_cli_path) and Path(graph_cli_path).exists()
    payload_for_id = json.dumps({"dotnet": dotnet, "graph_cli": graph_cli_path, "graph_cli_ready": graph_cli_ready}, sort_keys=True)
    resolver_plan_id = hashlib.sha256(payload_for_id.encode("utf-8")).hexdigest()[:16]
    python = shutil.which("python") or ""

    result = {
        "resolved_strategy": "graph",
        "resolver_plan_id": resolver_plan_id,
        "dotnet": dotnet,
        "graph_cli": {"path": graph_cli_path, "ready": graph_cli_ready},
        "builder": {
            "type": "external",
            "status": "not-bound",
        },
        "python": {"path": python, "method": "direct" if python else "missing"},
    }

    write_json(pf / "tool_resolve.json", result)
    write_text(pf / "tool_resolve_stdout.txt", "\n".join(stdout_lines).strip() + "\n")
    write_text(pf / "tool_resolve_stderr.txt", "\n".join(stderr_lines).strip() + "\n")
    return result
