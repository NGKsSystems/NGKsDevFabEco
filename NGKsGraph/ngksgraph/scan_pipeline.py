from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys

from ngksgraph.authority.authority_engine import evaluate_authority
from ngksgraph.classify.evidence_classifier import classify
from ngksgraph.classify.trust_assigner import trust_for_evidence
from ngksgraph.contradiction.contradiction_engine import detect_contradictions
from ngksgraph.core.enums import PreflightStatus
from ngksgraph.core.hashing import sha256_json
from ngksgraph.core.io_json import read_json, write_json, write_text
from ngksgraph.core.models import ScanRunResult
from ngksgraph.core.timestamps import now_utc
from ngksgraph.detect.detection_rules_engine import evaluate_detection_rules
from ngksgraph.detect.framework_detector import detect_frameworks
from ngksgraph.detect.language_detector import SOURCE_EXTENSION_TO_LANGUAGE, confidence, detect_language_for_path, primary_project_type
from ngksgraph.detect.manifest_detector import detect_build_system, detect_manifest_hints, detect_package_ecosystem
from ngksgraph.detect.monorepo_splitter import split_subprojects
from ngksgraph.detect.repo_detection_engine import walk_repo
from ngksgraph.env.env_contract import build_env_contract
from ngksgraph.explain.markdown_renderer import render_summary
from ngksgraph.explain.summary_builder import build_summary_data
from ngksgraph.imply.implication_engine import derive_requirements
from ngksgraph.plan.native_plan_builder import build_native_plan
from ngksgraph.probe.file_walker import iter_repo_files, relative
from ngksgraph.probe.ownership_probe import ownership_for_path
from ngksgraph.probe.path_classifier import directory_hint
from ngksgraph.probe.tool_probe import probe_tools
from ngksgraph.stale.stale_guard import evaluate_stale_risk
from ngksgraph.msvc import bootstrap_msvc


def _scan_id() -> str:
    return f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def _ensure_project_venv(repo_root: Path) -> tuple[bool, str]:
    venv_dir = repo_root / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe" if sys.platform.startswith("win") else venv_dir / "bin" / "python"
    if venv_python.exists():
        return False, ""
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        return False, detail
    return True, ""


def _write_contract_artifacts(repo_root: Path, out_dir: Path, native_plan: dict) -> tuple[dict, dict]:
    contract_dir = (repo_root / "_artifacts" / "graph_contract").resolve()
    contract_dir.mkdir(parents=True, exist_ok=True)
    contract_path = contract_dir / "native_contract.json"

    previous_contract = read_json(contract_path) if contract_path.exists() else {}
    current_contract = {
        "repo_root": str(repo_root),
        "version": "1",
        "native_plan_hash": sha256_json(native_plan),
        "native_plan": native_plan,
        "timestamp_utc": now_utc(),
    }

    plan_diff = {
        "changed": previous_contract.get("native_plan_hash") != current_contract["native_plan_hash"],
        "previous_hash": previous_contract.get("native_plan_hash", ""),
        "current_hash": current_contract["native_plan_hash"],
        "drift": {
            "target_count_previous": len(previous_contract.get("native_plan", {}).get("subprojects", []) or []),
            "target_count_current": len(native_plan.get("subprojects", []) or []),
            "added_subprojects": sorted(
                {
                    str(item.get("subproject_id", ""))
                    for item in (native_plan.get("subprojects", []) or [])
                    if str(item.get("subproject_id", ""))
                }
                - {
                    str(item.get("subproject_id", ""))
                    for item in (previous_contract.get("native_plan", {}).get("subprojects", []) or [])
                    if str(item.get("subproject_id", ""))
                }
            ),
            "removed_subprojects": sorted(
                {
                    str(item.get("subproject_id", ""))
                    for item in (previous_contract.get("native_plan", {}).get("subprojects", []) or [])
                    if str(item.get("subproject_id", ""))
                }
                - {
                    str(item.get("subproject_id", ""))
                    for item in (native_plan.get("subprojects", []) or [])
                    if str(item.get("subproject_id", ""))
                }
            ),
        },
    }

    write_json(contract_path, current_contract)
    write_json(out_dir / "native_contract.json", current_contract)
    write_json(out_dir / "plan_diff.json", plan_diff)
    return current_contract, plan_diff


