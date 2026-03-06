from __future__ import annotations


REQUIRED_TOP_LEVEL = {"capsule_version", "host", "runtimes", "toolchains"}


def validate_capsule(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Capsule must be a JSON object")
    missing = sorted(REQUIRED_TOP_LEVEL - set(payload.keys()))
    if missing:
        raise ValueError(f"Capsule missing required keys: {', '.join(missing)}")
    if int(payload.get("capsule_version", 0)) != 1:
        raise ValueError("capsule_version must be 1")
    if not isinstance(payload.get("host"), dict):
        raise ValueError("host must be an object")
    if not isinstance(payload.get("runtimes"), dict):
        raise ValueError("runtimes must be an object")
    if not isinstance(payload.get("toolchains"), dict):
        raise ValueError("toolchains must be an object")
