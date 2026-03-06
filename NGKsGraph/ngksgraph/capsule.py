from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import tempfile
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
import zipfile

from ngksgraph.build import configure_project
from ngksgraph.config import Config, load_config
from ngksgraph.diff import resolve_snapshot
from ngksgraph.hashutil import sha256_json, sha256_text, stable_json_dumps
from ngksgraph.log import write_json
from ngksgraph.util import normalize_path, sha256_file

CAPSULE_FILES_ORDER = [
    "capsule_meta.json",
    "graph.json",
    "compdb.json",
    "config.normalized.json",
    "hashes.json",
    "toolchain.json",
    "snapshot_ref.json",
]

REQUIRED_CAPSULE_FILES = [
    "capsule_meta.json",
    "graph.json",
    "compdb.json",
    "config.normalized.json",
    "hashes.json",
    "toolchain.json",
]


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _json_text(obj: Any) -> str:
    return _normalize_newlines(stable_json_dumps(obj)).rstrip("\n") + "\n"


def _slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return safe.strip("_") or "unknown"


def _query_command_text(args: list[str], timeout: float = 5.0) -> str | None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, shell=False, timeout=timeout)
    except Exception:
        return None
    body = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
    body = body.strip()
    return body or None


def _detect_cl_version() -> str | None:
    text = _query_command_text(["cl"])
    if not text:
        return None
    for line in text.splitlines():
        if "Compiler Version" in line:
            return line.strip()
    return None


def _read_last_report(out_dir: Path) -> dict[str, Any]:
    report_path = out_dir / "ngksgraph_last_report.json"
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_toolchain_summary(out_dir: Path, msvc_auto_used: bool) -> dict[str, Any]:
    last_report = _read_last_report(out_dir)
    toolchain = {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "msvc_auto_used": bool(msvc_auto_used),
        "vswhere_path": last_report.get("vswhere_path"),
        "vs_install_path": last_report.get("vs_install_path"),
        "vsdevcmd_path": last_report.get("vsdevcmd_path"),
    }
    cl_version = _detect_cl_version()
    if cl_version:
        toolchain["cl_version"] = cl_version
    return toolchain


def _graph_link_closure(graph: dict[str, Any], target_name: str) -> list[str]:
    targets = graph.get("targets", {})
    if target_name not in targets:
        return []

    visited: set[str] = set()

    def dfs(name: str) -> None:
        target = targets.get(name, {})
        for dep in target.get("links", []):
            if dep not in visited:
                visited.add(dep)
                dfs(dep)

    dfs(target_name)
    order = graph.get("build_order", sorted(targets.keys()))
    return [name for name in order if name in visited]


