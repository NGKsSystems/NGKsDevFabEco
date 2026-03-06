from __future__ import annotations


def manual_python_instructions(version: str) -> str:
    return (
        f"Install Python {version} exactly from python.org release artifacts, verify SHA256, "
        "then re-run ngksenvcapsule resolve."
    )


def handle_python_missing(version: str, auto_install: bool) -> tuple[bool, str]:
    if auto_install:
        return False, (
            f"Auto-install requested for Python {version}, but deterministic pinned installer flow "
            "is not implemented in Phase 1."
        )

    print(f"Required runtime missing: Python {version}")
    print("Options:")
    print("1 Install automatically")
    print("2 Show manual instructions")
    print("3 Abort")
    try:
        choice = input("Select [1-3]: ").strip()
    except EOFError:
        choice = "3"

    if choice == "2":
        msg = manual_python_instructions(version)
        print(msg)
        return False, msg
    if choice == "1":
        msg = (
            "Automatic install is not implemented in Phase 1. Use manual pinned installer with hash verification."
        )
        print(msg)
        return False, msg
    return False, "Aborted by user"
