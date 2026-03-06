from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .receipts import file_sha256_safe, utc_now_iso, write_json, write_text


def _git_output(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        return (proc.stdout or "").strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def repo_state(repo_root: Path) -> dict[str, Any]:
    head = _git_output(["git", "rev-parse", "HEAD"], repo_root)
    status = _git_output(["git", "status", "--porcelain"], repo_root)
    return {
        "root": str(repo_root.resolve()),
        "head": head or "unknown",
        "dirty": bool(status),
    }


def ensure_unified_pf(pf: Path, intent: dict[str, Any], components: list[str], repo_root: Path) -> Path:
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)
    for folder in ["graph", "devfabric", "buildcore", "summary"]:
        (pf / folder).mkdir(parents=True, exist_ok=True)

    proof_root = (repo_root / "_proof").resolve()
    try:
        pf_rel = pf.relative_to(proof_root).as_posix()
    except Exception:
        pf_rel = pf.as_posix()

    manifest = {
        "schema": "ngks.proof.manifest.v1",
        "pf_rel": pf_rel,
        "created_ts": utc_now_iso(),
        "intent": {
            "command": str(intent.get("command", "unknown")),
            "args": list(intent.get("args", [])),
            "mode": str(intent.get("mode", "execute")),
        },
        "components": components,
        "repos": {
            "devfabric": repo_state(repo_root),
        },
    }
    write_json(pf / "00_run_manifest.json", manifest)
    if not (pf / "00_writes_ledger.jsonl").exists():
        write_text(pf / "00_writes_ledger.jsonl", "")
    return pf


def _is_log(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".log", ".stderr", ".stdout"}:
        return True
    return "log" in path.name.lower() or "stderr" in path.name.lower() or "stdout" in path.name.lower()


def _is_output(path: Path) -> bool:
    return not _is_log(path)


def _entry_for_file(component: str, pf: Path, file_path: Path, notes: list[str]) -> dict[str, Any]:
    rel = file_path.resolve().relative_to(pf.resolve()).as_posix()
    item: dict[str, Any] = {
        "name": file_path.name,
        "path": rel,
    }
    sha = file_sha256_safe(file_path)
    if sha is None:
        notes.append(f"hash_missing:{rel}")
    else:
        item["sha256"] = sha
    return item


def collect_component_files(component_dir: Path) -> list[Path]:
    if not component_dir.exists():
        return []
    files = [p for p in component_dir.rglob("*") if p.is_file() and p.name != "component_report.json"]
    return sorted(files, key=lambda p: p.as_posix())


def write_component_report(
    pf: Path,
    component: str,
    status: str,
    start_ts: str,
    end_ts: str,
    cmdline: str,
    repo: dict[str, Any],
    version: str = "unknown",
    notes: list[str] | None = None,
) -> Path:
    notes_list = list(notes or [])
    component_dir = pf / component
    files = collect_component_files(component_dir)
    key_logs: list[dict[str, Any]] = []
    key_outputs: list[dict[str, Any]] = []

    for file_path in files:
        entry = _entry_for_file(component, pf, file_path, notes_list)
        if _is_log(file_path):
            key_logs.append(entry)
        elif _is_output(file_path):
            key_outputs.append(entry)

    report = {
        "component": component,
        "version": version,
        "status": status,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "cmdline": cmdline,
        "repo": repo,
        "key_outputs": key_outputs,
        "key_logs": key_logs,
        "notes": notes_list,
    }
    return write_json(component_dir / "component_report.json", report)


def append_ledger(pf: Path, rel_path: str, writer: str) -> None:
    ledger_path = pf / "00_writes_ledger.jsonl"
    record = {"ts": utc_now_iso(), "path": rel_path.replace("\\", "/"), "writer": writer}
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def reconcile_ledger(pf: Path) -> None:
    ledger_path = pf / "00_writes_ledger.jsonl"
    seen: set[tuple[str, str]] = set()
    if ledger_path.exists():
        for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            path = str(row.get("path", "")).replace("\\", "/")
            writer = str(row.get("writer", ""))
            if path and writer:
                seen.add((path, writer))

    for file_path in sorted([p for p in pf.rglob("*") if p.is_file()]):
        rel = file_path.resolve().relative_to(pf.resolve()).as_posix()
        if rel == "00_writes_ledger.jsonl":
            continue
        if rel.startswith("summary/"):
            writer = "docengine"
        elif rel.startswith("graph/"):
            writer = "graph"
        elif rel.startswith("buildcore/"):
            writer = "buildcore"
        elif rel.startswith("devfabric/") or rel in {"00_run_manifest.json"}:
            writer = "devfabric"
        else:
            writer = "devfabric"

        key = (rel, writer)
        if key not in seen:
            append_ledger(pf, rel, writer)
            seen.add(key)


