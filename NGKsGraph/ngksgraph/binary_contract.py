from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ngksgraph.util import sha256_file


def inspect_binary_integrity(version_output: str) -> dict[str, Any]:
    try:
        exe_path = Path(sys.executable).resolve()
    except Exception as exc:
        return {"ok": False, "error": f"Unable to resolve executable path: {exc}"}

    if not exe_path.exists() or not exe_path.is_file():
        return {"ok": False, "error": f"Executable path does not exist: {exe_path}"}

    manifest_path = exe_path.parent / "manifest.json"
    if not manifest_path.exists():
        return {
            "ok": True,
            "note": "MANIFEST_MISSING",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Manifest parse failed: {exc}",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
        }

    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "error": "Manifest is not a JSON object",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
        }

    expected_hash = str(manifest.get("sha256_ngksgraph_exe", "")).strip().lower()
    actual_hash = sha256_file(exe_path).lower()

    if not expected_hash:
        return {
            "ok": False,
            "error": "Manifest missing sha256_ngksgraph_exe",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
            "actual_hash": actual_hash,
        }

    if expected_hash != actual_hash:
        return {
            "ok": False,
            "error": "BINARY_HASH_MISMATCH",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
        }

    expected_version = str(manifest.get("version_output", "")).strip()
    if not expected_version:
        return {
            "ok": False,
            "error": "Manifest missing version_output",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
            "actual_version": version_output,
        }

    if expected_version != version_output:
        return {
            "ok": False,
            "error": "VERSION_STRING_MISMATCH",
            "exe_path": str(exe_path),
            "manifest_path": str(manifest_path),
            "expected_version": expected_version,
            "actual_version": version_output,
        }

    return {
        "ok": True,
        "note": "MANIFEST_VERIFIED",
        "exe_path": str(exe_path),
        "manifest_path": str(manifest_path),
        "sha256": actual_hash,
    }
