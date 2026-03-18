from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import io
import os
import shutil
import subprocess
import zipfile


_ACTIVE_PROOF_RUN_DIR: Path | None = None


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


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_repo_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd] + list(cwd.parents):
        if (candidate / "ngksgraph.toml").exists():
            return candidate
    return cwd


def resolve_proof_root(repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    proof_root = (repo_root / "_proof").resolve()
    if not _is_within(proof_root, repo_root):
        raise RuntimeError("INVALID_PROOF_PATH")
    return proof_root


def resolve_proof_work_root(repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    work_root = (repo_root / ".ngksgraph_proof_tmp").resolve()
    if not _is_within(work_root, repo_root):
        raise RuntimeError("INVALID_PROOF_PATH")
    return work_root


def activate_proof_run(run_dir: Path) -> None:
    global _ACTIVE_PROOF_RUN_DIR
    _ACTIVE_PROOF_RUN_DIR = run_dir.resolve()


def clear_active_proof_run() -> None:
    global _ACTIVE_PROOF_RUN_DIR
    _ACTIVE_PROOF_RUN_DIR = None


def current_proof_run_dir() -> Path | None:
    return _ACTIVE_PROOF_RUN_DIR


def _reserve_proof_paths(proof_root: Path, work_root: Path) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = 0
    while True:
        name = f"run_{stamp}" if suffix == 0 else f"run_{stamp}_{suffix:02d}"
        run_dir = (work_root / name).resolve()
        zip_path = (proof_root / f"{name}.zip").resolve()
        if not run_dir.exists() and not zip_path.exists():
            return run_dir, zip_path
        suffix += 1


def _preserve_failed_temp(run_dir: Path) -> None:
    if not run_dir.exists():
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    failed_dir = (run_dir.parent / f"_FAILED_TEMP_{stamp}").resolve()
    suffix = 1
    while failed_dir.exists():
        failed_dir = (run_dir.parent / f"_FAILED_TEMP_{stamp}_{suffix:02d}").resolve()
        suffix += 1

    try:
        run_dir.rename(failed_dir)
    except Exception:
        pass


def new_proof_run(repo_root: Path) -> ProofRun:
    proof_root = resolve_proof_root(repo_root)
    proof_root.mkdir(parents=True, exist_ok=True)
    work_root = resolve_proof_work_root(repo_root)
    work_root.mkdir(parents=True, exist_ok=True)

    run_dir, zip_path = _reserve_proof_paths(proof_root, work_root)

    if not _is_within(run_dir, work_root):
        raise RuntimeError("INVALID_PROOF_PATH")

    run_dir.mkdir(parents=True, exist_ok=False)
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
    run_dir = run_dir.resolve()
    zip_path = zip_path.resolve()
    tmp_zip = zip_path.with_name(zip_path.name + ".tmp")

    if tmp_zip.exists():
        tmp_zip.unlink()
    if zip_path.exists():
        zip_path.unlink()

    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(run_dir.rglob("*"), key=lambda p: p.as_posix()):
                if path.is_file():
                    zf.write(path, arcname=path.relative_to(run_dir).as_posix())
        tmp_zip.replace(zip_path)
        shutil.rmtree(run_dir)
        try:
            run_dir.parent.rmdir()
        except OSError:
            pass
    except Exception:
        if tmp_zip.exists():
            tmp_zip.unlink()
        _preserve_failed_temp(run_dir)
        raise
