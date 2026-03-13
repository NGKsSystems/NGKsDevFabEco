from __future__ import annotations

import ast
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .node_toolchain import detect_node_toolchain


def _tool_available(name: str) -> bool:
    return bool(shutil.which(name))


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def rank_routes(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    candidates: list[dict[str, Any]] = []

    ts_pkg = root / "app" / "ts_panel" / "package.json"
    if ts_pkg.is_file():
        decision = detect_node_toolchain(root, ts_pkg)
        manager = str(decision.get("selected_manager", "npm"))
        required_tools = ["node", manager]
        missing_tools = [tool for tool in required_tools if not _tool_available(tool)]
        factors = {
            "toolchain_availability_score": max(0, 100 - 50 * len(missing_tools)),
            "entrypoint_confidence_score": 95,
            "dependency_readiness_score": 90 if decision.get("reason") == "lockfile_detected" else 75,
            "backend_completeness_score": 88,
            "validation_readiness_score": 85,
            "risk_penalty": 10 * len(missing_tools),
        }
        final_score = (
            factors["toolchain_availability_score"] * 0.30
            + factors["entrypoint_confidence_score"] * 0.20
            + factors["dependency_readiness_score"] * 0.20
            + factors["backend_completeness_score"] * 0.15
            + factors["validation_readiness_score"] * 0.15
            - factors["risk_penalty"]
        )
        candidates.append(
            {
                "route_id": "node_ts_panel",
                "route_type": "node",
                "entry_evidence": [_safe_rel(ts_pkg, root)],
                "required_tools": required_tools,
                "present_tools": [t for t in required_tools if t not in missing_tools],
                "missing_tools": missing_tools,
                "confidence": 0.95,
                "viability": "high" if not missing_tools else "medium",
                "factors": factors,
                "final_score": round(final_score, 2),
                "selected": False,
                "rejection_reason": "",
            }
        )

    py_req = root / "app" / "python_workers" / "requirements.txt"
    py_root = root / "app" / "python_workers"
    py_files = list(py_root.rglob("*.py")) if py_root.is_dir() else []
    if py_req.is_file() or py_files:
        required_tools = ["python"]
        missing_tools = [tool for tool in required_tools if not _tool_available(tool)]
        factors = {
            "toolchain_availability_score": max(0, 100 - 60 * len(missing_tools)),
            "entrypoint_confidence_score": 82,
            "dependency_readiness_score": 78 if py_req.is_file() else 58,
            "backend_completeness_score": 70,
            "validation_readiness_score": 72,
            "risk_penalty": 12 * len(missing_tools),
        }
        final_score = (
            factors["toolchain_availability_score"] * 0.30
            + factors["entrypoint_confidence_score"] * 0.20
            + factors["dependency_readiness_score"] * 0.20
            + factors["backend_completeness_score"] * 0.15
            + factors["validation_readiness_score"] * 0.15
            - factors["risk_penalty"]
        )
        candidates.append(
            {
                "route_id": "python_workers",
                "route_type": "python",
                "entry_evidence": [_safe_rel(py_req, root)] if py_req.is_file() else ["app/python_workers/*.py"],
                "required_tools": required_tools,
                "present_tools": [t for t in required_tools if t not in missing_tools],
                "missing_tools": missing_tools,
                "confidence": 0.86,
                "viability": "high" if not missing_tools else "medium",
                "factors": factors,
                "final_score": round(final_score, 2),
                "selected": False,
                "rejection_reason": "",
            }
        )

    host_pro = root / "app" / "cpp_host" / "NGKsMediaLabHost.pro"
    if host_pro.is_file():
        required_tools = ["qmake", "cl", "link"]
        missing_tools = [tool for tool in required_tools if not _tool_available(tool)]
        factors = {
            "toolchain_availability_score": max(0, 100 - 30 * len(missing_tools)),
            "entrypoint_confidence_score": 88,
            "dependency_readiness_score": 66,
            "backend_completeness_score": 84,
            "validation_readiness_score": 60,
            "risk_penalty": 18 * len(missing_tools),
        }
        final_score = (
            factors["toolchain_availability_score"] * 0.30
            + factors["entrypoint_confidence_score"] * 0.20
            + factors["dependency_readiness_score"] * 0.20
            + factors["backend_completeness_score"] * 0.15
            + factors["validation_readiness_score"] * 0.15
            - factors["risk_penalty"]
        )
        candidates.append(
            {
                "route_id": "native_host_qt",
                "route_type": "native_qt",
                "entry_evidence": [_safe_rel(host_pro, root)],
                "required_tools": required_tools,
                "present_tools": [t for t in required_tools if t not in missing_tools],
                "missing_tools": missing_tools,
                "confidence": 0.79,
                "viability": "medium" if len(missing_tools) <= 1 else "low",
                "factors": factors,
                "final_score": round(final_score, 2),
                "selected": False,
                "rejection_reason": "",
            }
        )

    ranked = sorted(candidates, key=lambda item: (-item["final_score"], item["route_id"]))
    for index, candidate in enumerate(ranked):
        if index == 0:
            candidate["selected"] = True
        else:
            candidate["rejection_reason"] = f"lower_final_score_than_{ranked[0]['route_id']}"

    breakdown = []
    for candidate in ranked:
        breakdown.append(
            {
                "route_id": candidate["route_id"],
                **candidate["factors"],
                "final_score": candidate["final_score"],
            }
        )

    return {
        "repo_root": str(root),
        "ranking_method": "weighted_factor_scoring",
        "weights": {
            "toolchain_availability_score": 0.30,
            "entrypoint_confidence_score": 0.20,
            "dependency_readiness_score": 0.20,
            "backend_completeness_score": 0.15,
            "validation_readiness_score": 0.15,
            "risk_penalty": -1.0,
        },
        "route_candidates": ranked,
        "route_scoring_breakdown": breakdown,
        "selected_route": ranked[0]["route_id"] if ranked else "none",
    }


def _parse_requirements(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~]", line, maxsplit=1)[0].strip().lower().replace("-", "_")
        if name:
            out.add(name)
    return out


def infer_dependency_holes(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    holes: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    py_root = root / "app" / "python_workers"
    req_declared = _parse_requirements(py_root / "requirements.txt")
    local_modules = {p.stem.lower() for p in py_root.rglob("*.py")} if py_root.is_dir() else set()

    if py_root.is_dir():
        for py_file in py_root.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except Exception:
                continue
            for node in ast.walk(tree):
                mod = ""
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name.split(".")[0].lower()
                        if mod in stdlib or mod in local_modules:
                            continue
                        if mod not in req_declared:
                            holes.append(
                                {
                                    "dependency_name": mod,
                                    "language": "python",
                                    "evidence_type": "import",
                                    "evidence_files": [_safe_rel(py_file, root)],
                                    "evidence_lines": [int(getattr(node, "lineno", 0) or 0)],
                                    "owning_component": "app/python_workers",
                                    "declared_status": "missing",
                                    "inferred_required_status": "required",
                                    "confidence": "high",
                                    "confidence_reason": "direct_import_without_matching_requirement",
                                    "recommended_contract_fix": {
                                        "file": "app/python_workers/requirements.txt",
                                        "action": "add_dependency",
                                        "value": mod,
                                    },
                                }
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module.split(".")[0].lower()
                    if mod in stdlib or mod in local_modules:
                        continue
                    if mod not in req_declared:
                        holes.append(
                            {
                                "dependency_name": mod,
                                "language": "python",
                                "evidence_type": "import_from",
                                "evidence_files": [_safe_rel(py_file, root)],
                                "evidence_lines": [int(getattr(node, "lineno", 0) or 0)],
                                "owning_component": "app/python_workers",
                                "declared_status": "missing",
                                "inferred_required_status": "required",
                                "confidence": "high",
                                "confidence_reason": "direct_from_import_without_matching_requirement",
                                "recommended_contract_fix": {
                                    "file": "app/python_workers/requirements.txt",
                                    "action": "add_dependency",
                                    "value": mod,
                                },
                            }
                        )

    ts_pkg = root / "app" / "ts_panel" / "package.json"
    if ts_pkg.is_file():
        try:
            pkg = json.loads(ts_pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            pkg = {}
        declared = set()
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            value = pkg.get(key)
            if isinstance(value, dict):
                declared.update(name.lower() for name in value.keys())
        src_root = ts_pkg.parent
        pattern = re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)")
        for source in src_root.rglob("*.ts"):
            text = source.read_text(encoding="utf-8", errors="ignore")
            for idx, line in enumerate(text.splitlines(), start=1):
                for match in pattern.finditer(line):
                    mod = (match.group(1) or match.group(2) or "").strip()
                    if not mod or mod.startswith(".") or mod.startswith("/"):
                        continue
                    top = mod.split("/")[0].lower()
                    if top.startswith("@") and "/" in mod:
                        top = "/".join(mod.split("/")[:2]).lower()
                    if top not in declared:
                        holes.append(
                            {
                                "dependency_name": top,
                                "language": "typescript",
                                "evidence_type": "import",
                                "evidence_files": [_safe_rel(source, root)],
                                "evidence_lines": [idx],
                                "owning_component": "app/ts_panel",
                                "declared_status": "missing",
                                "inferred_required_status": "required",
                                "confidence": "high",
                                "confidence_reason": "direct_module_import_without_package_json_declaration",
                                "recommended_contract_fix": {
                                    "file": "app/ts_panel/package.json",
                                    "action": "add_dependency",
                                    "value": top,
                                },
                            }
                        )

    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for hole in holes:
        key = (hole["dependency_name"], hole["language"], hole["owning_component"])
        if key not in unique:
            unique[key] = hole
        else:
            existing = unique[key]
            existing["evidence_files"] = sorted(set(existing["evidence_files"] + hole["evidence_files"]))
            existing["evidence_lines"] = sorted(set(existing["evidence_lines"] + hole["evidence_lines"]))

    final_holes = list(unique.values())
    for hole in final_holes:
        traces.append(
            {
                "dependency_name": hole["dependency_name"],
                "trace_chain": [
                    {"type": hole["evidence_type"], "files": hole["evidence_files"], "lines": hole["evidence_lines"]},
                    {"type": "declaration_check", "status": hole["declared_status"], "component": hole["owning_component"]},
                    {"type": "inference", "result": hole["inferred_required_status"], "confidence": hole["confidence"]},
                ],
            }
        )

    return {
        "repo_root": str(root),
        "holes": final_holes,
        "trace_report": traces,
    }
