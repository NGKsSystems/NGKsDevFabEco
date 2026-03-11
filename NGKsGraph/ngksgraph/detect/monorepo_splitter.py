from __future__ import annotations

from pathlib import Path


ROOT_MARKERS = {
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "CMakeLists.txt",
    "*.csproj",
}


def _matches_marker(name: str) -> bool:
    for marker in ROOT_MARKERS:
        if "*" in marker:
            if name.endswith(marker.replace("*", "")):
                return True
        elif name == marker:
            return True
    return False


def split_subprojects(repo_root: Path, files_seen: list[str]) -> list[dict[str, str]]:
    roots: set[str] = set()
    for rel in files_seen:
        name = Path(rel).name
        if not _matches_marker(name):
            continue
        parent = str(Path(rel).parent).replace("\\", "/")
        roots.add("." if parent in {"", "."} else parent)

    if not roots:
        return [{"subproject_id": "root", "root_path": "."}]

    ordered = sorted(roots)
    out = []
    for idx, root in enumerate(ordered, start=1):
        if root == ".":
            out.append({"subproject_id": "root", "root_path": "."})
        else:
            out.append({"subproject_id": f"sp_{idx:02d}", "root_path": root})
    return out
