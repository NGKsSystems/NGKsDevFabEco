from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import platform
from pathlib import Path
import shutil
import traceback
from time import perf_counter
from typing import Any, Callable

from ngksgraph import __version__
from ngksgraph.build import configure_project
from ngksgraph.capsule import freeze_capsule, verify_capsule
from ngksgraph.compdb_contract import compdb_hash, load_compdb, validate_compdb
from ngksgraph.graph_contract import (
    compute_structural_graph_hash,
    expected_compile_units,
    expected_link_inputs,
    validate_graph_integrity,
    validate_profile_parity,
)
from ngksgraph.log import write_json, write_text
from ngksgraph.torture_project import GeneratedProject, gen_project


class SelftestFailure(RuntimeError):
    def __init__(self, message: str, repro_path: str = "") -> None:
        super().__init__(message)
        self.repro_path = repro_path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _hashes(configured: dict[str, Any]) -> tuple[str, str]:
    hashes = configured["snapshot_info"]["hashes"]
    return hashes["graph_hash"], hashes["compdb_hash"]


def _generator_fps(configured: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {"moc": {}, "uic": {}, "rcc": {}}
    for node in configured["qt_result"].generator_nodes:
        out.setdefault(node.kind, {})[node.input] = node.fingerprint
    return out


def _cleanup_project(path: Path, keep: bool) -> None:
    if keep:
        return
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _run_case(
    *,
    name: str,
    seed: int,
    timeout: int,
    log_path: Path,
    case_fn: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = perf_counter()
    failure: dict[str, Any] | None = None
    details: dict[str, Any] = {}
    passed = True

    try:
        details = case_fn() or {}
    except Exception as exc:
        passed = False
        details = {
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        repro = getattr(exc, "repro_path", "")
        if repro:
            details["repro_path"] = repro

    elapsed_ms = int((perf_counter() - started) * 1000)
    if passed and elapsed_ms > timeout * 1000:
        passed = False
        details = {
            "error": f"TIMEOUT: scenario exceeded {timeout}s",
            "traceback": "",
            **details,
        }

    lines = [
        f"name={name}",
        f"seed={seed}",
        f"pass={passed}",
        f"ms={elapsed_ms}",
    ]
    for key in sorted(details.keys()):
        value = details[key]
        if isinstance(value, (dict, list)):
            lines.append(f"{key}={value}")
        else:
            lines.append(f"{key}={value}")
    write_text(log_path, "\n".join(lines) + "\n")

    result = {
        "name": name,
        "seed": seed,
        "pass": passed,
        "ms": elapsed_ms,
    }

    if not passed:
        failure = {
            "name": name,
            "seed": seed,
            "error": str(details.get("error", "unknown failure")),
            "repro_path": str(details.get("repro_path", "")),
            "log_path": str(log_path),
        }
    return result, failure


def _scenario_determinism_core(
    projects_dir: Path,
    seed: int,
    scale: int,
    keep: bool,
) -> dict[str, Any]:
    project = gen_project(
        projects_dir,
        seed=seed,
        qobject_headers=scale,
        ui_files=1,
        qrc_files=1,
    )
    first = configure_project(project.repo_root, project.config_path)
    second = configure_project(project.repo_root, project.config_path)

    hash_a = _hashes(first)
    hash_b = _hashes(second)
    if hash_a != hash_b:
        raise AssertionError("configure hashes differ across repeated runs")

    fp_a = _generator_fps(first)
    fp_b = _generator_fps(second)
    if fp_a != fp_b:
        raise AssertionError("generator fingerprints differ across repeated runs")

    details = {
        "repro_path": str(project.repo_root),
        "graph_hash": hash_a[0],
        "compdb_hash": hash_a[1],
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_qt_generators(
    projects_dir: Path,
    seed: int,
    scale: int,
    keep: bool,
) -> dict[str, Any]:
    project = gen_project(
        projects_dir,
        seed=seed,
        qobject_headers=scale,
        ui_files=2,
        qrc_files=1,
    )
    configured = configure_project(project.repo_root, project.config_path)
    nodes = configured["qt_result"].generator_nodes

    moc_nodes = [n for n in nodes if n.kind == "moc"]
    uic_nodes = [n for n in nodes if n.kind == "uic"]
    rcc_nodes = [n for n in nodes if n.kind == "rcc"]

    if len(moc_nodes) != scale:
        raise AssertionError(f"expected {scale} moc nodes, got {len(moc_nodes)}")
    if not uic_nodes:
        raise AssertionError("expected at least one uic node")
    if not rcc_nodes:
        raise AssertionError("expected at least one rcc node")

    for node in moc_nodes + uic_nodes + rcc_nodes:
        if not Path(node.output).exists():
            raise AssertionError(f"missing generated output: {node.output}")

    details = {
        "repro_path": str(project.repo_root),
        "moc_count": len(moc_nodes),
        "uic_count": len(uic_nodes),
        "rcc_count": len(rcc_nodes),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_paths_with_spaces(projects_dir: Path, seed: int, keep: bool) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, path_with_spaces=True, mixed_slashes=True, qobject_headers=8)
    configured = configure_project(project.repo_root, project.config_path)

    compdb = configured["compdb"]
    app_cmds = [entry["command"] for entry in compdb if "app_main.cpp" in entry["file"]]
    if not app_cmds:
        raise AssertionError("expected app compile command in compile_commands")
    if not any('"src/app/space dir/app_main.cpp"' in cmd for cmd in app_cmds):
        raise AssertionError("compile command does not quote source path containing spaces")

    details = {
        "repro_path": str(project.repo_root),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_capsule_integrity(
    projects_dir: Path,
    capsules_dir: Path,
    seed: int,
    keep: bool,
) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, qobject_headers=12, ui_files=1, qrc_files=1)
    out_capsule = capsules_dir / f"seed_{seed:03d}_integrity.ngkcapsule.zip"
    frozen = freeze_capsule(repo_root=project.repo_root, config_path=project.config_path, target="app", out=out_capsule, verify=True)
    capsule_path = Path(frozen["capsule_path"])
    verify = verify_capsule(capsule_path)
    if not verify.get("ok"):
        raise AssertionError(f"capsule verify failed unexpectedly: {verify.get('mismatches')}")

    details = {
        "repro_path": str(project.repo_root),
        "capsule_path": str(capsule_path),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_tool_corruption_detection(
    projects_dir: Path,
    capsules_dir: Path,
    seed: int,
    keep: bool,
    inject_expected_failure: bool,
) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, qobject_headers=10, ui_files=1, qrc_files=1)
    out_capsule = capsules_dir / f"seed_{seed:03d}_corruptcheck.ngkcapsule.zip"
    frozen = freeze_capsule(repo_root=project.repo_root, config_path=project.config_path, target="app", out=out_capsule, verify=True)
    capsule_path = Path(frozen["capsule_path"])

    moc_tool = Path(project.qt_paths["moc_path"])
    moc_tool.write_text("@echo off\necho tampered\n", encoding="utf-8")

    verify = verify_capsule(capsule_path)
    mismatch_types = {m.get("component") for m in verify.get("mismatches", [])}
    has_tool_mismatch = bool(mismatch_types & {"qt_tool.moc.sha256", "qt_tool.moc.version"})

    if inject_expected_failure:
        if verify.get("ok"):
            raise SelftestFailure("expected capsule verify to fail under corruption injection", repro_path=str(project.repo_root))
        raise SelftestFailure("injected corruption failure", repro_path=str(project.repo_root))

    if verify.get("ok") or not has_tool_mismatch:
        raise AssertionError("tool corruption detection did not produce expected mismatch classification")

    details = {
        "repro_path": str(project.repo_root),
        "capsule_path": str(capsule_path),
        "mismatch_types": sorted(mismatch_types),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_parallel_isolation(projects_dir: Path, seed: int, keep: bool) -> dict[str, Any]:
    project_a = gen_project(projects_dir / "a", seed=seed, qobject_headers=30, ui_files=1, qrc_files=1)
    project_b = gen_project(projects_dir / "b", seed=seed + 1000, qobject_headers=30, ui_files=1, qrc_files=1)

    def _run(project: GeneratedProject) -> tuple[tuple[str, str], tuple[str, str], list[str]]:
        first = configure_project(project.repo_root, project.config_path)
        second = configure_project(project.repo_root, project.config_path)
        return _hashes(first), _hashes(second), [n.output for n in first["qt_result"].generator_nodes]

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_run, project_a)
        fut_b = pool.submit(_run, project_b)
        a_first, a_second, a_outputs = fut_a.result()
        b_first, b_second, b_outputs = fut_b.result()

    if a_first != a_second:
        raise AssertionError("project A hashes changed across repeated configure")
    if b_first != b_second:
        raise AssertionError("project B hashes changed across repeated configure")

    a_root = str(project_a.repo_root.resolve()).replace("\\", "/")
    b_root = str(project_b.repo_root.resolve()).replace("\\", "/")
    if not all(v.startswith(a_root) for v in a_outputs):
        raise AssertionError("project A outputs contaminated with foreign paths")
    if not all(v.startswith(b_root) for v in b_outputs):
        raise AssertionError("project B outputs contaminated with foreign paths")

    details = {
        "repro_path": str(projects_dir),
        "project_a_graph_hash": a_first[0],
        "project_b_graph_hash": b_first[0],
    }
    _cleanup_project(project_a.repo_root, keep)
    _cleanup_project(project_b.repo_root, keep)
    return details


def _scenario_compdb_contract(projects_dir: Path, seed: int, scale: int, keep: bool) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, qobject_headers=scale, ui_files=1, qrc_files=1)

    first = configure_project(project.repo_root, project.config_path)
    compdb_path = first["paths"]["compdb"]
    bytes_a = compdb_path.read_bytes()
    entries_a = load_compdb(compdb_path)
    hash_a = compdb_hash(entries_a)

    second = configure_project(project.repo_root, project.config_path)
    bytes_b = compdb_path.read_bytes()
    entries_b = load_compdb(compdb_path)
    hash_b = compdb_hash(entries_b)

    if bytes_a != bytes_b:
        raise AssertionError("NONDETERMINISTIC_BYTES: compile_commands.json bytes changed across repeated configure")
    if hash_a != hash_b:
        raise AssertionError("NONDETERMINISTIC_HASH: normalized compdb hash changed across repeated configure")

    violations = validate_compdb(entries_b, second["graph"], second["config"])
    if violations:
        lines = [f"{v.get('code')}: {v.get('detail')}" for v in violations]
        raise AssertionError("compdb contract violations: " + " | ".join(lines))

    details = {
        "repro_path": str(project.repo_root),
        "compdb_hash": hash_b,
        "entries": len(entries_b),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_graph_integrity(projects_dir: Path, seed: int, scale: int, keep: bool) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, qobject_headers=scale, ui_files=1, qrc_files=1)

    first = configure_project(project.repo_root, project.config_path)
    units_a = expected_compile_units(first["graph"], first["config"])
    links_a = expected_link_inputs(first["graph"], first["config"])

    second = configure_project(project.repo_root, project.config_path)
    units_b = expected_compile_units(second["graph"], second["config"])
    links_b = expected_link_inputs(second["graph"], second["config"])

    if units_a != units_b:
        raise AssertionError("graph.integrity: compile unit sets are not stable across repeated configure")
    if links_a != links_b:
        raise AssertionError("graph.integrity: link input plans are not stable across repeated configure")

    violations = validate_graph_integrity(second["graph"], second["config"], second["paths"]["out_dir"])
    if violations:
        lines = [f"{v.get('code')}: {v.get('detail')}" for v in violations]
        raise AssertionError("graph.integrity violations: " + " | ".join(lines))

    details = {
        "repro_path": str(project.repo_root),
        "targets": len(second["graph"].targets),
    }
    _cleanup_project(project.repo_root, keep)
    return details


def _scenario_profiles_parity(projects_dir: Path, seed: int, scale: int, keep: bool) -> dict[str, Any]:
    project = gen_project(projects_dir, seed=seed, qobject_headers=scale, ui_files=1, qrc_files=1, with_profiles=True)

    profile_results: dict[str, dict[str, Any]] = {}
    for profile in ["debug", "release"]:
        first = configure_project(project.repo_root, project.config_path, profile=profile)
        second = configure_project(project.repo_root, project.config_path, profile=profile)

        compdb_path = first["paths"]["compdb"]
        bytes_a = compdb_path.read_bytes()
        hash_a = compdb_hash(load_compdb(compdb_path))

        compdb_path_2 = second["paths"]["compdb"]
        bytes_b = compdb_path_2.read_bytes()
        hash_b = compdb_hash(load_compdb(compdb_path_2))

        if bytes_a != bytes_b:
            raise AssertionError(f"profiles.parity: NONDETERMINISTIC_BYTES for profile={profile}")
        if hash_a != hash_b:
            raise AssertionError(f"profiles.parity: NONDETERMINISTIC_HASH for profile={profile}")

        links_a = expected_link_inputs(first["graph"], first["config"])
        links_b = expected_link_inputs(second["graph"], second["config"])
        if links_a != links_b:
            raise AssertionError(f"profiles.parity: link input plan instability for profile={profile}")

        compdb_violations = validate_compdb(load_compdb(compdb_path_2), second["graph"], second["config"])
        if compdb_violations:
            lines = [f"{v.get('code')}: {v.get('detail')}" for v in compdb_violations]
            raise AssertionError(f"profiles.parity: compdb contract violations for profile={profile}: " + " | ".join(lines))

        graph_violations = validate_graph_integrity(second["graph"], second["config"], second["paths"]["out_dir"])
        if graph_violations:
            lines = [f"{v.get('code')}: {v.get('detail')}" for v in graph_violations]
            raise AssertionError(f"profiles.parity: graph integrity violations for profile={profile}: " + " | ".join(lines))

        profile_results[profile] = second

    parity_violations = validate_profile_parity(profile_results["debug"]["graph"], profile_results["release"]["graph"])
    if parity_violations:
        lines = [f"{v.get('code')}: {v.get('detail')}" for v in parity_violations]
        raise AssertionError("profiles.parity: profile parity violations: " + " | ".join(lines))

    debug_hash = compute_structural_graph_hash(profile_results["debug"]["graph"])
    release_hash = compute_structural_graph_hash(profile_results["release"]["graph"])
    if debug_hash != release_hash:
        raise AssertionError("profiles.parity: structural graph hash differs between debug and release")

    details = {
        "repro_path": str(project.repo_root),
        "debug_structural_hash": debug_hash,
        "release_structural_hash": release_hash,
    }
    _cleanup_project(project.repo_root, keep)
    return details


def run_selftest(
    *,
    scale: int,
    seeds: range,
    out_dir: Path,
    fail_fast: bool,
    timeout: int,
    keep: bool = False,
    inject_corruption_failure: bool = False,
    profiles_mode: bool = False,
) -> dict[str, Any]:
    seeds_list = list(seeds)
    out_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = out_dir / "logs"
    capsules_dir = out_dir / "capsules"
    projects_dir = out_dir / "projects"
    logs_dir.mkdir(parents=True, exist_ok=True)
    capsules_dir.mkdir(parents=True, exist_ok=True)
    projects_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "phase": "6F",
        "ts": _utc_stamp(),
        "scale": int(scale),
        "seeds": list(seeds_list),
        "results": [],
        "pass": True,
        "failures": [],
        "artifacts_dir": str(out_dir.resolve()),
        "version": {
            "ngksgraph": __version__,
            "python": platform.python_version(),
        },
    }

    for seed in seeds_list:
        scenarios: list[tuple[str, Callable[[], dict[str, Any]]]] = [
            (
                "qt.scale.moc_many_headers",
                lambda s=seed: _scenario_determinism_core(projects_dir / f"seed_{s:03d}_det", s, int(scale), keep),
            ),
            (
                "qt.generators.correctness",
                lambda s=seed: _scenario_qt_generators(projects_dir / f"seed_{s:03d}_gen", s, int(scale), keep),
            ),
            (
                "qt.paths.with_spaces",
                lambda s=seed: _scenario_paths_with_spaces(projects_dir / f"seed_{s:03d}_spaces", s, keep),
            ),
            (
                "capsule.integrity.verify",
                lambda s=seed: _scenario_capsule_integrity(projects_dir / f"seed_{s:03d}_caps", capsules_dir, s, keep),
            ),
            (
                "capsule.corruption.detect",
                lambda s=seed: _scenario_tool_corruption_detection(
                    projects_dir / f"seed_{s:03d}_corrupt",
                    capsules_dir,
                    s,
                    keep,
                    inject_expected_failure=bool(inject_corruption_failure),
                ),
            ),
            (
                "parallel.isolation.light",
                lambda s=seed: _scenario_parallel_isolation(projects_dir / f"seed_{s:03d}_parallel", s, keep),
            ),
        ]

        for name, fn in scenarios:
            log_path = logs_dir / f"{name.replace('.', '_')}_seed_{seed:03d}.log"
            result, failure = _run_case(name=name, seed=seed, timeout=timeout, log_path=log_path, case_fn=fn)
            report["results"].append(result)
            if failure is not None:
                report["pass"] = False
                report["failures"].append(failure)
                if fail_fast:
                    return report

        compdb_name = "compdb.contract"
        compdb_log = logs_dir / f"{compdb_name.replace('.', '_')}_seed_{seed:03d}.log"
        compdb_result, compdb_failure = _run_case(
            name=compdb_name,
            seed=seed,
            timeout=timeout,
            log_path=compdb_log,
            case_fn=lambda s=seed: _scenario_compdb_contract(projects_dir / f"seed_{s:03d}_compdb", s, int(scale), keep),
        )
        report["results"].append(compdb_result)
        if compdb_failure is not None:
            report["pass"] = False
            report["failures"].append(compdb_failure)
            if fail_fast:
                return report

        graph_name = "graph.integrity"
        graph_log = logs_dir / f"{graph_name.replace('.', '_')}_seed_{seed:03d}.log"
        graph_result, graph_failure = _run_case(
            name=graph_name,
            seed=seed,
            timeout=timeout,
            log_path=graph_log,
            case_fn=lambda s=seed: _scenario_graph_integrity(projects_dir / f"seed_{s:03d}_graph", s, int(scale), keep),
        )
        report["results"].append(graph_result)
        if graph_failure is not None:
            report["pass"] = False
            report["failures"].append(graph_failure)
            if fail_fast:
                return report

        if profiles_mode:
            parity_name = "profiles.parity"
            parity_log = logs_dir / f"{parity_name.replace('.', '_')}_seed_{seed:03d}.log"
            parity_result, parity_failure = _run_case(
                name=parity_name,
                seed=seed,
                timeout=timeout,
                log_path=parity_log,
                case_fn=lambda s=seed: _scenario_profiles_parity(projects_dir / f"seed_{s:03d}_profiles", s, int(scale), keep),
            )
            report["results"].append(parity_result)
            if parity_failure is not None:
                report["pass"] = False
                report["failures"].append(parity_failure)
                if fail_fast:
                    return report

    if report["pass"] and not keep:
        shutil.rmtree(projects_dir, ignore_errors=True)

    return report


def write_report(report_dict: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    write_json(report_path, report_dict)
    return report_path


def print_summary(report_dict: dict[str, Any], json_only: bool = False, report_path: Path | None = None) -> None:
    passed = bool(report_dict.get("pass"))
    results = report_dict.get("results", [])
    failures = report_dict.get("failures", [])

    if json_only:
        print("PASS" if passed else "FAIL")
        if report_path is not None:
            print(str(report_path))
        return

    print("NGKsGraph Selftest (Phase 6F)")
    print(f"Status: {'PASS' if passed else 'FAIL'}")
    print(f"Cases: {len(results)}")
    print(f"Failures: {len(failures)}")
    if report_path is not None:
        print(f"Report: {report_path}")

    if failures:
        print("Failure details:")
        for item in failures:
            print(
                f"- {item.get('name')} seed={item.get('seed')} error={item.get('error')} repro={item.get('repro_path')}"
            )
