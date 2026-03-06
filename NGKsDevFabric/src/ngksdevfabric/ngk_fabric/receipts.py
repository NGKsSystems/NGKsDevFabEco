from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_PROOF_CONTEXT = threading.local()


def _get_proof_context() -> tuple[Path | None, str]:
    pf_root = getattr(_PROOF_CONTEXT, "pf_root", None)
    writer = getattr(_PROOF_CONTEXT, "writer", "devfabric")
    return pf_root, writer


def set_proof_context(pf_root: Path | None, writer: str) -> None:
    _PROOF_CONTEXT.pf_root = pf_root.resolve() if pf_root else None
    _PROOF_CONTEXT.writer = writer


def clear_proof_context() -> None:
    _PROOF_CONTEXT.pf_root = None
    _PROOF_CONTEXT.writer = "devfabric"


def _append_ledger_entry_for_path(path: Path) -> None:
    pf_root, writer = _get_proof_context()
    if pf_root is None:
        return
    try:
        abs_path = path.resolve()
        rel_path = abs_path.relative_to(pf_root).as_posix()
    except Exception:
        return
    if rel_path == "00_writes_ledger.jsonl":
        return
    ledger_path = pf_root / "00_writes_ledger.jsonl"
    ensure_dir(ledger_path.parent)
    record = {
        "ts": utc_now_iso(),
        "path": rel_path,
        "writer": writer,
    }
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    _append_ledger_entry_for_path(path)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    _append_ledger_entry_for_path(path)
    return path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256_safe(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return file_sha256(path)
    except Exception:
        return None


def hash_command(parts: Iterable[str]) -> str:
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def run_command_capture(
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str] | None = None,
) -> int:
    ensure_dir(stdout_path.parent)
    ensure_dir(stderr_path.parent)
    with stdout_path.open("w", encoding="utf-8", newline="\n") as out_handle, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as err_handle:
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=out_handle,
                stderr=err_handle,
                env=env,
                check=False,
            )
            _append_ledger_entry_for_path(stdout_path)
            _append_ledger_entry_for_path(stderr_path)
            return int(completed.returncode)
        except FileNotFoundError as exc:
            err_handle.write(f"tool missing: {exc}\n")
            _append_ledger_entry_for_path(stdout_path)
            _append_ledger_entry_for_path(stderr_path)
            return 127
        except Exception as exc:  # pragma: no cover
            err_handle.write(f"execution error: {exc}\n")
            _append_ledger_entry_for_path(stdout_path)
            _append_ledger_entry_for_path(stderr_path)
            return 126


def tool_version(tool: str) -> str:
    try:
        out = subprocess.run(
            [tool, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        text = (out.stdout or "").strip()
        return text if text else f"{tool} --version returned empty"
    except FileNotFoundError:
        return "tool missing"
    except Exception as exc:  # pragma: no cover
        return f"error: {exc}"


def is_writable_directory(path: Path) -> bool:
    try:
        ensure_dir(path)
        probe = path / ".ngk_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def apply_src_to_env(base_env: dict[str, str], src_path: Path) -> dict[str, str]:
    env = dict(base_env)
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = str(src_path) + os.pathsep + existing
    else:
        env["PYTHONPATH"] = str(src_path)
    return env
