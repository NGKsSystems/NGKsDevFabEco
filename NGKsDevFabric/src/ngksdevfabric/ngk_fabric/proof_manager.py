from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TS_RE = re.compile(r"(20\d{6}_\d{6})")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp_from_name(name: str) -> str | None:
    match = _TS_RE.search(name)
    if not match:
        return None
    raw = match.group(1)
    try:
        dt = datetime.strptime(raw, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def _infer_run_type(run_id: str) -> str:
    lowered = run_id.lower()
    if "onboarding_build" in lowered:
        return "onboarding_build"
    if "stress_refine" in lowered:
        return "stress_refine"
    if "stress_routes_deps_conflicts" in lowered:
        return "stress_routes_deps_conflicts"
    if "stress_routes" in lowered:
        return "stress_routes"
    if "cert" in lowered:
        return "certification_suite"
    if lowered.startswith("devfabric_run_run_"):
        return "analysis_only"
    return "analysis_only"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_gate(bundle: Path) -> str:
    summary_md = bundle / "18_summary.md"
    if summary_md.is_file():
        for line in summary_md.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "final gate:" in line.lower():
                return line.split(":", 1)[1].strip().upper()

    summary_txt = bundle / "99_summary.txt"
    if summary_txt.is_file():
        lines = summary_txt.read_text(encoding="utf-8", errors="ignore").splitlines()
        values = {}
        for line in lines:
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        if values.get("exit_code") == "0" and values.get("build_success") == "true":
            return "PASS"
        if values.get("exit_code") == "0":
            return "PARTIAL"
        return "FAIL"

    return "UNKNOWN"


def _extract_route(bundle: Path) -> str:
    ranking = _read_json(bundle / "05_route_ranking.json")
    if ranking and isinstance(ranking.get("selected_route"), str):
        return str(ranking["selected_route"])

    summary_md = bundle / "18_summary.md"
    if summary_md.is_file():
        for line in summary_md.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "selected route" in line.lower():
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()

    summary_txt = bundle / "99_summary.txt"
    if summary_txt.is_file():
        for line in summary_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("build_system="):
                return line.split("=", 1)[1].strip()
    return "unknown"


def _extract_dependency_holes(bundle: Path) -> int:
    dep = _read_json(bundle / "09_dependency_inference_report.json")
    if dep and isinstance(dep.get("holes"), list):
        return len(dep["holes"])
    return 0


def _extract_conflicts(bundle: Path) -> bool:
    conflict = _read_json(bundle / "14_conflict_outcome.json")
    if conflict and isinstance(conflict.get("conflict_detected"), bool):
        return bool(conflict["conflict_detected"])
    conflict = _read_json(bundle / "conflict_outcome.json")
    if conflict and isinstance(conflict.get("conflict_detected"), bool):
        return bool(conflict["conflict_detected"])
    return False


def _extract_weaknesses(bundle: Path) -> list[str]:
    summary_md = bundle / "18_summary.md"
    if not summary_md.is_file():
        return []
    lines = summary_md.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if "top weaknesses" in lower:
            capture = True
            continue
        if capture:
            if lower.startswith("- final gate"):
                break
            if stripped.startswith("1.") or stripped.startswith("2.") or stripped.startswith("3.") or stripped.startswith("4.") or stripped.startswith("5."):
                out.append(stripped)
    return out


def _canonical_bundle_path(*, runs_dir: Path, run_id: str) -> Path:
    return (runs_dir / run_id).resolve()


def _canonical_zip_path(*, runs_dir: Path, run_id: str) -> Path:
    return (runs_dir / f"{run_id}.zip").resolve()


def _create_run_zip(*, bundle_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(bundle_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(bundle_dir)
            zf.write(file_path, arcname.as_posix())


def _update_latest_operator_zip(*, canonical_zip: Path, hub_root: Path) -> Path:
    latest_operator_zip = (hub_root / "latest_proof.zip").resolve()
    shutil.copy2(canonical_zip, latest_operator_zip)
    return latest_operator_zip


def _write_latest(latest_dir: Path, metadata: dict[str, Any]) -> None:
    latest_dir.mkdir(parents=True, exist_ok=True)
    pointer = {
        "run_id": metadata["run_id"],
        "proof_folder": metadata["proof_folder"],
        "proof_zip": metadata["proof_zip"],
        "latest_proof_zip": metadata["latest_proof_zip"],
        "timestamp": metadata["timestamp"],
        "summary_file": metadata["summary_file"],
        "gate": metadata["gate"],
    }
    (latest_dir / "latest_run_pointer.json").write_text(json.dumps(pointer, indent=2), encoding="utf-8")

    latest_summary_json = {
        "run_id": metadata["run_id"],
        "run_type": metadata["run_type"],
        "timestamp": metadata["timestamp"],
        "gate": metadata["gate"],
        "route_selected": metadata["route_selected"],
        "dependency_holes_detected": metadata["dependency_holes_detected"],
        "conflicts_detected": metadata["conflicts_detected"],
        "key_weaknesses": metadata["key_weaknesses"],
        "proof_folder": metadata["proof_folder"],
        "proof_zip": metadata["proof_zip"],
        "latest_proof_zip": metadata["latest_proof_zip"],
        "summary_file": metadata["summary_file"],
    }
    (latest_dir / "latest_summary.json").write_text(json.dumps(latest_summary_json, indent=2), encoding="utf-8")

    lines = [
        "# Latest DevFabEco Run Summary",
        "",
        f"- run_id: {metadata['run_id']}",
        f"- run_type: {metadata['run_type']}",
        f"- timestamp: {metadata['timestamp']}",
        f"- gate: {metadata['gate']}",
        f"- route_selected: {metadata['route_selected']}",
        f"- dependency_holes_detected: {metadata['dependency_holes_detected']}",
        f"- conflicts_detected: {str(metadata['conflicts_detected']).lower()}",
        f"- proof_folder: {metadata['proof_folder']}",
        f"- proof_zip: {metadata['proof_zip']}",
        f"- latest_proof_zip: {metadata['latest_proof_zip']}",
        f"- summary_file: {metadata['summary_file']}",
    ]
    if metadata["key_weaknesses"]:
        lines.append("- key_weaknesses:")
        for item in metadata["key_weaknesses"]:
            lines.append(f"  - {item}")
    (latest_dir / "latest_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_index(index_dir: Path, metadata: dict[str, Any]) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "runs_index.json"
    current = {"runs": []}
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("runs"), list):
                current = loaded
        except (OSError, ValueError, TypeError):
            pass

    runs: list[dict[str, Any]] = [entry for entry in current.get("runs", []) if isinstance(entry, dict)]
    normalized_runs: list[dict[str, Any]] = []
    for entry in runs:
        run_id = str(entry.get("run_id", "")).strip()
        timestamp = str(entry.get("timestamp", "")).strip()
        run_type = str(entry.get("run_type", "analysis_only")).strip() or "analysis_only"
        gate = str(entry.get("gate", "UNKNOWN")).strip() or "UNKNOWN"
        proof_folder = str(entry.get("proof_folder", "")).strip()
        if not proof_folder:
            proof_folder = str(entry.get("proof_path", "")).strip()
        if proof_folder and not Path(proof_folder).is_absolute() and proof_folder.startswith("_proof/"):
            proof_folder = str((index_dir.resolve().parent.parent / proof_folder[len("_proof/"):]).resolve())
        proof_zip = str(entry.get("proof_zip", "")).strip()
        if not proof_zip and proof_folder:
            proof_zip = str(Path(proof_folder).with_suffix(".zip"))
        latest_proof_zip = str(entry.get("latest_proof_zip", "")).strip()
        if not latest_proof_zip:
            latest_proof_zip = str((index_dir.resolve().parent.parent / "latest_proof.zip").resolve())
        summary_file = str(entry.get("summary_file", "")).strip()
        if not summary_file:
            summary_file = str(entry.get("summary", "")).strip()
        if summary_file and not Path(summary_file).is_absolute() and summary_file.startswith("_proof/"):
            summary_file = str((index_dir.resolve().parent.parent / summary_file[len("_proof/"):]).resolve())
        normalized_runs.append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "run_type": run_type,
                "gate": gate,
                "proof_folder": proof_folder,
                "proof_zip": proof_zip,
                "latest_proof_zip": latest_proof_zip,
                "summary_file": summary_file,
            }
        )
    runs = normalized_runs
    runs = [entry for entry in runs if entry.get("run_id") != metadata["run_id"]]
    runs.append(
        {
            "run_id": metadata["run_id"],
            "timestamp": metadata["timestamp"],
            "run_type": metadata["run_type"],
            "gate": metadata["gate"],
            "proof_folder": metadata["proof_folder"],
            "proof_zip": metadata["proof_zip"],
            "latest_proof_zip": metadata["latest_proof_zip"],
            "summary_file": metadata["summary_file"],
        }
    )
    runs = sorted(runs, key=lambda item: str(item.get("timestamp", "")), reverse=True)
    index_obj = {"runs": runs}
    index_path.write_text(json.dumps(index_obj, indent=2), encoding="utf-8")

    md_lines = [
        "# DevFabEco Runs Index",
        "",
        "| Timestamp | Run | Type | Gate | Proof Folder | Proof Zip | Latest Proof Zip | Summary File |",
        "| --------- | --- | ---- | ---- | ------------ | --------- | ---------------- | ------------ |",
    ]
    for row in runs:
        md_lines.append(
            f"| {row.get('timestamp','')} | {row.get('run_id','')} | {row.get('run_type','')} | {row.get('gate','')} | {row.get('proof_folder','')} | {row.get('proof_zip','')} | {row.get('latest_proof_zip','')} | {row.get('summary_file','')} |"
        )
    (index_dir / "runs_index.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def register_proof_bundle(*, bundle_path: Path, devfab_root: Path) -> dict[str, Any]:
    src = bundle_path.resolve()
    if not src.exists() or not src.is_dir():
        return {"status": "skipped", "reason": "bundle_missing", "bundle": str(src)}

    hub_root = (devfab_root.resolve().parent / "_proof").resolve()
    runs_dir = hub_root / "runs"
    latest_dir = hub_root / "latest"
    index_dir = hub_root / "index"
    runs_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    run_id = src.name
    dest = runs_dir / run_id
    if src != dest:
        if not dest.exists():
            shutil.copytree(src, dest)
        else:
            marker = (dest / ".registered_from").read_text(encoding="utf-8", errors="ignore") if (dest / ".registered_from").is_file() else ""
            if marker.strip() != str(src):
                suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = runs_dir / f"{run_id}_{suffix}"
                run_id = dest.name
                shutil.copytree(src, dest)
    (dest / ".registered_from").write_text(str(src), encoding="utf-8")

    timestamp = _parse_timestamp_from_name(run_id) or datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat()
    canonical_folder = _canonical_bundle_path(runs_dir=runs_dir, run_id=run_id)
    canonical_zip = _canonical_zip_path(runs_dir=runs_dir, run_id=run_id)
    _create_run_zip(bundle_dir=canonical_folder, zip_path=canonical_zip)
    latest_proof_zip = _update_latest_operator_zip(canonical_zip=canonical_zip, hub_root=hub_root)

    summary_md = dest / "18_summary.md"
    summary_file = summary_md if summary_md.is_file() else (dest / "99_summary.txt")

    metadata = {
        "run_id": run_id,
        "timestamp": timestamp,
        "run_type": _infer_run_type(run_id),
        "gate": _extract_gate(dest),
        "route_selected": _extract_route(dest),
        "dependency_holes_detected": _extract_dependency_holes(dest),
        "conflicts_detected": _extract_conflicts(dest),
        "key_weaknesses": _extract_weaknesses(dest),
        "proof_folder": str(canonical_folder),
        "proof_zip": str(canonical_zip),
        "latest_proof_zip": str(latest_proof_zip),
        "summary_file": str(summary_file.resolve()) if summary_file.exists() else "",
        "registered_at": _now_iso(),
    }

    _write_latest(latest_dir, metadata)
    _write_index(index_dir, metadata)
    return {"status": "ok", **metadata}