def closure_hashes_from_graph(graph: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    targets = graph.get("targets", {})
    for target_name in sorted(targets.keys()):
        target = targets[target_name]
        payload = {
            "target": target_name,
            "kind": target.get("kind"),
            "sources": target.get("sources", []),
            "include_dirs": target.get("include_dirs", []),
            "defines": target.get("defines", []),
            "cflags": target.get("cflags", []),
            "libs": target.get("libs", []),
            "lib_dirs": target.get("lib_dirs", []),
            "ldflags": target.get("ldflags", []),
            "links": target.get("links", []),
            "closure": _graph_link_closure(graph, target_name),
        }
        out[target_name] = sha256_text(stable_json_dumps(payload))
    return out


def compute_hashes(config_normalized: dict[str, Any], graph: dict[str, Any], compdb: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "config_hash": sha256_json(config_normalized),
        "graph_hash": sha256_json(graph),
        "compdb_hash": sha256_json(compdb),
        "closure_hashes": closure_hashes_from_graph(graph),
    }


def compute_qt_generated_hashes(repo_root: Path, generated_files: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in sorted(set(generated_files)):
        path = (repo_root / rel).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Qt generated file missing: {path}")
        out[normalize_path(rel)] = sha256_file(path)
    return out


def verify_hashes(config_normalized: dict[str, Any], graph: dict[str, Any], compdb: list[dict[str, Any]], expected_hashes: dict[str, Any]) -> tuple[bool, list[dict[str, str]], dict[str, Any]]:
    actual = compute_hashes(config_normalized, graph, compdb)
    mismatches: list[dict[str, str]] = []

    for key in ["config_hash", "graph_hash", "compdb_hash"]:
        if str(expected_hashes.get(key)) != str(actual.get(key)):
            mismatches.append(
                {
                    "component": key,
                    "expected": str(expected_hashes.get(key)),
                    "actual": str(actual.get(key)),
                }
            )

    expected_closure = expected_hashes.get("closure_hashes", {}) or {}
    actual_closure = actual.get("closure_hashes", {}) or {}
    for target_name in sorted(set(expected_closure.keys()) | set(actual_closure.keys())):
        if str(expected_closure.get(target_name)) != str(actual_closure.get(target_name)):
            mismatches.append(
                {
                    "component": f"closure_hashes.{target_name}",
                    "expected": str(expected_closure.get(target_name)),
                    "actual": str(actual_closure.get(target_name)),
                }
            )

    return len(mismatches) == 0, mismatches, actual


def build_capsule_payload_files(
    capsule_meta: dict[str, Any],
    graph: dict[str, Any],
    compdb: list[dict[str, Any]],
    config_normalized: dict[str, Any],
    hashes: dict[str, Any],
    toolchain: dict[str, Any],
    snapshot_ref: dict[str, Any] | None,
    qt_generated_payload: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    payload: dict[str, bytes] = {
        "capsule_meta.json": _json_text(capsule_meta).encode("utf-8"),
        "graph.json": _json_text(graph).encode("utf-8"),
        "compdb.json": _json_text(compdb).encode("utf-8"),
        "config.normalized.json": _json_text(config_normalized).encode("utf-8"),
        "hashes.json": _json_text(hashes).encode("utf-8"),
        "toolchain.json": _json_text(toolchain).encode("utf-8"),
    }
    if snapshot_ref is not None:
        payload["snapshot_ref.json"] = _json_text(snapshot_ref).encode("utf-8")
    if qt_generated_payload:
        for name in sorted(qt_generated_payload.keys()):
            payload[name] = qt_generated_payload[name]
    return payload


def write_deterministic_capsule_zip(zip_path: Path, payload: dict[str, bytes]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    constant_time = (1980, 1, 1, 0, 0, 0)

    with tempfile.NamedTemporaryFile(delete=False, dir=str(zip_path.parent), suffix=".tmp") as tmp:
        tmp_zip = Path(tmp.name)

    with zipfile.ZipFile(tmp_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in CAPSULE_FILES_ORDER:
            if name not in payload:
                continue
            info = zipfile.ZipInfo(filename=name)
            info.date_time = constant_time
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0
            zf.writestr(info, payload[name])

        extra = sorted([name for name in payload.keys() if name not in CAPSULE_FILES_ORDER])
        for name in extra:
            info = zipfile.ZipInfo(filename=name)
            info.date_time = constant_time
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0
            zf.writestr(info, payload[name])

    tmp_zip.replace(zip_path)


def _load_snapshot_artifacts(snapshot_dir: Path) -> dict[str, Any]:
    items: dict[str, Any] = {}

    graph_file = snapshot_dir / "graph.json"
    if graph_file.exists():
        items["graph"] = json.loads(graph_file.read_text(encoding="utf-8"))

    compdb_file = snapshot_dir / "compdb.json"
    if compdb_file.exists():
        items["compdb"] = json.loads(compdb_file.read_text(encoding="utf-8"))

    cfg_file = snapshot_dir / "ngksgraph.toml"
    if cfg_file.exists():
        snap_cfg = load_config(cfg_file)
        snap_cfg.normalize()
        items["config_normalized"] = asdict(snap_cfg)

    meta_file = snapshot_dir / "meta.json"
    if meta_file.exists():
        try:
            items["meta"] = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return items


def _default_capsule_path(out_dir: Path, project_name: str, target_name: str) -> Path:
    capsules_dir = out_dir / "ngksgraph_capsules"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    return capsules_dir / f"{stamp}_{_slug(project_name)}_{_slug(target_name)}.ngkcapsule.zip"


def _resolve_snapshot_dir(out_dir: Path, snapshot_ref: str) -> Path:
    snapshots_root = out_dir / ".ngksgraph_snapshots"
    resolved = resolve_snapshot(snapshots_root, snapshot_ref, -1)
    if resolved is None:
        raise FileNotFoundError(f"Snapshot not found: {snapshot_ref}")
    return resolved


def _update_last_report_with_capsule(out_dir: Path, capsule_path: Path, capsule_hash: str, capsule_created_at: str) -> None:
    report_path = out_dir / "ngksgraph_last_report.json"
    payload: dict[str, Any] = {}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    payload["capsule_path"] = normalize_path(capsule_path.resolve())
    payload["capsule_hash"] = capsule_hash
    payload["capsule_created_at"] = capsule_created_at

    history = payload.get("history")
    if isinstance(history, list):
        history.append(
            {
                "source": "freeze",
                "capsule_path": payload["capsule_path"],
                "capsule_hash": capsule_hash,
                "created_at": capsule_created_at,
            }
        )

    write_json(report_path, payload)


def freeze_capsule(
    repo_root: Path,
    config_path: Path,
    target: str | None = None,
    from_snapshot: str | None = None,
    out: Path | None = None,
    msvc_auto: bool = False,
    verify: bool = True,
    profile: str | None = None,
) -> dict[str, Any]:
    configured = configure_project(repo_root, config_path, msvc_auto=msvc_auto, target=target, profile=profile)
    config: Config = configured["config"]
    config.normalize()

    selected_target = configured["selected_target"]
    out_dir = configured["paths"]["out_dir"]

    graph_payload = configured["graph_payload"]
    compdb = configured["compdb"]
    config_normalized = asdict(config)
    qt_result = configured.get("qt_result")

    snapshot_ref_payload: dict[str, Any] | None = None

    if from_snapshot:
        snapshot_dir = _resolve_snapshot_dir(out_dir, from_snapshot)
        snapshot_artifacts = _load_snapshot_artifacts(snapshot_dir)

        graph_payload = snapshot_artifacts.get("graph", graph_payload)
        compdb = snapshot_artifacts.get("compdb", compdb)
        config_normalized = snapshot_artifacts.get("config_normalized", config_normalized)

        snapshot_ref_payload = {
            "snapshot": snapshot_dir.name,
            "path": normalize_path(snapshot_dir.resolve()),
            "fallbacks_used": {
                "graph": "graph" not in snapshot_artifacts,
                "compdb": "compdb" not in snapshot_artifacts,
                "normalized_config": "config_normalized" not in snapshot_artifacts,
            },
        }

    hashes = compute_hashes(config_normalized, graph_payload, compdb)
    qt_generated_payload: dict[str, bytes] = {}
    qt_generated_files: list[str] = []
    if qt_result is not None:
        qt_generated_files = list(getattr(qt_result, "generated_files", []))
    if qt_generated_files:
        hashes["qt_generated_hashes"] = compute_qt_generated_hashes(repo_root, qt_generated_files)
        for rel in sorted(qt_generated_files):
            blob = (repo_root / rel).read_bytes()
            qt_generated_payload[f"qt_generated/{normalize_path(rel)}"] = blob

    capsule_meta = {
        "schema_version": 1,
        "project": config.name,
        "target": selected_target,
        "msvc_auto_used": bool(msvc_auto),
        "source": "snapshot" if from_snapshot else "live",
        "qt_enabled": bool(config.qt.enabled),
    }

    toolchain = build_toolchain_summary(out_dir=out_dir, msvc_auto_used=msvc_auto)
    if qt_result is not None and getattr(qt_result, "tool_info", {}):
        toolchain["qt_tools"] = getattr(qt_result, "tool_info", {})
    payload = build_capsule_payload_files(
        capsule_meta=capsule_meta,
        graph=graph_payload,
        compdb=compdb,
        config_normalized=config_normalized,
        hashes=hashes,
        toolchain=toolchain,
        snapshot_ref=snapshot_ref_payload,
        qt_generated_payload=qt_generated_payload,
    )

    zip_path = out if out is not None else _default_capsule_path(out_dir=out_dir, project_name=config.name, target_name=selected_target)
    write_deterministic_capsule_zip(zip_path, payload)

    if verify:
        verified = verify_capsule(zip_path)
        if not verified["ok"]:
            raise ValueError(f"Capsule verification failed: {verified['mismatches']}")

    capsule_bytes = zip_path.read_bytes()
    capsule_hash = hashlib.sha256(capsule_bytes).hexdigest()
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _update_last_report_with_capsule(out_dir=out_dir, capsule_path=zip_path, capsule_hash=capsule_hash, capsule_created_at=created_at)

    return {
        "ok": True,
        "capsule_path": normalize_path(zip_path.resolve()),
        "capsule_hash": capsule_hash,
        "capsule_created_at": created_at,
    }


def _read_capsule_json(zip_file: zipfile.ZipFile, name: str) -> Any:
    return json.loads(zip_file.read(name).decode("utf-8"))


def verify_capsule(capsule_path: Path) -> dict[str, Any]:
    if not capsule_path.exists():
        return {"ok": False, "mismatches": [{"component": "capsule", "expected": "exists", "actual": "missing"}]}

    with zipfile.ZipFile(capsule_path, mode="r") as zf:
        names = set(zf.namelist())
        missing = [name for name in REQUIRED_CAPSULE_FILES if name not in names]
        if missing:
            return {
                "ok": False,
                "mismatches": [
                    {"component": "missing_files", "expected": ",".join(REQUIRED_CAPSULE_FILES), "actual": ",".join(sorted(missing))}
                ],
            }

        graph = _read_capsule_json(zf, "graph.json")
        compdb = _read_capsule_json(zf, "compdb.json")
        config_normalized = _read_capsule_json(zf, "config.normalized.json")
        hashes = _read_capsule_json(zf, "hashes.json")
        toolchain = _read_capsule_json(zf, "toolchain.json")

        qt_generated_in_zip = sorted([n for n in zf.namelist() if n.startswith("qt_generated/")])
        qt_generated_hashes = hashes.get("qt_generated_hashes", {}) if isinstance(hashes, dict) else {}

    ok, mismatches, actual = verify_hashes(config_normalized, graph, compdb, hashes)

    if isinstance(qt_generated_hashes, dict):
        for rel, expected_hash in sorted(qt_generated_hashes.items()):
            capsule_name = f"qt_generated/{rel}"
            if capsule_name not in qt_generated_in_zip:
                mismatches.append({"component": f"qt_generated.{rel}", "expected": str(expected_hash), "actual": "missing_in_capsule"})
                continue
            with zipfile.ZipFile(capsule_path, mode="r") as zf2:
                blob = zf2.read(capsule_name)
            actual_hash = hashlib.sha256(blob).hexdigest()
            if actual_hash != str(expected_hash):
                mismatches.append({"component": f"qt_generated.{rel}", "expected": str(expected_hash), "actual": actual_hash})

    qt_tools = toolchain.get("qt_tools", {}) if isinstance(toolchain, dict) else {}
    for tool_name in ["moc", "uic", "rcc"]:
        info = qt_tools.get(tool_name)
        if not isinstance(info, dict):
            continue
        tool_path = Path(str(info.get("path", "")))
        if not tool_path.exists():
            mismatches.append({"component": f"qt_tool.{tool_name}.path", "expected": str(info.get("path")), "actual": "missing"})
            continue
        actual_hash = sha256_file(tool_path)
        expected_hash = str(info.get("sha256", ""))
        if actual_hash != expected_hash:
            mismatches.append({"component": f"qt_tool.{tool_name}.sha256", "expected": expected_hash, "actual": actual_hash})
        actual_version = _query_command_text([str(tool_path), "-v"]) or ""
        actual_version = actual_version.splitlines()[0].strip() if actual_version else ""
        expected_version = str(info.get("version", ""))
        if actual_version != expected_version:
            mismatches.append({"component": f"qt_tool.{tool_name}.version", "expected": expected_version, "actual": actual_version})

    ok = len(mismatches) == 0
    return {
        "ok": ok,
        "mismatches": mismatches,
        "actual_hashes": actual,
    }


def thaw_capsule(capsule_path: Path, out_dir: Path, verify: bool = True, force: bool = False) -> dict[str, Any]:
    if not capsule_path.exists():
        raise FileNotFoundError(f"Capsule not found: {capsule_path}")
    if out_dir.exists() and not force:
        raise FileExistsError(f"Output directory already exists: {out_dir}")

    if verify:
        result = verify_capsule(capsule_path)
        if not result["ok"]:
            raise ValueError(f"Capsule verification failed: {result['mismatches']}")

    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(capsule_path, mode="r") as zf:
        graph_text = zf.read("graph.json").decode("utf-8")
        compdb_text = zf.read("compdb.json").decode("utf-8")
        config_norm_text = zf.read("config.normalized.json").decode("utf-8")

        (out_dir / "ngksgraph_graph.json").write_text(_normalize_newlines(graph_text), encoding="utf-8")
        (out_dir / "compile_commands.json").write_text(_normalize_newlines(compdb_text), encoding="utf-8")
        (out_dir / "config.normalized.json").write_text(_normalize_newlines(config_norm_text), encoding="utf-8")

        for name in ["capsule_meta.json", "hashes.json", "toolchain.json", "snapshot_ref.json"]:
            if name in zf.namelist():
                (out_dir / name).write_text(_normalize_newlines(zf.read(name).decode("utf-8")), encoding="utf-8")

    return {
        "ok": True,
        "out_dir": normalize_path(out_dir.resolve()),
    }
