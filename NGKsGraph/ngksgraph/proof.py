from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import io
import os
import shutil
import subprocess
import zipfile


class TeeTextIO(io.TextIOBase):
    def __init__(self, primary: io.TextIOBase, mirror: io.TextIOBase):
        self._primary = primary
        self._mirror = mirror

    def write(self, s: str) -> int:
        written = self._primary.write(s)
        self._primary.flush()
        self._mirror.write(s)
        self._mirror.flush()
        return written

    def flush(self) -> None:
        self._primary.flush()
        self._mirror.flush()


@dataclass
class ProofRun:
    repo_root: Path
    run_dir: Path
    zip_path: Path


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_proof_root(repo_root: Path) -> Path:
    proof_root = (repo_root / "_proof").resolve()
    if not str(proof_root).startswith(str(repo_root.resolve())):
        raise RuntimeError("INVALID_PROOF_PATH")
    return proof_root


def _resolve_easy_access_root(repo_root: Path) -> Path:
    easy_root = (repo_root / "proofs").resolve()
    easy_root.mkdir(parents=True, exist_ok=True)
    return easy_root


def _mirror_easy_access(run_dir: Path, zip_path: Path) -> None:
    try:
        repo_root = run_dir.parent.parent.resolve()
        easy_root = _resolve_easy_access_root(repo_root)
        latest_run_dir = easy_root / "latest_ngksgraph_run"
        if latest_run_dir.exists():
            shutil.rmtree(latest_run_dir)
        shutil.copytree(run_dir, latest_run_dir)
        shutil.copy2(zip_path, easy_root / "latest_ngksgraph_run.zip")
        (easy_root / "LATEST_NGKSGRAPH_PROOF_DIR.txt").write_text(str(run_dir) + "\n", encoding="utf-8")
        (easy_root / "LATEST_NGKSGRAPH_PROOF_ZIP.txt").write_text(str(zip_path) + "\n", encoding="utf-8")
    except Exception:
        # Proof mirroring is best-effort and must never fail the primary run.
        pass


def new_proof_run(repo_root: Path) -> ProofRun:
    proof_root = resolve_proof_root(repo_root)
    proof_root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = (proof_root / f"run_{stamp}").resolve()
    suffix = 1
    while run_dir.exists():
        run_dir = (proof_root / f"run_{stamp}_{suffix:02d}").resolve()
        suffix += 1

    if not str(run_dir).startswith(str(proof_root)):
        raise RuntimeError("INVALID_PROOF_PATH")

    run_dir.mkdir(parents=True, exist_ok=False)
    zip_path = run_dir.with_suffix(".zip")
    return ProofRun(repo_root=repo_root.resolve(), run_dir=run_dir, zip_path=zip_path.resolve())


def gather_git_metadata(repo_root: Path, run_dir: Path) -> tuple[str, str]:
    rev = "unknown"
    status = ""

    try:
        proc_rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            shell=False,
        )
        if proc_rev.returncode == 0:
            rev = (proc_rev.stdout or "").strip() or "unknown"
        else:
            rev = ((proc_rev.stderr or proc_rev.stdout or "unknown").strip() or "unknown")
    except Exception as exc:
        rev = f"error: {exc}"

    try:
        proc_status = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            shell=False,
        )
        status = (proc_status.stdout or proc_status.stderr or "").strip()
    except Exception as exc:
        status = f"error: {exc}"

    (run_dir / "git_rev_parse_head.txt").write_text(rev + "\n", encoding="utf-8")
    (run_dir / "git_status.txt").write_text((status + "\n") if status else "", encoding="utf-8")
    return rev, status


def write_summary(
    run_dir: Path,
    *,
    command: str,
    exit_code: int,
    started_at: str,
    finished_at: str,
    python_path: str,
    cwd: str,
    git_commit: str,
) -> None:
    lines = [
        "# RUN SUMMARY",
        "",
        f"- timestamp_start_utc: {started_at}",
        f"- timestamp_end_utc: {finished_at}",
        f"- command: {command}",
        f"- exit_code: {exit_code}",
        f"- python: {python_path}",
        f"- cwd: {cwd}",
        f"- git_commit: {git_commit}",
        f"- platform: {os.name}",
    ]
    (run_dir / "RUN_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_run(run_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(run_dir.rglob("*"), key=lambda p: p.as_posix()):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(run_dir).as_posix())
    _mirror_easy_access(run_dir, zip_path)
