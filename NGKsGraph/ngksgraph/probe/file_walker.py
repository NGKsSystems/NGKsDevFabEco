from __future__ import annotations

from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "third_party",
    "_proof",
    "_artifacts",
    "artifacts",
    "__pycache__",
}


def iter_repo_files(repo_root: Path):
    for dirpath, dirnames, filenames in repo_root.walk(top_down=True):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS and not name.startswith(".")]
        for filename in filenames:
            yield dirpath / filename


def relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()
