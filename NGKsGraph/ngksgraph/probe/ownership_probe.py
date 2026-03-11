from __future__ import annotations


def ownership_for_path(rel_path: str) -> str:
    lower = rel_path.lower()
    if any(part in lower for part in ["/third_party/", "/vendor/", "/external/"]):
        return "third_party"
    if any(part in lower for part in ["/build/", "/out/", "/cmake-build"]):
        return "generated"
    return "first_party"