def _is_allowed_ledger_entry(path: str, writer: str) -> bool:
    path = path.replace("\\", "/")
    docengine_allowed = {"summary/index.json", "summary/SUMMARY.md"}
    if writer == "docengine":
        return path in docengine_allowed
    if writer == "devfabric":
        return path.startswith("devfabric/") or path in {"00_run_manifest.json", "00_writes_ledger.jsonl"}
    if writer == "graph":
        return path.startswith("graph/")
    if writer == "buildcore":
        return path.startswith("buildcore/")
    return False


def doc_gate(pf: Path) -> tuple[int, dict[str, Any]]:
    pf = pf.resolve()
    errors: list[str] = []

    manifest_path = pf / "00_run_manifest.json"
    summary_md = pf / "summary" / "SUMMARY.md"
    summary_index = pf / "summary" / "index.json"
    ledger_path = pf / "00_writes_ledger.jsonl"

    manifest: dict[str, Any] = {}
    if not manifest_path.exists():
        errors.append("missing:00_run_manifest.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid_manifest_json:{exc}")

    if not summary_md.exists():
        errors.append("missing:summary/SUMMARY.md")
    if not summary_index.exists():
        errors.append("missing:summary/index.json")
    else:
        try:
            index_payload = json.loads(summary_index.read_text(encoding="utf-8"))
            if str(index_payload.get("schema", "")) != "ngks.doc.index.v1":
                errors.append("invalid:summary/index.json:schema")
        except Exception as exc:
            errors.append(f"invalid_summary_index_json:{exc}")

    for component in manifest.get("components", []) if isinstance(manifest, dict) else []:
        comp_report = pf / str(component) / "component_report.json"
        if not comp_report.exists():
            errors.append(f"missing:{component}/component_report.json")

    if not ledger_path.exists():
        errors.append("missing:00_writes_ledger.jsonl")
    else:
        seen_docengine_paths: set[str] = set()
        for idx, line in enumerate(ledger_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                errors.append(f"invalid_ledger_json:line{idx}")
                continue
            path = str(row.get("path", ""))
            writer = str(row.get("writer", ""))
            if not path or not writer:
                errors.append(f"invalid_ledger_fields:line{idx}")
                continue
            normalized_path = path.replace("\\", "/")
            if writer == "docengine":
                seen_docengine_paths.add(normalized_path)
            if not _is_allowed_ledger_entry(path, writer):
                errors.append(f"ledger_violation:line{idx}:{writer}:{path}")

        for required_docengine_path in ["summary/index.json", "summary/SUMMARY.md"]:
            if required_docengine_path not in seen_docengine_paths:
                errors.append(f"missing_docengine_ledger:{required_docengine_path}")

    report = {
        "pf": str(pf),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "python": sys.version.split()[0],
    }

    write_json(pf / "devfabric" / "doc_gate_report.json", report)
    return (0 if not errors else 2), report


def _resolve_ngkslibrary_root(devfabric_root: Path) -> Path | None:
    env_root = os.environ.get("NGKSLIBRARY_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).resolve()
        if (candidate / "ngksdocengine").exists():
            return candidate

    sibling = (devfabric_root.parent / "NGKsLibrary").resolve()
    if (sibling / "ngksdocengine").exists():
        return sibling
    return None


def run_docengine_render(pf: Path, devfabric_root: Path) -> tuple[int, dict[str, Any]]:
    pf = pf.resolve()
    devfabric_root = devfabric_root.resolve()
    ngkslibrary_root = _resolve_ngkslibrary_root(devfabric_root)

    if ngkslibrary_root is None:
        details = {
            "status": "FAIL",
            "reason": "ngkslibrary_not_found",
            "hint": "Set NGKSLIBRARY_ROOT or place NGKsLibrary beside NGKsDevFabric",
            "pf": str(pf),
        }
        return 2, details

    command = [sys.executable, "-m", "ngksdocengine", "render", "--pf", str(pf)]
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ngkslibrary_root) + (os.pathsep + existing if existing else "")

    proc = subprocess.run(
        command,
        cwd=str(ngkslibrary_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    details = {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "pf": str(pf),
        "ngkslibrary_root": str(ngkslibrary_root),
        "command": command,
        "exit_code": int(proc.returncode),
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }
    return int(proc.returncode), details