def run_scan(
    repo_root: Path,
    out_dir: Path,
    authority_mode: str = "native_ngks",
    bootstrap_venv: bool = False,
    bootstrap_msvc_env: bool = False,
) -> ScanRunResult:
    repo_root = repo_root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scan_id = _scan_id()

    # Run comprehensive repo detection
    detection_result = walk_repo(repo_root)

    files_seen: list[dict[str, object]] = []
    file_rel_paths: list[str] = []
    classified_items: list[dict[str, object]] = []
    directories_seen: list[dict[str, str]] = []
    seen_dirs: set[str] = set()

    for path in iter_repo_files(repo_root):
        rel_path = relative(path, repo_root)
        file_rel_paths.append(rel_path)
        ext = path.suffix.lower()
        stat = path.stat()

        files_seen.append(
            {
                "path": rel_path,
                "kind": "file",
                "extension": ext,
                "size_bytes": int(stat.st_size),
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

        for parent in path.relative_to(repo_root).parents:
            if str(parent) in {".", ""}:
                continue
            p = str(parent).replace("\\", "/")
            if p in seen_dirs:
                continue
            seen_dirs.add(p)
            directories_seen.append({"path": p, "classification_hint": directory_hint(p)})

        file_name = path.name
        is_source_ext = ext in SOURCE_EXTENSION_TO_LANGUAGE
        evidence_type, used_for_detection = classify(rel_path, file_name, ext, is_source_ext)
        ownership = ownership_for_path(rel_path)
        trust_class = trust_for_evidence(evidence_type, ownership)
        classified_items.append(
            {
                "path": rel_path,
                "evidence_type": evidence_type,
                "ownership": ownership,
                "trust_class": trust_class,
                "used_for_detection": used_for_detection,
            }
        )

    language_scores = detection_result.language_scores
    extension_hits = detection_result.extension_hits
    top_score = next(iter(language_scores.values()), 0) if language_scores else 0

    source_paths = {item["path"] for item in classified_items if item["evidence_type"] == "source"}
    frameworks = detect_frameworks(repo_root, source_paths)
    detection_rule_hits = evaluate_detection_rules(repo_root)
    detection_rule_ids = {str(item.get("id", "")) for item in detection_rule_hits}
    if "detect_qt6_cmake" in detection_rule_ids or "detect_qt6_source" in detection_rule_ids:
        if not any(str(item.get("name", "")) == "Qt6" for item in frameworks):
            matched_by: list[str] = []
            for hit in detection_rule_hits:
                if str(hit.get("id", "")) in {"detect_qt6_cmake", "detect_qt6_source"}:
                    matched_by.extend([str(ev) for ev in hit.get("matched_by", [])])
            frameworks.append({"name": "Qt6", "confidence": 0.8, "evidence": sorted(set(matched_by))[:8]})
    framework_names = {item["name"] for item in frameworks}

    languages = [
        {
            "name": language,
            "confidence": confidence(score, top_score),
            "evidence": [f"extension_count={extension_hits.get(language, 0)}"],
        }
        for language, score in list(language_scores.items())[:8]
    ]

    package_ecosystems = [{"name": name, "confidence": 0.9} for name in detection_result.package_ecosystems]
    subprojects = split_subprojects(repo_root, file_rel_paths)

    # Evaluate authority and filter build systems before creating detected_stack
    authority = evaluate_authority(repo_root, authority_mode)

    # Filter build systems based on authority mode
    def _authoritative_build_systems(all_systems: list[str], authority_items: list[dict]) -> list[str]:
        if authority_mode == "foreign_authoritative":
            # In foreign authoritative mode, include detected systems that are allowed to be authoritative
            result = []
            for system in all_systems:
                # Map build system names to their corresponding authority file names
                file_map = {
                    "CMake": "CMakeLists.txt",
                    "Make": "Makefile",
                    "Ninja": "build.ninja",
                    # Add more mappings as needed
                }
                auth_file = file_map.get(system, system)
                # Find the corresponding authority item
                auth_item = next((item for item in authority_items if item["tool_or_file"] == auth_file), None)
                if auth_item and auth_item.get("execution_allowed", False):
                    result.append(system)
            return result
        elif authority_mode in {"native_ngks", "compatibility_only", "import_foreign"}:
            # In native modes, only NGKsGraph is authoritative
            return ["NGKsGraph"]
        return all_systems  # fallback

    filtered_build_systems = _authoritative_build_systems(detection_result.build_systems, authority["items"])

    if bootstrap_venv:
        _, venv_err = _ensure_project_venv(repo_root)
        if venv_err:
            return ScanRunResult(out_dir=out_dir, status=str(PreflightStatus.FAIL_CLOSED), blockers=(f"venv bootstrap failed: {venv_err}",))

    msvc_env_active_override = False
    msvc_bootstrap_error = ""
    if bootstrap_msvc_env and sys.platform.startswith("win"):
        boot = bootstrap_msvc()
        if boot.success:
            msvc_env_active_override = True
        else:
            msvc_bootstrap_error = str(boot.error or "unknown bootstrap failure")

    def _is_under_root(rel_path: str, root_path: str) -> bool:
        if root_path in {"", "."}:
            return True
        normalized = rel_path.replace("\\", "/")
        prefix = root_path.rstrip("/") + "/"
        return normalized == root_path or normalized.startswith(prefix)

    def _frameworks_for_root(root_path: str) -> list[dict[str, object]]:
        scoped: list[dict[str, object]] = []
        for fw in frameworks:
            evidence = list(fw.get("evidence", []))
            root_evidence = [ev for ev in evidence if _is_under_root(str(ev), root_path)]
            if root_evidence:
                scoped.append({**fw, "evidence": root_evidence[:8]})
            elif root_path in {"", "."}:
                scoped.append(dict(fw))
        return scoped

    def _languages_for_root(root_path: str) -> list[dict[str, object]]:
        # For now, return main languages since comprehensive detection doesn't split by subproject
        return languages

    def _ecosystems_for_root(root_path: str) -> list[dict[str, object]]:
        scoped_names: set[str] = set()
        for rel in detection_result.manifests_found:
            if not _is_under_root(rel, root_path):
                continue
            eco = detect_package_ecosystem(Path(rel).name)
            if eco:
                scoped_names.add(eco)
        return [{"name": name, "confidence": 0.9} for name in sorted(scoped_names)]

    detected_stack = {
        "repo_root": str(repo_root),
        "detection_precedence": [
            "manifests_and_build_files",
            "lockfiles",
            "project_files",
            "directory_conventions",
            "extensions",
            "content_sniffing",
        ],
        "detection_rule_hits": detection_rule_hits,
        "build_systems": filtered_build_systems,
        "subprojects": [
            {
                "subproject_id": sp["subproject_id"],
                "root_path": sp["root_path"],
                "project_type": primary_project_type({item["name"]: int(float(item["confidence"]) * 100) for item in (_languages_for_root(sp["root_path"]) or languages)}),
                "languages": _languages_for_root(sp["root_path"]) or languages,
                "frameworks": _frameworks_for_root(sp["root_path"]) or frameworks,
                "package_ecosystems": _ecosystems_for_root(sp["root_path"]) or package_ecosystems,
            }
            for sp in subprojects
        ],
    }

    language_names = {item["name"] for item in languages}
    manifest_names = {Path(item).name for item in detection_result.manifests_found}
    requirements = derive_requirements(framework_names, language_names, manifest_names)

    stale_risk = evaluate_stale_risk(repo_root)
    contradictions = detect_contradictions(repo_root, detection_result.manifests_found, source_paths)

    tools = probe_tools()
    env_contract = build_env_contract(repo_root, requirements, tools, msvc_env_active_override=msvc_env_active_override)
    required_flags = env_contract["subprojects"][0].get("required_flags", [])
    native_plan = build_native_plan(repo_root, source_paths, framework_names, required_flags)

    blockers: list[str] = []
    high_contradictions = [
        item for item in contradictions.get("contradictions", []) if str(item.get("severity", "")).lower() == "high"
    ]
    if high_contradictions:
        blockers.append("high-severity contradictions detected")
    missing_tools = env_contract["subprojects"][0].get("missing", [])
    if missing_tools:
        blockers.append(f"missing required tools: {', '.join(sorted(missing_tools))}")
    missing_env = env_contract["subprojects"][0].get("missing_env", [])
    if missing_env:
        blockers.append(f"missing required env: {', '.join(sorted(missing_env))}")
    required_env = env_contract["subprojects"][0].get("required_env", [])
    if msvc_bootstrap_error and any(str(item).strip().lower() == "vcvars active" for item in required_env):
        blockers.append(f"msvc bootstrap failed: {msvc_bootstrap_error}")

    status = PreflightStatus.PASS
    if blockers:
        status = PreflightStatus.FAIL_CLOSED
    elif stale_risk.get("stale_items"):
        status = PreflightStatus.PASS_WITH_WARNINGS

    probe_facts = {
        "repo_root": str(repo_root),
        "scan_id": scan_id,
        "timestamp_utc": now_utc(),
        "files_seen": sorted(files_seen, key=lambda item: str(item["path"])),
        "directories_seen": sorted(directories_seen, key=lambda item: str(item["path"])),
        "tools_found_on_system": [
            {"tool": tool, "found": bool(path), "path": str(path or "")}
            for tool, path in sorted(tools.items(), key=lambda item: item[0])
        ],
    }

    classified_evidence = {
        "repo_root": str(repo_root),
        "classified_items": sorted(classified_items, key=lambda item: str(item["path"])),
    }

    downstream_requirements = {
        "repo_root": str(repo_root),
        "requirements": requirements,
        "status": str(status),
    }

    summary_data = build_summary_data(
        scan_id=scan_id,
        repo_root=str(repo_root),
        timestamp_utc=now_utc(),
        authority_mode=authority_mode,
        status=str(status),
        project_type=primary_project_type(language_scores),
        top_languages=list(language_scores.keys())[:5],
        frameworks=sorted(framework_names),
        ecosystems=sorted([eco["name"] for eco in package_ecosystems]),
        subprojects=[item["root_path"] for item in subprojects],
        requirement_count=len(requirements),
        required_standards=sorted(
            {
                str(value)
                for req in requirements
                for value in req.get("required_minimums", {}).values()
                if str(value).strip()
            }
        ),
        required_tools=sorted({tool for req in requirements for tool in req.get("required_tools", [])}),
        required_flags=list(required_flags),
        required_env=list(env_contract["subprojects"][0].get("required_env", [])),
        stale_count=len(stale_risk.get("stale_items", [])),
        stale_high_count=int(stale_risk.get("summary", {}).get("high", 0)),
        ignored_generated_count=sum(1 for item in classified_items if str(item.get("evidence_type", "")) == "foreign_generated"),
        ignored_blocked_foreign_count=sum(1 for item in classified_items if str(item.get("trust_class", "")) == "blocked_stale_risk"),
        contradiction_count=len(contradictions.get("contradictions", [])),
        trust_issue_count=sum(
            1
            for item in classified_items
            if str(item.get("trust_class", "")) in {"foreign_authored_hint", "foreign_generated_hint", "blocked_stale_risk"}
        ),
        missing_tools=list(missing_tools),
        missing_env=list(missing_env),
        missing_flags=[],
        unsupported_native_paths=[
            str(sp.get("subproject_id", "root"))
            for sp in native_plan.get("subprojects", [])
            if not bool(sp.get("execution_support", {}).get("native_supported", True))
        ],
        blockers=blockers,
    )

    write_json(out_dir / "01_probe_facts.json", probe_facts)
    write_json(out_dir / "02_classified_evidence.json", classified_evidence)
    write_json(out_dir / "03_detected_stack.json", detected_stack)
    write_json(out_dir / "04_downstream_requirements.json", downstream_requirements)
    write_json(out_dir / "05_build_authority.json", authority)
    write_json(out_dir / "06_stale_risk_report.json", stale_risk)
    write_json(out_dir / "07_contradictions.json", contradictions)
    write_json(out_dir / "08_environment_contract.json", env_contract)
    write_json(out_dir / "09_native_plan.json", native_plan)
    write_text(out_dir / "SUMMARY.md", render_summary(summary_data))

    _write_contract_artifacts(repo_root, out_dir, native_plan)

    return ScanRunResult(out_dir=out_dir, status=str(status), blockers=tuple(blockers))
