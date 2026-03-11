from __future__ import annotations


def directory_hint(rel_dir: str) -> str:
    lower = rel_dir.lower()
    if any(part in lower for part in ["third_party", "vendor", "external"]):
        return "vendor"
    if any(part in lower for part in ["build", "out", "cmake-build"]):
        return "build"
    if any(part in lower for part in ["sample", "example", "examples"]):
        return "sample"
    if any(part in lower for part in ["cache", "tmp"]):
        return "cache"
    if any(part in lower for part in ["test", "tests"]):
        return "test"
    if any(part in lower for part in ["generated", "gen"]):
        return "generated"
    return "normal"


def is_stale_risk_path(rel_path: str) -> bool:
    low = rel_path.lower()
    if "build/" in low or "out/" in low or "cmake-build" in low:
        return True
    return False
