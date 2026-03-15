from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .component_exec import ComponentResolutionError, resolve_component_cmd
from .certification_rollup import run_subtarget_rollup_comparison, run_subtarget_rollup_gate
from .certification_target import run_target_validation_precheck
from .certify_compare import ComparisonPolicy, run_certification_comparison
from .certify_gate import GateEnforcementPolicy, run_certification_gate
from .decision_validation import run_decision_validation
from .explain_engine import persist_explain_bundle, run_explain_query
from .node_toolchain import detect_node_toolchain
from .proof_manager import register_proof_bundle
from .proof_contract import doc_gate, ensure_unified_pf, repo_state, run_docengine_render, write_component_report
from .probe import probe_project
from .predictive_risk import analyze_premerge_regression_risk
from .validation_planner import plan_premerge_validation
from .validation_policy_engine import evaluate_validation_policy
from .validation_orchestrator import run_validation_orchestrator
from .validation_rerun_pipeline import run_validation_and_certify_pipeline
from .devfabeco_orchestrator import (
    ensure_graph_state_current,
    generate_graph_plan,
    run_build_pipeline,
)
from .graph_state_monitor import start_background_graph_monitor
from .connector_transport import run_connector_transport
from .profile import init_profile
from .runwrap import doctor_toolchain, run_build
from .workspace_integrity import run_workspace_integrity_check
from .graph_state_manager import ensure_graph_state_fresh
from .smart_terminal import detect_shell, resolve_smart_terminal_enabled, run_shell, run_shell_direct

DEVFABRIC_ROOT = Path(__file__).resolve().parents[3]
_NOTEBOOK_POLICY_TOKENS = (".ipynb", "jupyter", "ipykernel", "notebook", "run_notebook_cell")


@dataclass(frozen=True)
class StageResult:
    stage: str
    exit_code: int
    stdout: str
    stderr: str
    failure_class: str = "stage_failed"


def _print_result(message: str) -> None:
    print(message)


def _enforce_workspace_integrity(*, pf: Path | None, scope: str) -> bool:
    artifact_dir = (pf / "workspace_integrity") if pf is not None else None
    result, artifact_paths = run_workspace_integrity_check(scope=scope, artifact_dir=artifact_dir)
    if result.ok:
        return True

    _print_result("WORKSPACE_INTEGRITY=FAIL")
    _print_result(f"workspace_root={result.workspace_root}")
    _print_result(f"python_executable={result.python_executable}")
    for module_name, module_file in sorted(result.module_resolution.items()):
        _print_result(f"module_resolution.{module_name}={module_file}")
    for violation in result.violations:
        _print_result(f"workspace_integrity_violation={violation}")
    if artifact_paths:
        _print_result(f"workspace_integrity_artifacts={artifact_dir}")
    return False


def _enforce_graph_state_automation(
    *,
    project_root: Path,
    pf: Path,
    scope: str,
    active_profile: str,
    active_target: str,
) -> bool:
    pf = pf.resolve()
    pf.mkdir(parents=True, exist_ok=True)
    graph_artifact_root = (pf / "20_graph_auto_refresh").resolve()

    def _refresh_callback() -> tuple[bool, str]:
        try:
            graph_artifact_root.mkdir(parents=True, exist_ok=True)
            state = ensure_graph_state_current(project_root=project_root, pf=graph_artifact_root)
            generate_graph_plan(project_root=project_root, pf=graph_artifact_root, graph_state=state)
            return True, "graph_refresh_completed"
        except Exception as exc:
            return False, str(exc)

    outcome = ensure_graph_state_fresh(
        project_root=project_root,
        pf=pf,
        active_profile=active_profile,
        active_target=active_target,
        graph_artifact_root=graph_artifact_root,
        refresh_callback=_refresh_callback,
    )

    action = outcome.get("refresh_action", {}) if isinstance(outcome.get("refresh_action", {}), dict) else {}
    _print_result(f"graph_state_scope={scope}")
    _print_result(f"graph_state_dirty_before={outcome.get('dirty_before', True)}")
    _print_result(f"graph_state_refresh_action={action.get('action', '')}")
    _print_result(f"graph_state_refresh_status={action.get('status', '')}")
    _print_result(f"graph_state_file={outcome.get('state_path', '')}")

    if not bool(outcome.get("ok", False)):
        _print_result("GRAPH_STATE_AUTOMATION=FAIL")
        for reason in outcome.get("dirty_reasons", []):
            _print_result(f"graph_state_dirty_reason={reason}")
        _print_result(f"graph_state_failure_reason={action.get('reason', '')}")
        return False

    _print_result("GRAPH_STATE_AUTOMATION=PASS")
    return True


def _enforce_validation_policy(
    *,
    project_root: Path,
    pf: Path,
    stage: str,
    profile: str,
    target: str,
) -> bool:
    result = evaluate_validation_policy(
        project_root=project_root,
        pf=pf,
        stage=stage,
        profile=profile,
        target=target,
    )
    _print_result(f"validation_policy_stage={stage}")
    _print_result(f"validation_policy_selected_plugins={','.join(result.get('selected_plugins', []))}")
    _print_result(f"validation_policy_skipped_plugins={','.join(result.get('skipped_plugins', []))}")
    _print_result(f"validation_policy_blocking_failures={','.join(result.get('blocking_failures', []))}")
    _print_result(f"validation_policy_advisory_failures={','.join(result.get('advisory_failures', []))}")
    _print_result(f"validation_policy_gate={result.get('gate_status', 'PASS')}")
    return str(result.get("gate_status", "PASS")).upper() == "PASS"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runid_now() -> str:
    return "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_intent(args: argparse.Namespace) -> dict[str, object]:
    arg_list: list[str] = []
    if getattr(args, "project_path", None) and args.project_path != ".":
        arg_list.append(str(args.project_path))
    arg_list.extend(["--mode", str(args.mode)])
    arg_list.extend(["--backend", str(args.backend)])
    if args.target:
        arg_list.extend(["--target", str(args.target)])
    if args.jobs:
        arg_list.extend(["--jobs", str(args.jobs)])
    if args.profile:
        arg_list.extend(["--profile", str(args.profile)])
    return {
        "command": "ngksdevfabric build",
        "args": arg_list,
        "mode": "build",
    }


def _emit_component_reports_for_build(
    pf: Path,
    backend: str,
    build_exit_code: int,
    start_ts: str,
    end_ts: str,
    build_cmdline: str,
) -> None:
    repo = repo_state(DEVFABRIC_ROOT)
    base_status = "PASS" if build_exit_code == 0 else "FAIL"

    write_component_report(
        pf=pf,
        component="devfabric",
        version="unknown",
        status=base_status,
        start_ts=start_ts,
        end_ts=end_ts,
        cmdline=build_cmdline,
        repo=repo,
        notes=["shim_report_generated_by_devfabric"],
    )

    if backend == "buildcore":
        write_component_report(
            pf=pf,
            component="graph",
            version="unknown",
            status=base_status,
            start_ts=start_ts,
            end_ts=end_ts,
            cmdline="graph buildplan (via devfabric shim)",
            repo=repo,
            notes=["shim_report_generated_by_devfabric", "backend=buildcore"],
        )
        write_component_report(
            pf=pf,
            component="buildcore",
            version="unknown",
            status=base_status,
            start_ts=start_ts,
            end_ts=end_ts,
            cmdline="buildcore run (via devfabric shim)",
            repo=repo,
            notes=["shim_report_generated_by_devfabric", "backend=buildcore"],
        )


def _default_pf(project: Path, prefix: str) -> Path:
    runs_root = (project / "_proof" / "runs").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return runs_root / f"{prefix}_{stamp}"


def _canonical_pf(project_root: Path, candidate: Path) -> Path:
    runs_root = (project_root / "_proof" / "runs").resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    try:
        candidate.resolve().relative_to(runs_root)
        return candidate.resolve()
    except Exception:
        return (runs_root / candidate.name).resolve()


def _git_root_for(path: Path) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    root = (proc.stdout or "").strip()
    if not root:
        return None
    return Path(root).resolve()


def _resolve_project_root(project_path: str | None) -> Path:
    if project_path and project_path != ".":
        return Path(project_path).resolve()
    cwd = Path.cwd().resolve()
    git_root = _git_root_for(cwd)
    return git_root if git_root else cwd


def _project_path_from_argv(argv: list[str]) -> str | None:
    for index, token in enumerate(argv):
        if token == "--project-path" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _collect_notebook_policy_hits(argv: list[str]) -> list[str]:
    hits: list[str] = []
    for raw in argv:
        lowered = str(raw).lower()
        for token in _NOTEBOOK_POLICY_TOKENS:
            if token in lowered:
                hits.append(str(raw))
                break
    return hits


def _record_notebook_policy_violation(*, project_root: Path, argv: list[str], hits: list[str]) -> Path:
    policy_dir = (project_root / "_proof" / "policy_violations").resolve()
    policy_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = policy_dir / f"notebook_policy_violation_{ts}.json"
    payload = {
        "timestamp": _iso_now(),
        "policy": "forbid_notebook_jupyter_ipykernel_in_core_workflows",
        "argv": argv,
        "hits": hits,
        "result": "blocked",
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _enforce_notebook_policy(argv: list[str]) -> int:
    hits = _collect_notebook_policy_hits(argv)
    if not hits:
        return 0
    project_root = _resolve_project_root(_project_path_from_argv(argv))
    violation_path = _record_notebook_policy_violation(project_root=project_root, argv=argv, hits=hits)
    _print_result("error=policy_violation_notebook_execution_forbidden")
    _print_result(f"policy_violation_file={violation_path}")
    return 2


def _is_interactive_tty() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def _normalize_backup_root(raw_value: str, project_root: Path) -> Path:
    normalized = raw_value.strip()
    normalized = normalized.strip('"').strip("'")

    expanded = os.path.expandvars(normalized)
    path = Path(expanded)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    else:
        path = path.resolve()
    return path


def _validate_backup_root(path: Path) -> tuple[bool, str]:
    anchor = path.anchor
    if anchor:
        drive_root = Path(anchor)
        if not drive_root.exists():
            return False, f"Drive root does not exist: {drive_root}"

    if path.exists() and not path.is_dir():
        return False, f"Path exists but is not a directory: {path}"

    return True, ""


def _prompt_backup_root(project_root: Path) -> Path | None:
    _print_result("Backup root is required for mirroring documentation.")

    while True:
        raw = input("Enter backup root path (or blank to cancel): ")
        if not raw.strip():
            return None

        candidate = _normalize_backup_root(raw, project_root)
        ok, reason = _validate_backup_root(candidate)
        if not ok:
            _print_result(reason)
            continue

        if candidate.exists():
            return candidate

        ans = input("Backup root does not exist. Create it? [y/N]:")
        if ans.strip().lower() != "y":
            continue

        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _print_result(f"Unable to create backup root: {exc}")
            continue

        ok, reason = _validate_backup_root(candidate)
        if ok:
            return candidate
        _print_result(reason)


def _resolve_backup_root_interactive(project_root: Path, initial_value: str | None = None) -> Path | None:
    if initial_value and initial_value.strip():
        candidate = _normalize_backup_root(initial_value, project_root)
        ok, reason = _validate_backup_root(candidate)
        if not ok:
            _print_result(reason)
        elif candidate.exists():
            return candidate
        else:
            ans = input("Backup root does not exist. Create it? [y/N]:")
            if ans.strip().lower() == "y":
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    return candidate
                except OSError as exc:
                    _print_result(f"Unable to create backup root: {exc}")

    return _prompt_backup_root(project_root)


def _resolve_backup_root(args: argparse.Namespace, project_root: Path, allow_prompt: bool = False) -> Path | None:
    backup_root_value = (getattr(args, "backup_root", None) or os.environ.get("NGKS_BACKUP_ROOT", "")).strip()
    no_prompt = bool(getattr(args, "no_prompt", False))
    interactive_allowed = allow_prompt and not no_prompt and _is_interactive_tty()

    if backup_root_value:
        backup_root = _normalize_backup_root(backup_root_value, project_root)
        ok, reason = _validate_backup_root(backup_root)
        if ok and backup_root.exists():
            os.environ["NGKS_BACKUP_ROOT"] = str(backup_root)
            return backup_root

        if interactive_allowed:
            chosen = _resolve_backup_root_interactive(project_root, initial_value=backup_root_value)
            if chosen is None:
                raise ValueError("backup_root_cancelled")
            os.environ["NGKS_BACKUP_ROOT"] = str(chosen)
            return chosen

        if not ok:
            raise ValueError(reason)

        if not backup_root.exists():
            try:
                backup_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise ValueError(f"backup_root_not_found: {backup_root}")

        if not backup_root.exists():
            raise ValueError(f"backup_root_not_found: {backup_root}")

        os.environ["NGKS_BACKUP_ROOT"] = str(backup_root)
        return backup_root

    if interactive_allowed:
        chosen = _prompt_backup_root(project_root)
        if chosen is None:
            return None
        os.environ["NGKS_BACKUP_ROOT"] = str(chosen)
        return chosen

    return None


def _resolve_pf(args: argparse.Namespace, project_root: Path, prefix: str) -> Path:
    if getattr(args, "pf", None):
        return _canonical_pf(project_root, Path(args.pf))
    return _default_pf(project_root, prefix)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_required_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise ValueError(f"expected_output_missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _register_bundle_safely(bundle: Path) -> None:
    try:
        register_proof_bundle(bundle_path=bundle, devfab_root=DEVFABRIC_ROOT)
    except Exception:
        # Proof registration must not break the primary command outcome.
        pass


def _run_stage_command(stage: str, command: list[str], cwd: Path, stdout_file: Path) -> StageResult:
    try:
        proc = subprocess.run(command, cwd=str(cwd), check=False, capture_output=True, text=True)
        out_text = (proc.stdout or "")
        err_text = (proc.stderr or "")
        exit_code = int(proc.returncode)
    except OSError as exc:
        out_text = ""
        err_text = str(exc)
        exit_code = 2
    _write_text(stdout_file, out_text + ("\n" if out_text and not out_text.endswith("\n") else "") + f"EXITCODE={exit_code}\n")
    return StageResult(stage=stage, exit_code=exit_code, stdout=out_text, stderr=err_text)


def _write_stage_contract_files(stage_dir: Path, mode: str, why: str, argv: list[str], stdout: str, stderr: str, exit_code: int) -> None:
    resolve_text = "\n".join(
        [
            f"mode={mode}",
            f"why={why}",
            "argv=" + " ".join(str(part) for part in argv),
            "",
        ]
    )
    _write_text(stage_dir / "00_resolve.txt", resolve_text)
    _write_text(stage_dir / "01_stdout.txt", stdout)
    _write_text(stage_dir / "02_stderr.txt", stderr)
    _write_text(stage_dir / "03_exit_code.txt", f"EXITCODE={int(exit_code)}\n")


def _run_stage_with_resolver(
    *,
    stage: str,
    stage_dir: Path,
    project_root: Path,
    component_name: str,
    module_name: str,
    tail_args: list[str],
) -> StageResult:
    try:
        resolved = resolve_component_cmd(component_name=component_name, module_name=module_name)
        mode = str(resolved.get("mode", ""))
        why = str(resolved.get("why", ""))
        base_argv = [str(part) for part in list(resolved.get("argv", []))]
        argv = [*base_argv, *tail_args]
    except ComponentResolutionError as exc:
        stderr = str(exc)
        _write_stage_contract_files(
            stage_dir=stage_dir,
            mode="resolve_error",
            why="component resolver failed",
            argv=[],
            stdout="",
            stderr=stderr + ("\n" if stderr and not stderr.endswith("\n") else ""),
            exit_code=2,
        )
        return StageResult(stage=stage, exit_code=2, stdout="", stderr=stderr, failure_class="component_missing")

    stage_env = dict(os.environ)
    if component_name == "ngksbuildcore":
        # Internal pipeline stages are allowed to invoke BuildCore directly.
        stage_env["NGKS_ALLOW_DIRECT_BUILDCORE"] = "1"

    try:
        proc = subprocess.run(argv, cwd=str(project_root), check=False, capture_output=True, text=True, env=stage_env)
        out_text = proc.stdout or ""
        err_text = proc.stderr or ""
        exit_code = int(proc.returncode)
    except OSError as exc:
        out_text = ""
        err_text = str(exc)
        exit_code = 2

    _write_stage_contract_files(
        stage_dir=stage_dir,
        mode=mode,
        why=why,
        argv=argv,
        stdout=out_text,
        stderr=err_text,
        exit_code=exit_code,
    )
    return StageResult(stage=stage, exit_code=exit_code, stdout=out_text, stderr=err_text)


def _verify_required_outputs(required_outputs: list[Path]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for output in required_outputs:
        if not output.exists() or not output.is_file():
            missing.append(output.name)
    return len(missing) == 0, missing


def _append_failure(
    run_dir: Path,
    result: StageResult,
    *,
    failure_class: str,
    missing_outputs: list[str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> None:
    snippet_src = result.stderr if result.stderr.strip() else result.stdout
    snippet = "\n".join(snippet_src.splitlines()[:40])
    missing_joined = ",".join(missing_outputs) if missing_outputs else ""
    _write_text(
        run_dir / "30_errors.txt",
        "\n".join(
            [
                f"class={failure_class}",
                f"stage={result.stage}",
                f"exit_code={result.exit_code}",
                f"missing_outputs={missing_joined}",
                f"stdout_path={str(stdout_path) if stdout_path else ''}",
                f"stderr_path={str(stderr_path) if stderr_path else ''}",
                "snippet_start",
                snippet,
                "snippet_end",
                "next_steps=verify component installation, confirm stage contract output files are produced, and rerun with PF artifacts",
                "",
            ]
        ),
    )


def _append_failure_message(run_dir: Path, stage: str, message: str, exit_code: int = 2) -> None:
    _append_failure(
        run_dir,
        StageResult(stage=stage, exit_code=exit_code, stdout="", stderr=message),
        failure_class="stage_failed",
    )


def _read_failure_hint(run_dir: Path) -> str:
    errors_path = run_dir / "30_errors.txt"
    if not errors_path.exists():
        return ""
    try:
        lines = errors_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    ignored_prefixes = (
        "class=",
        "stage=",
        "exit_code=",
        "missing_outputs=",
        "stdout_path=",
        "stderr_path=",
        "snippet_start",
        "snippet_end",
        "next_steps=",
    )
    candidates = [line.strip() for line in lines if line.strip() and not line.strip().startswith(ignored_prefixes)]
    if not candidates:
        return ""

    preferred_markers = ("[err]", "error", "missing_tool", "config_not_found", "target_not_found")
    for candidate in candidates:
        lowered = candidate.lower()
        if any(marker in lowered for marker in preferred_markers):
            return candidate[:220]
    return candidates[0][:220]


def _stage_label(stage: str) -> str:
    mapping = {
        "10_envcapsule": "EnvCapsule",
        "20_graph": "Graph",
        "30_buildcore": "BuildCore",
        "40_library": "Library",
    }
    return mapping.get(stage, stage or "unknown")


def _failure_action_hint(failure_hint: str, build_reason: str) -> str:
    lowered = f"{failure_hint} {build_reason}".lower()
    if "cargo" in lowered:
        return "ensure Rust Cargo is installed and on PATH (e.g. %USERPROFILE%\\.cargo\\bin), then rerun"
    if "missing_required_target" in lowered:
        return "add the requested npm script target to package.json scripts and rerun"
    if "missing_tool:" in lowered:
        return "install the missing tool and rerun"
    if "missing_required_outputs" in lowered:
        return "check prior stage outputs and rerun"
    return "see 30_errors.txt for details"


def _extract_hash(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ""
    return text.split()[0].strip()


def _hash_with_reason(path: Path, stage_ok: bool) -> tuple[str, str]:
    if not stage_ok:
        return "", "skipped_due_to_precondition"
    if not path.exists():
        return "", "missing_outputs"
    value = _extract_hash(path)
    if not value:
        return "", "missing_outputs"
    return value, "ok"


def _is_reasonable_signal_path(project_root: Path, path: Path, max_depth: int = 8) -> bool:
    try:
        rel = path.resolve().relative_to(project_root.resolve())
    except Exception:
        return False
    if len(rel.parts) > max_depth:
        return False
    blocked = {
        ".git",
        "node_modules",
        ".venv",
        "__pycache__",
        "_proof",
        "build",
        "out",
        "target",
        ".dart_tool",
    }
    return all(part not in blocked for part in rel.parts)


def _find_first_signal(project_root: Path, patterns: list[str]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        for path in project_root.rglob(pattern):
            if not path.is_file():
                continue
            if _is_reasonable_signal_path(project_root, path):
                matches.append(path.resolve())
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.as_posix().lower())[0]


def _detect_build_inputs(project_root: Path) -> tuple[bool, str, str]:
    flutter_signal = _find_first_signal(project_root, ["pubspec.yaml"])
    if flutter_signal is not None:
        return True, "flutter", str(flutter_signal.relative_to(project_root).as_posix())

    dotnet_signal = _find_first_signal(project_root, ["*.sln", "*.csproj"])
    if dotnet_signal is not None:
        return True, "dotnet", str(dotnet_signal.relative_to(project_root).as_posix())

    node_signal = _find_first_signal(project_root, ["package.json"])
    if node_signal is not None:
        return True, "node", str(node_signal.relative_to(project_root).as_posix())

    python_signal = _find_first_signal(project_root, ["pyproject.toml", "requirements.txt"])
    if python_signal is not None:
        return True, "python", str(python_signal.relative_to(project_root).as_posix())

    return False, "none", "no_build_inputs"


def _detect_static_site_root(project_root: Path) -> Path | None:
    direct_index = project_root / "index.html"
    if direct_index.is_file():
        return project_root

    blocked = {".git", "_proof", "node_modules", ".venv", ".venv_ngksdevfabeco_pypi", "build", "dist", "out"}
    for child in sorted(project_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name in blocked:
            continue
        if (child / "index.html").is_file():
            return child
    return None


def _run_static_site_build(project_root: Path, source_root: Path) -> tuple[bool, str]:
    out_root = project_root / "build_static_site"
    try:
        if out_root.exists():
            shutil.rmtree(out_root)
        shutil.copytree(source_root, out_root)
        receipt = {
            "build_system": "static_site",
            "source_root": str(source_root),
            "output_root": str(out_root),
            "generated_at": _iso_now(),
        }
        _write_text(out_root / "_ngks_build_receipt.json", json.dumps(receipt, indent=2))
    except OSError as exc:
        return False, str(exc)
    return True, "ok"


def _ensure_ngks_operating_rules(project_root: Path) -> None:
    ngks_dir = project_root / ".ngks"
    ngks_dir.mkdir(parents=True, exist_ok=True)
    (ngks_dir / "project.json").write_text(
        json.dumps(
            {
                "schema": "ngks.project.rules.v1",
                "project_root": str(project_root),
                "autodetect": ["flutter", "node", "python", "dotnet"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (ngks_dir / "profile.default.json").write_text(
        json.dumps(
            {
                "schema": "ngks.profile.default.v1",
                "mode": "ecosystem",
                "safety": "fail_closed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (ngks_dir / "README.txt").write_text(
        "NGKs operating rules for ecosystem mode.\nThis folder may be created for NOOP runs.\n",
        encoding="utf-8",
    )


def _missing_required_tool(build_system: str) -> str | None:
    tool_map = {
        "flutter": "flutter",
        "node": "npm",
        "python": "python",
        "dotnet": "dotnet",
    }
    tool = tool_map.get(build_system)
    if not tool:
        return None
    return None if shutil.which(tool) else tool


def _write_stage_sentinel(stage_dir: Path, stage_name: str, status: str, reason: str) -> None:
    _write_text(
        stage_dir / "00_stage.txt",
        "\n".join(
            [
                f"stage={stage_name}",
                f"status={status}",
                f"reason={reason}",
                f"timestamp={_iso_now()}",
                "",
            ]
        ),
    )


def _node_target_exists(project_root: Path, target: str) -> bool:
    pkg = project_root / "package.json"
    if not pkg.is_file():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return False
    script = scripts.get(target)
    return isinstance(script, str) and bool(script.strip())


def _node_target_exists_in_package(package_json_path: Path, target: str) -> bool:
    pkg = package_json_path
    if not pkg.is_file():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return False
    script = scripts.get(target)
    return isinstance(script, str) and bool(script.strip())


def _resolve_node_package_json(project_root: Path, build_detect_reason: str) -> Path:
    default_pkg = project_root / "package.json"
    reason = str(build_detect_reason or "").strip()
    if not reason or reason == "package.json":
        return default_pkg
    candidate = (project_root / reason).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except Exception:
        return default_pkg
    if candidate.name != "package.json":
        return default_pkg
    return candidate


def _resolve_detected_build_root(project_root: Path, build_detect_reason: str) -> Path:
    reason = str(build_detect_reason or "").strip()
    if not reason or reason == "no_build_inputs":
        return project_root
    candidate = (project_root / reason).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except Exception:
        return project_root
    if candidate.is_dir():
        return candidate
    return candidate.parent


def _apply_node_package_manager_to_plan(plan_file: Path, package_manager: str) -> tuple[bool, str]:
    if not plan_file.exists() or package_manager not in {"pnpm", "npm", "yarn"}:
        return False, "invalid_input"

    try:
        data = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False, "invalid_plan_json"
    if not isinstance(data, dict):
        return False, "invalid_plan_object"

    requirements = data.get("requirements")
    if not isinstance(requirements, dict):
        requirements = {}
        data["requirements"] = requirements
    requirements["package_manager"] = package_manager

    actions = data.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            argv = action.get("argv")
            if isinstance(argv, list) and argv:
                first = str(argv[0]).strip().lower()
                if first in {"npm", "pnpm", "yarn"}:
                    argv[0] = package_manager

    plan_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    digest = hashlib.sha256(plan_file.read_bytes()).hexdigest()
    plan_hash_file = plan_file.with_name("build_plan.hash.txt")
    plan_hash_file.write_text(digest + "\n", encoding="utf-8")
    return True, "ok"


def _write_run_summary(
    run_dir: Path,
    run_id: str,
    env_hash: str,
    plan_hash: str,
    build_success: bool,
    env_hash_reason: str,
    plan_hash_reason: str,
    *,
    build_detected: bool,
    build_system: str,
    build_detect_reason: str,
    build_action: str,
    build_reason: str,
    components_state: str,
    exit_code: int,
    conflict_detected: bool = False,
    conflict_type: str = "none",
    conflicting_inputs: str = "",
    conflict_resolution: str = "none",
    conflict_confidence: str = "",
    unresolved_risk: str = "",
    failure_class: str = "",
    failed_stage: str = "",
) -> None:
    lines = [
        f"run_id={run_id}",
        "components_executed=envcapsule,graph,buildcore,library",
        f"env_capsule_hash={env_hash}",
        f"env_capsule_hash_reason={env_hash_reason}",
        f"build_plan_hash={plan_hash}",
        f"build_plan_hash_reason={plan_hash_reason}",
        f"build_detected={'true' if build_detected else 'false'}",
        f"build_system={build_system}",
        f"build_detect_reason={build_detect_reason}",
        f"build_action={build_action}",
        f"build_reason={build_reason}",
        f"components_state={components_state}",
        f"build_success={'true' if build_success else 'false'}",
        f"exit_code={int(exit_code)}",
        f"conflict_detected={'true' if conflict_detected else 'false'}",
        f"conflict_type={conflict_type}",
        f"conflicting_inputs={conflicting_inputs}",
        f"conflict_resolution={conflict_resolution}",
        f"conflict_confidence={conflict_confidence}",
        f"unresolved_risk={unresolved_risk}",
    ]
    if failure_class:
        lines.append(f"failure_class={failure_class}")
    if failed_stage:
        lines.append(f"failed_stage={failed_stage}")
    lines.append("")

    _write_text(
        run_dir / "99_summary.txt",
        "\n".join(lines),
    )


def _print_doc_notice(project_root: Path) -> None:
    _print_result(f"Documentation will be located at {project_root / '_proof'}")
    _print_result("Set --backup-root (or NGKS_BACKUP_ROOT) to mirror backup documentation; otherwise backup is disabled.")


def _backup_mirror_path(project_root: Path, backup_root: Path, pf: Path) -> Path:
    repo_name = project_root.name if project_root.name else "project"
    return (backup_root / repo_name / "_proof" / pf.name).resolve()


def _mirror_docs_to_backup(project_root: Path, backup_root: Path, pf: Path) -> Path:
    backup_pf = _backup_mirror_path(project_root, backup_root, pf)
    try:
        backup_pf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pf, backup_pf, dirs_exist_ok=True)
    except OSError as exc:
        raise ValueError(f"backup_mirror_failed: {exc}") from exc
    _print_result(f"Backup documentation saved to {backup_pf}")
    return backup_pf


def cmd_probe(args: argparse.Namespace) -> int:
    project = _resolve_project_root(args.project_path)
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "probe")
    report = probe_project(project, pf, run_dynamic_checks=True)
    if backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"probe_report={pf / 'probe_report.json'}")
    _print_result(f"primary_path={report.get('primary_path')}")
    _print_result("exit_code=0")
    return 0


def cmd_profile_init(args: argparse.Namespace) -> int:
    project = _resolve_project_root(args.project_path)
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "profile_init")
    receipt = init_profile(project, pf, write_project=bool(args.write_project))
    if backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"profile_write_receipt={pf / 'profile_write_receipt.json'}")
    _print_result(f"profile_path={receipt.get('profile_path')}")
    _print_result(f"write_mode={receipt.get('write_mode')}")
    _print_result("exit_code=0")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    project = _resolve_project_root(args.project_path)
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "build")

    if not _enforce_workspace_integrity(pf=pf, scope="cli_ngks_build"):
        _register_bundle_safely(pf)
        _print_result(f"project_root={project}")
        _print_result(f"proof_dir={pf}")
        _print_result("exit_code=2")
        return 2

    if not _enforce_graph_state_automation(
        project_root=project,
        pf=pf,
        scope="cli_ngks_build",
        active_profile=str(getattr(args, "profile", "debug") or "debug"),
        active_target=str(getattr(args, "target", "build") or "build"),
    ):
        _register_bundle_safely(pf)
        _print_result(f"project_root={project}")
        _print_result(f"proof_dir={pf}")
        _print_result("exit_code=2")
        return 2

    if not _enforce_validation_policy(
        project_root=project,
        pf=pf,
        stage="build",
        profile=str(getattr(args, "profile", "debug") or "debug"),
        target=str(getattr(args, "target", "build") or "build"),
    ):
        _register_bundle_safely(pf)
        _print_result(f"project_root={project}")
        _print_result(f"proof_dir={pf}")
        _print_result("exit_code=2")
        return 2

    components = ["graph", "devfabric", "buildcore"] if args.backend == "buildcore" else ["devfabric"]

    ensure_unified_pf(
        pf=pf,
        intent=_build_intent(args),
        components=components,
        repo_root=DEVFABRIC_ROOT,
    )

    started_at = _iso_now()
    pipeline_result = run_build_pipeline(
        project_root=project,
        pf=pf,
        mode=args.mode,
        target=args.target,
        profile=args.profile,
        trigger="ngksdevfabric build",
    )
    code = int(pipeline_result.get("exit_code", 1))
    ended_at = _iso_now()

    build_cmdline = "python -m ngksdevfabric build"
    if args.backend:
        build_cmdline += f" --backend {args.backend}"
    if args.target:
        build_cmdline += f" --target {args.target}"
    if args.mode:
        build_cmdline += f" --mode {args.mode}"
    if args.jobs:
        build_cmdline += f" --jobs {args.jobs}"

    _emit_component_reports_for_build(
        pf=pf,
        backend=args.backend,
        build_exit_code=code,
        start_ts=started_at,
        end_ts=ended_at,
        build_cmdline=build_cmdline,
    )

    if code == 0 and args.render_doc:
        render_code, render_details = run_docengine_render(pf=pf, devfabric_root=DEVFABRIC_ROOT)
        _print_result(f"docengine_exit_code={render_code}")
        if render_details.get("stdout"):
            _print_result(f"docengine_stdout={str(render_details.get('stdout')).strip()}")
        if render_details.get("stderr"):
            _print_result(f"docengine_stderr={str(render_details.get('stderr')).strip()}")
        if render_code != 0:
            code = int(render_code)

    if code == 0 and args.doc_gate:
        gate_code, gate_report = doc_gate(pf=pf)
        _print_result(f"doc_gate_status={gate_report.get('status', 'UNKNOWN')}")
        _print_result(f"doc_gate_exit_code={gate_code}")
        _print_result(f"doc_gate_report={pf / 'devfabric' / 'doc_gate_report.json'}")
        if gate_code != 0:
            code = int(gate_code)

    _print_result(f"build_run_dir={pf / 'pipeline_build_run'}")
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"exit_code={code}")
    return int(code)


def cmd_ngks_doctor(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project", None))
    pf = _resolve_pf(args, project, "ngks_doctor")
    if not _enforce_workspace_integrity(pf=pf, scope="cli_ngks_doctor"):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_graph_state_automation(
        project_root=project,
        pf=pf,
        scope="cli_ngks_doctor",
        active_profile="debug",
        active_target="doctor",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_validation_policy(
        project_root=project,
        pf=pf,
        stage="doctor",
        profile="debug",
        target="doctor",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    state = ensure_graph_state_current(project_root=project, pf=pf)
    _print_result(f"project_root={project}")
    _print_result(f"graph_tracked_file_count={state.get('tracked_file_count', 0)}")
    _print_result(f"graph_changed_since_last={state.get('changed_since_last', False)}")
    _print_result(f"PF={pf.resolve()}")
    _print_result("GATE=PASS")
    _register_bundle_safely(pf)
    return 0


def cmd_ngks_plan(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project", None))
    pf = _resolve_pf(args, project, "ngks_plan")
    if not _enforce_workspace_integrity(pf=pf, scope="cli_ngks_plan"):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_graph_state_automation(
        project_root=project,
        pf=pf,
        scope="cli_ngks_plan",
        active_profile="debug",
        active_target="plan",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_validation_policy(
        project_root=project,
        pf=pf,
        stage="plan",
        profile="debug",
        target="plan",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    state = ensure_graph_state_current(project_root=project, pf=pf)
    report = generate_graph_plan(project_root=project, pf=pf, graph_state=state)
    _print_result(f"project_root={project}")
    _print_result(f"graph_refresh_triggered={report.get('graph_refresh_triggered', False)}")
    _print_result(f"PF={pf.resolve()}")
    _print_result("GATE=PASS")
    _register_bundle_safely(pf)
    return 0


def cmd_ngks_test(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project", None))
    pf = _resolve_pf(args, project, "ngks_test")
    if not _enforce_graph_state_automation(
        project_root=project,
        pf=pf,
        scope="cli_ngks_test",
        active_profile="debug",
        active_target="test",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_validation_policy(
        project_root=project,
        pf=pf,
        stage="test",
        profile="debug",
        target="test",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    command = [sys.executable, "-m", "pytest"]
    if str(getattr(args, "path", "")).strip():
        command.append(str(args.path).strip())
    proc = subprocess.run(command, cwd=str(project), check=False, capture_output=True, text=True)
    _write_json(
        pf / "test_execution_report.json",
        {
            "command": command,
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "generated_at": _iso_now(),
        },
    )
    _print_result(proc.stdout or "")
    if proc.stderr:
        _print_result(proc.stderr)
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"GATE={'PASS' if int(proc.returncode) == 0 else 'FAIL'}")
    _register_bundle_safely(pf)
    return int(proc.returncode)


def cmd_ngks_ship(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project", None))
    pf = _resolve_pf(args, project, "ngks_ship")
    if not _enforce_graph_state_automation(
        project_root=project,
        pf=pf,
        scope="cli_ngks_ship",
        active_profile="release",
        active_target="ship",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    if not _enforce_validation_policy(
        project_root=project,
        pf=pf,
        stage="ship",
        profile="release",
        target="ship",
    ):
        _register_bundle_safely(pf)
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 2
    script_path = (project / "tools" / "make_release_bundle.ps1").resolve()
    if not script_path.exists():
        _print_result(f"error=missing_release_script:{script_path}")
        return 2
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    proc = subprocess.run(command, cwd=str(project), check=False)
    return int(proc.returncode)


def cmd_ngks_build(args: argparse.Namespace) -> int:
    build_args = argparse.Namespace(
        project_path=getattr(args, "project", "."),
        pf=getattr(args, "pf", None),
        backup_root=None,
        mode=str(getattr(args, "mode", "debug")),
        profile=getattr(args, "profile", "debug") or "debug",
        backend="buildcore",
        target=getattr(args, "target", None),
        jobs=getattr(args, "jobs", None),
        render_doc=False,
        doc_gate=False,
    )
    return cmd_build(build_args)


def cmd_ngks_graph_monitor(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project", None))
    pf = _resolve_pf(args, project, "graph_monitor")
    return start_background_graph_monitor(
        project_root=project,
        pf=pf,
        poll_seconds=float(getattr(args, "poll_seconds", 2.0) or 2.0),
        max_cycles=int(getattr(args, "max_cycles", 0) or 0),
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    project = _resolve_project_root(args.project_path)
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "doctor")
    code = doctor_toolchain(project, pf)
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"toolchain_report={pf / 'toolchain_report.json'}")
    _print_result(f"exit_code={code}")
    return int(code)


def cmd_run(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    build_detected, build_system, build_detect_reason = _detect_build_inputs(project_root)
    build_root = _resolve_detected_build_root(project_root, build_detect_reason)
    run_id = _runid_now()
    run_dir = project_root / "_proof" / "runs" / f"devfabric_run_{run_id}"

    env_dir = run_dir / "10_envcapsule"
    graph_dir = run_dir / "20_graph"
    buildcore_dir = run_dir / "30_buildcore"
    library_dir = run_dir / "40_library"
    for path in (run_dir, env_dir, graph_dir, buildcore_dir, library_dir):
        path.mkdir(parents=True, exist_ok=True)

    _write_text(
        run_dir / "00_run_header.txt",
        "\n".join(
            [
                f"run_id={run_id}",
                f"timestamp={_iso_now()}",
                f"project_root={project_root}",
                f"profile={args.profile or ''}",
                f"target={args.target or ''}",
                f"mode={args.mode}",
                "",
            ]
        ),
    )

    node_package_json = _resolve_node_package_json(project_root, build_detect_reason)
    node_toolchain_decision: dict[str, object] = {
        "repo_root": str(project_root),
        "package_json_path": "",
        "evidence_found": {
            "package_json": False,
            "pnpm_lock": False,
            "npm_lock": False,
            "yarn_lock": False,
            "npmrc": False,
            "pnpmfile": False,
            "ngk_profile": False,
        },
        "policy_preference": ["pnpm", "npm"],
        "selected_manager": "",
        "selected_manager_available": False,
        "node_runtime_available": bool(shutil.which("node")),
        "reason": "not_applicable",
        "repo_boundary_enforced": True,
        "scan_scope": "repo_root_only",
    }
    if build_detected and build_system == "node":
        node_toolchain_decision = detect_node_toolchain(project_root, node_package_json)
    _write_text(run_dir / "node_toolchain_decision.json", json.dumps(node_toolchain_decision, indent=2))

    evidence = node_toolchain_decision.get("evidence_found", {}) if isinstance(node_toolchain_decision, dict) else {}
    lock_hits = []
    if isinstance(evidence, dict):
        if bool(evidence.get("pnpm_lock", False)):
            lock_hits.append("pnpm-lock.yaml")
        if bool(evidence.get("npm_lock", False)):
            lock_hits.append("package-lock.json")
        if bool(evidence.get("yarn_lock", False)):
            lock_hits.append("yarn.lock")
    conflict_detected = build_detected and build_system == "node" and len(lock_hits) > 1
    conflict_outcome = {
        "conflict_detected": bool(conflict_detected),
        "conflict_type": "node_package_manager_lockfile_conflict" if conflict_detected else "none",
        "conflicting_inputs": lock_hits,
        "resolution_policy_used": "lockfile_precedence_pnpm_then_npm_then_yarn_else_policy",
        "selected_resolution": str(node_toolchain_decision.get("selected_manager", "")) if isinstance(node_toolchain_decision, dict) else "",
        "reason": str(node_toolchain_decision.get("reason", "")) if isinstance(node_toolchain_decision, dict) else "",
        "confidence": "high" if conflict_detected else "none",
        "unresolved_risk": "none" if not conflict_detected else "lockfile divergence risk if lockfiles disagree",
    }
    _write_text(run_dir / "conflict_outcome.json", json.dumps(conflict_outcome, indent=2))

    stage_map = {
        "envcapsule": env_dir,
        "graph": graph_dir,
        "buildcore": buildcore_dir,
        "library": library_dir,
    }
    stage_state: dict[str, dict[str, str]] = {
        key: {"status": "skipped", "reason": "not_reached"} for key in stage_map
    }

    def _mark_stage(stage_key: str, status: str, reason: str) -> None:
        stage_state[stage_key] = {"status": status, "reason": reason}
        _write_stage_sentinel(stage_map[stage_key], stage_key, status, reason)

    for key in stage_map:
        _mark_stage(key, "skipped", "not_reached")

    env_lock = project_root / "env_capsule.lock.json"
    env_hash = project_root / "env_capsule.hash.txt"
    plan_file = build_root / "build_plan.json"
    plan_hash = build_root / "build_plan.hash.txt"
    env_required_outputs = [env_lock, env_hash]
    graph_required_outputs = [plan_file, plan_hash]
    env_hash_value = ""
    plan_hash_value = ""
    env_hash_reason = "skipped_due_to_precondition"
    plan_hash_reason = "skipped_due_to_precondition"
    requested_target = str(args.target or "").strip()
    missing_tool = _missing_required_tool(build_system) if build_detected else None
    if build_detected and build_system == "node":
        if not bool(node_toolchain_decision.get("node_runtime_available", False)):
            missing_tool = "node"
        elif not bool(node_toolchain_decision.get("selected_manager_available", False)):
            selected_manager = str(node_toolchain_decision.get("selected_manager", "")).strip() or "pnpm"
            missing_tool = selected_manager

    def _finish(
        *,
        exit_code: int,
        build_success: bool,
        build_action: str,
        build_reason: str,
        failure_class: str = "",
        failed_stage: str = "",
    ) -> int:
        components_state = ",".join(
            [
                f"envcapsule:{stage_state['envcapsule']['status']}({stage_state['envcapsule']['reason']})",
                f"graph:{stage_state['graph']['status']}({stage_state['graph']['reason']})",
                f"buildcore:{stage_state['buildcore']['status']}({stage_state['buildcore']['reason']})",
                f"library:{stage_state['library']['status']}({stage_state['library']['reason']})",
            ]
        )
        _write_run_summary(
            run_dir=run_dir,
            run_id=run_id,
            env_hash=env_hash_value,
            plan_hash=plan_hash_value,
            build_success=build_success,
            env_hash_reason=env_hash_reason,
            plan_hash_reason=plan_hash_reason,
            build_detected=build_detected,
            build_system=build_system,
            build_detect_reason=build_detect_reason,
            build_action=build_action,
            build_reason=build_reason,
            components_state=components_state,
            exit_code=exit_code,
            conflict_detected=bool(conflict_outcome.get("conflict_detected", False)),
            conflict_type=str(conflict_outcome.get("conflict_type", "none")),
            conflicting_inputs=",".join(str(item) for item in conflict_outcome.get("conflicting_inputs", [])),
            conflict_resolution=str(conflict_outcome.get("selected_resolution", "none")),
            conflict_confidence=str(conflict_outcome.get("confidence", "")),
            unresolved_risk=str(conflict_outcome.get("unresolved_risk", "")),
            failure_class=failure_class,
            failed_stage=failed_stage,
        )
        if int(exit_code) != 0:
            errors_path = run_dir / "30_errors.txt"
            failure_hint = _read_failure_hint(run_dir)
            action_hint = _failure_action_hint(failure_hint, build_reason)
            summary = (
                f"failure_summary: Build failed in {_stage_label(failed_stage)} "
                f"(class={failure_class or 'unknown'}, reason={build_reason}). "
                f"Action: {action_hint}. Details: {errors_path}"
            )
            if failure_hint:
                summary += f". Hint: {failure_hint}"
            _print_result(summary)
        _print_result(f"run_id={run_id}")
        _print_result(f"proof_dir={run_dir}")
        _print_result(f"exit_code={int(exit_code)}")
        _register_bundle_safely(run_dir)
        return int(exit_code)

    if not build_detected:
        static_site_root = _detect_static_site_root(project_root)
        if requested_target == "build" and static_site_root is not None:
            build_detected = True
            build_system = "static_site"
            try:
                build_detect_reason = str(static_site_root.relative_to(project_root).as_posix() + "/index.html")
            except ValueError:
                build_detect_reason = "index.html"

            env_hash_reason = "no_build_inputs"
            plan_hash_reason = "no_build_inputs"
            _mark_stage("envcapsule", "skipped", "no_build_inputs")
            _mark_stage("graph", "skipped", "no_build_inputs")
            _mark_stage("buildcore", "ran", "attempted_static_site")

            static_ok, static_reason = _run_static_site_build(project_root, static_site_root)
            if not static_ok:
                _mark_stage("buildcore", "ran", "build_failed")
                _mark_stage("library", "skipped", "upstream_failed")
                _append_failure(
                    run_dir,
                    StageResult(stage="30_buildcore", exit_code=1, stdout="", stderr=static_reason),
                    failure_class="build_failed",
                )
                return _finish(
                    exit_code=1,
                    build_success=False,
                    build_action="attempted",
                    build_reason="build_failed",
                    failure_class="build_failed",
                    failed_stage="30_buildcore",
                )

            _mark_stage("buildcore", "ran", "ok")
            _mark_stage("library", "ran", "attempted")
            stage = _run_stage_with_resolver(
                stage="40_library",
                stage_dir=library_dir,
                project_root=project_root,
                component_name="ngkslibrary",
                module_name="ngkslibrary",
                tail_args=[
                    "assemble",
                    "--run-proof",
                    str(run_dir),
                    "--pf",
                    str(library_dir),
                    "--run-id",
                    run_id,
                    "--build-system",
                    build_system,
                    "--build-action",
                    "attempted",
                    "--build-reason",
                    "build_completed_static_site",
                    "--exit-code",
                    "0",
                ],
            )
            if stage.exit_code != 0:
                _mark_stage("library", "ran", "build_failed")
                _append_failure(
                    run_dir,
                    stage,
                    failure_class="build_failed",
                    stdout_path=library_dir / "01_stdout.txt",
                    stderr_path=library_dir / "02_stderr.txt",
                )
                return _finish(
                    exit_code=1,
                    build_success=False,
                    build_action="attempted",
                    build_reason="build_failed",
                    failure_class="build_failed",
                    failed_stage="40_library",
                )

            _mark_stage("library", "ran", "ok")
            return _finish(
                exit_code=0,
                build_success=True,
                build_action="attempted",
                build_reason="build_completed_static_site",
            )

        _ensure_ngks_operating_rules(project_root)
        env_hash_reason = "no_build_inputs"
        plan_hash_reason = "no_build_inputs"
        _mark_stage("envcapsule", "skipped", "no_build_inputs")
        _mark_stage("graph", "skipped", "no_build_inputs")
        _mark_stage("buildcore", "skipped", "no_build_inputs")
        _mark_stage("library", "ran", "attempted")
        stage = _run_stage_with_resolver(
            stage="40_library",
            stage_dir=library_dir,
            project_root=project_root,
            component_name="ngkslibrary",
            module_name="ngkslibrary",
            tail_args=[
                "assemble",
                "--run-proof",
                str(run_dir),
                "--pf",
                str(library_dir),
                "--run-id",
                run_id,
                "--build-system",
                build_system,
                "--build-action",
                "skipped",
                "--build-reason",
                "no_build_inputs",
                "--exit-code",
                "0",
            ],
        )
        if stage.exit_code != 0:
            _mark_stage("library", "ran", "tool_missing" if stage.failure_class == "component_missing" else "build_failed")
            _append_failure(
                run_dir,
                stage,
                failure_class="tool_missing" if stage.failure_class == "component_missing" else "build_failed",
                stdout_path=library_dir / "01_stdout.txt",
                stderr_path=library_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="skipped",
                build_reason="tool_missing:ngkslibrary",
                failure_class="tool_missing",
                failed_stage="40_library",
            )
        _mark_stage("library", "ran", "ok")
        return _finish(exit_code=0, build_success=True, build_action="skipped", build_reason="no_build_inputs")

    if missing_tool:
        _mark_stage("envcapsule", "skipped", f"missing_tool:{missing_tool}")
        _mark_stage("graph", "skipped", f"missing_tool:{missing_tool}")
        _mark_stage("buildcore", "ran", f"missing_tool:{missing_tool}")
        _mark_stage("library", "skipped", "upstream_failed")
        _write_text(buildcore_dir / "30_errors.txt", f"missing_tool:{missing_tool}\n")
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="skipped",
            build_reason=f"missing_tool:{missing_tool}",
            failure_class="precondition_failed",
            failed_stage="30_buildcore",
        )

    if requested_target and build_system == "node" and not _node_target_exists_in_package(node_package_json, requested_target):
        env_hash_reason = "skipped_due_to_precondition"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "skipped", "missing_required_target")
        _mark_stage("graph", "skipped", "missing_required_target")
        _mark_stage("buildcore", "skipped", "missing_required_target")
        _mark_stage("library", "skipped", "missing_required_target")
        message = f"target '{requested_target}' is missing from {node_package_json.name} scripts"
        _write_stage_contract_files(
            stage_dir=buildcore_dir,
            mode="precheck",
            why="target resolution",
            argv=[],
            stdout="",
            stderr=message + "\n",
            exit_code=2,
        )
        _append_failure(
            run_dir,
            StageResult(stage="30_buildcore", exit_code=2, stdout="", stderr=message),
            failure_class="precondition_failed",
            stdout_path=buildcore_dir / "01_stdout.txt",
            stderr_path=buildcore_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="skipped",
            build_reason="missing_required_target",
            failure_class="precondition_failed",
            failed_stage="30_buildcore",
        )

    try:
        _mark_stage("envcapsule", "ran", "attempted")
        env_resolved = resolve_component_cmd(component_name="ngksenvcapsule", module_name="ngksenvcapsule")
        env_mode = str(env_resolved.get("mode", ""))
        env_why = str(env_resolved.get("why", ""))
        env_base_argv = [str(part) for part in list(env_resolved.get("argv", []))]
    except ComponentResolutionError as exc:
        env_err = str(exc)
        _mark_stage("envcapsule", "ran", "tool_missing")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _write_stage_contract_files(
            stage_dir=env_dir,
            mode="resolve_error",
            why="component resolver failed",
            argv=[],
            stdout="",
            stderr=env_err + ("\n" if env_err and not env_err.endswith("\n") else ""),
            exit_code=2,
        )
        failure = StageResult(stage="10_envcapsule", exit_code=2, stdout="", stderr=env_err)
        env_hash_reason = "tool_missing"
        plan_hash_reason = "skipped_due_to_precondition"
        _append_failure(
            run_dir,
            failure,
            failure_class="tool_missing",
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="tool_missing",
            failure_class="tool_missing",
            failed_stage="10_envcapsule",
        )

    resolve_stdout = ""
    resolve_stderr = ""
    resolve_exit = 0
    resolve_os_error = False
    resolve_cmd = [*env_base_argv, "resolve", "--pf", str(env_dir)]
    try:
        resolve_proc = subprocess.run(resolve_cmd, cwd=str(project_root), check=False, capture_output=True, text=True)
        resolve_stdout = resolve_proc.stdout or ""
        resolve_stderr = resolve_proc.stderr or ""
        resolve_exit = int(resolve_proc.returncode)
    except OSError as exc:
        resolve_stderr = f"{exc}\ncommand={' '.join(str(part) for part in resolve_cmd)}"
        resolve_exit = 2
        resolve_os_error = True

    env_stdout_parts = ["=== resolve ===\n", resolve_stdout]
    env_stderr_parts = ["=== resolve ===\n", resolve_stderr]

    if resolve_exit != 0:
        if resolve_os_error:
            env_hash_reason = "tool_missing"
            plan_hash_reason = "skipped_due_to_precondition"
            _mark_stage("envcapsule", "ran", "tool_missing")
            _mark_stage("graph", "skipped", "upstream_failed")
            _mark_stage("buildcore", "skipped", "upstream_failed")
            _mark_stage("library", "skipped", "upstream_failed")
            _write_stage_contract_files(
                stage_dir=env_dir,
                mode=env_mode,
                why=env_why,
                argv=resolve_cmd,
                stdout="".join(env_stdout_parts),
                stderr="".join(env_stderr_parts),
                exit_code=resolve_exit,
            )
            failure = StageResult(stage="10_envcapsule", exit_code=resolve_exit, stdout=resolve_stdout, stderr=resolve_stderr)
            _append_failure(
                run_dir,
                failure,
                failure_class="tool_missing",
                stdout_path=env_dir / "01_stdout.txt",
                stderr_path=env_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="attempted",
                build_reason="tool_missing",
                failure_class="tool_missing",
                failed_stage="10_envcapsule",
            )

        env_hash_reason = "precondition_failed"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "ran", "precondition_failed")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _write_stage_contract_files(
            stage_dir=env_dir,
            mode=env_mode,
            why=env_why,
            argv=resolve_cmd,
            stdout="".join(env_stdout_parts),
            stderr="".join(env_stderr_parts),
            exit_code=resolve_exit,
        )
        failure = StageResult(stage="10_envcapsule", exit_code=resolve_exit, stdout=resolve_stdout, stderr=resolve_stderr)
        _append_failure(
            run_dir,
            failure,
            failure_class="precondition_failed",
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="precondition_failed",
            failure_class="precondition_failed",
            failed_stage="10_envcapsule",
        )

    lock_stdout = ""
    lock_stderr = ""
    lock_exit = 0
    lock_os_error = False
    lock_cmd = [*env_base_argv, "lock", "--pf", str(env_dir)]
    try:
        lock_proc = subprocess.run(lock_cmd, cwd=str(project_root), check=False, capture_output=True, text=True)
        lock_stdout = lock_proc.stdout or ""
        lock_stderr = lock_proc.stderr or ""
        lock_exit = int(lock_proc.returncode)
    except OSError as exc:
        lock_stderr = f"{exc}\ncommand={' '.join(str(part) for part in lock_cmd)}"
        lock_exit = 2
        lock_os_error = True

    env_stdout_parts.extend(["=== lock ===\n", lock_stdout])
    env_stderr_parts.extend(["=== lock ===\n", lock_stderr])

    if lock_exit != 0:
        if lock_os_error:
            env_hash_reason = "tool_missing"
            plan_hash_reason = "skipped_due_to_precondition"
            _mark_stage("envcapsule", "ran", "tool_missing")
            _mark_stage("graph", "skipped", "upstream_failed")
            _mark_stage("buildcore", "skipped", "upstream_failed")
            _mark_stage("library", "skipped", "upstream_failed")
            _write_stage_contract_files(
                stage_dir=env_dir,
                mode=env_mode,
                why=env_why,
                argv=lock_cmd,
                stdout="".join(env_stdout_parts),
                stderr="".join(env_stderr_parts),
                exit_code=lock_exit,
            )
            failure = StageResult(stage="10_envcapsule", exit_code=lock_exit, stdout=lock_stdout, stderr=lock_stderr)
            _append_failure(
                run_dir,
                failure,
                failure_class="tool_missing",
                stdout_path=env_dir / "01_stdout.txt",
                stderr_path=env_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="attempted",
                build_reason="tool_missing",
                failure_class="tool_missing",
                failed_stage="10_envcapsule",
            )

        _, missing_outputs = _verify_required_outputs(env_required_outputs)
        if missing_outputs:
            env_hash_reason = "missing_outputs"
            plan_hash_reason = "skipped_due_to_precondition"
            _mark_stage("envcapsule", "ran", "missing_required_outputs")
            _mark_stage("graph", "skipped", "upstream_failed")
            _mark_stage("buildcore", "skipped", "upstream_failed")
            _mark_stage("library", "skipped", "upstream_failed")
            _write_stage_contract_files(
                stage_dir=env_dir,
                mode=env_mode,
                why=env_why,
                argv=lock_cmd,
                stdout="".join(env_stdout_parts),
                stderr="".join(env_stderr_parts),
                exit_code=lock_exit,
            )
            failure = StageResult(stage="10_envcapsule", exit_code=lock_exit, stdout=lock_stdout, stderr=lock_stderr)
            _append_failure(
                run_dir,
                failure,
                failure_class="precondition_failed",
                missing_outputs=missing_outputs,
                stdout_path=env_dir / "01_stdout.txt",
                stderr_path=env_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="attempted",
                build_reason="missing_required_outputs",
                failure_class="precondition_failed",
                failed_stage="10_envcapsule",
            )

        _write_stage_contract_files(
            stage_dir=env_dir,
            mode=env_mode,
            why=env_why,
            argv=lock_cmd,
            stdout="".join(env_stdout_parts),
            stderr="".join(env_stderr_parts),
            exit_code=lock_exit,
        )
        failure = StageResult(stage="10_envcapsule", exit_code=lock_exit, stdout=lock_stdout, stderr=lock_stderr)
        env_hash_reason = "precondition_failed"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "ran", "precondition_failed")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            failure,
            failure_class="precondition_failed",
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="precondition_failed",
            failure_class="precondition_failed",
            failed_stage="10_envcapsule",
        )

    env_hash_value, env_hash_reason = _hash_with_reason(env_hash, True)

    verify_cmd = [*env_base_argv, "verify", "--lock", str(env_lock), "--pf", str(env_dir)]
    verify_stdout = ""
    verify_stderr = ""
    verify_exit = 0
    try:
        verify_proc = subprocess.run(verify_cmd, cwd=str(project_root), check=False, capture_output=True, text=True)
        verify_stdout = verify_proc.stdout or ""
        verify_stderr = verify_proc.stderr or ""
        verify_exit = int(verify_proc.returncode)
    except OSError as exc:
        verify_stderr = str(exc)
        verify_exit = 2

    env_stdout_parts.extend(["=== verify ===\n", verify_stdout])
    env_stderr_parts.extend(["=== verify ===\n", verify_stderr])
    _write_stage_contract_files(
        stage_dir=env_dir,
        mode=env_mode,
        why=env_why,
        argv=verify_cmd,
        stdout="".join(env_stdout_parts),
        stderr="".join(env_stderr_parts),
        exit_code=verify_exit,
    )

    if verify_exit != 0:
        ok_outputs, missing_outputs = _verify_required_outputs(env_required_outputs)
        if not ok_outputs:
            env_hash_reason = "missing_outputs"
            plan_hash_reason = "skipped_due_to_precondition"
            _mark_stage("envcapsule", "ran", "missing_required_outputs")
            _mark_stage("graph", "skipped", "upstream_failed")
            _mark_stage("buildcore", "skipped", "upstream_failed")
            _mark_stage("library", "skipped", "upstream_failed")
            failure = StageResult(stage="10_envcapsule", exit_code=verify_exit, stdout=verify_stdout, stderr=verify_stderr)
            _append_failure(
                run_dir,
                failure,
                failure_class="precondition_failed",
                missing_outputs=missing_outputs,
                stdout_path=env_dir / "01_stdout.txt",
                stderr_path=env_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="attempted",
                build_reason="missing_required_outputs",
                failure_class="precondition_failed",
                failed_stage="10_envcapsule",
            )

        failure = StageResult(stage="10_envcapsule", exit_code=verify_exit, stdout=verify_stdout, stderr=verify_stderr)
        env_hash_reason = "stage_failed"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "ran", "precondition_failed")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            failure,
            failure_class="precondition_failed",
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="precondition_failed",
            failure_class="precondition_failed",
            failed_stage="10_envcapsule",
        )

    ok_outputs, missing_outputs = _verify_required_outputs(env_required_outputs)
    if not ok_outputs:
        env_hash_reason = "missing_outputs"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "ran", "missing_required_outputs")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        failure = StageResult(stage="10_envcapsule", exit_code=verify_exit, stdout=verify_stdout, stderr=verify_stderr)
        _append_failure(
            run_dir,
            failure,
            failure_class="precondition_failed",
            missing_outputs=missing_outputs,
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="missing_required_outputs",
            failure_class="precondition_failed",
            failed_stage="10_envcapsule",
        )

    try:
        _copy_required_file(env_lock, env_dir / "env_capsule.lock.json")
        _copy_required_file(env_hash, env_dir / "env_capsule.hash.txt")
    except ValueError as exc:
        env_hash_reason = "missing_outputs"
        plan_hash_reason = "skipped_due_to_precondition"
        _mark_stage("envcapsule", "ran", "missing_required_outputs")
        _mark_stage("graph", "skipped", "upstream_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            StageResult(stage="10_envcapsule", exit_code=2, stdout="", stderr=str(exc)),
            failure_class="precondition_failed",
            missing_outputs=[env_lock.name, env_hash.name],
            stdout_path=env_dir / "01_stdout.txt",
            stderr_path=env_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="missing_required_outputs",
            failure_class="precondition_failed",
            failed_stage="10_envcapsule",
        )

    env_hash_value, env_hash_reason = _hash_with_reason(env_hash, True)
    _mark_stage("envcapsule", "ran", "ok")

    # Always require graph to regenerate plan artifacts for the current run.
    for stale_path in (plan_file, plan_hash):
        try:
            if stale_path.exists():
                stale_path.unlink()
        except OSError:
            pass

    _mark_stage("graph", "ran", "attempted")
    graph_tail_args = [
        "plan",
        "--project",
        str(build_root),
        "--mode",
        args.mode,
        "--env-capsule-lock",
        str(env_lock),
        "--pf",
        str(graph_dir),
    ]
    if args.profile:
        graph_tail_args.extend(["--profile", str(args.profile)])
    if args.target:
        graph_tail_args.extend(["--target", str(args.target)])

    stage = _run_stage_with_resolver(
        stage="20_graph",
        stage_dir=graph_dir,
        project_root=project_root,
        component_name="ngksgraph",
        module_name="ngksgraph",
        tail_args=graph_tail_args,
    )
    if stage.exit_code != 0:
        ok_outputs, missing_outputs = _verify_required_outputs(graph_required_outputs)
        if not ok_outputs:
            plan_hash_reason = "missing_outputs"
            _mark_stage("graph", "ran", "missing_required_outputs")
            _mark_stage("buildcore", "skipped", "upstream_failed")
            _mark_stage("library", "skipped", "upstream_failed")
            _append_failure(
                run_dir,
                stage,
                failure_class="precondition_failed",
                missing_outputs=missing_outputs,
                stdout_path=graph_dir / "01_stdout.txt",
                stderr_path=graph_dir / "02_stderr.txt",
            )
            return _finish(
                exit_code=2,
                build_success=False,
                build_action="attempted",
                build_reason="missing_required_outputs",
                failure_class="precondition_failed",
                failed_stage="20_graph",
            )

        mapped_failure = "tool_missing" if stage.failure_class == "component_missing" else "precondition_failed"
        plan_hash_reason = "tool_missing" if mapped_failure == "tool_missing" else "precondition_failed"
        _mark_stage("graph", "ran", "tool_missing" if mapped_failure == "tool_missing" else "precondition_failed")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            stage,
            failure_class=mapped_failure,
            stdout_path=graph_dir / "01_stdout.txt",
            stderr_path=graph_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="tool_missing" if mapped_failure == "tool_missing" else "precondition_failed",
            failure_class=mapped_failure,
            failed_stage="20_graph",
        )

    ok_outputs, missing_outputs = _verify_required_outputs(graph_required_outputs)
    if not ok_outputs:
        plan_hash_reason = "missing_outputs"
        _mark_stage("graph", "ran", "missing_required_outputs")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            StageResult(stage="20_graph", exit_code=0, stdout="", stderr="required outputs missing"),
            failure_class="precondition_failed",
            missing_outputs=missing_outputs,
            stdout_path=graph_dir / "01_stdout.txt",
            stderr_path=graph_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="missing_required_outputs",
            failure_class="precondition_failed",
            failed_stage="20_graph",
        )

    try:
        if build_system == "node":
            selected_manager = str(node_toolchain_decision.get("selected_manager", "")).strip().lower()
            _apply_node_package_manager_to_plan(plan_file, selected_manager)
        _copy_required_file(plan_file, graph_dir / "build_plan.json")
        _copy_required_file(plan_hash, graph_dir / "build_plan.hash.txt")
    except ValueError as exc:
        plan_hash_reason = "missing_outputs"
        _mark_stage("graph", "ran", "missing_required_outputs")
        _mark_stage("buildcore", "skipped", "upstream_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            StageResult(stage="20_graph", exit_code=2, stdout="", stderr=str(exc)),
            failure_class="precondition_failed",
            missing_outputs=[plan_file.name, plan_hash.name],
            stdout_path=graph_dir / "01_stdout.txt",
            stderr_path=graph_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=2,
            build_success=False,
            build_action="attempted",
            build_reason="missing_required_outputs",
            failure_class="precondition_failed",
            failed_stage="20_graph",
        )

    plan_hash_value, plan_hash_reason = _hash_with_reason(plan_hash, True)
    _mark_stage("graph", "ran", "ok")

    build_tail_args = [
        "run",
        "--plan",
        str(plan_file),
        "--env-lock",
        str(env_lock),
        "--pf",
        str(buildcore_dir),
    ]

    _mark_stage("buildcore", "ran", "attempted")
    stage = _run_stage_with_resolver(
        stage="30_buildcore",
        stage_dir=buildcore_dir,
        project_root=project_root,
        component_name="ngksbuildcore",
        module_name="ngksbuildcore",
        tail_args=build_tail_args,
    )
    if stage.exit_code != 0:
        mapped_failure = "tool_missing" if stage.failure_class == "component_missing" else "build_failed"
        mapped_code = 2 if mapped_failure == "tool_missing" else 1
        _mark_stage("buildcore", "ran", "tool_missing" if mapped_failure == "tool_missing" else "build_failed")
        _mark_stage("library", "skipped", "upstream_failed")
        _append_failure(
            run_dir,
            stage,
            failure_class=mapped_failure,
            stdout_path=buildcore_dir / "01_stdout.txt",
            stderr_path=buildcore_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=mapped_code,
            build_success=False,
            build_action="attempted",
            build_reason="tool_missing" if mapped_failure == "tool_missing" else "build_failed",
            failure_class=mapped_failure,
            failed_stage="30_buildcore",
        )

    _mark_stage("buildcore", "ran", "ok")
    _mark_stage("library", "ran", "attempted")
    stage = _run_stage_with_resolver(
        stage="40_library",
        stage_dir=library_dir,
        project_root=project_root,
        component_name="ngkslibrary",
        module_name="ngkslibrary",
        tail_args=[
            "assemble",
            "--run-proof",
            str(run_dir),
            "--pf",
            str(library_dir),
            "--run-id",
            run_id,
            "--build-system",
            build_system,
            "--build-action",
            "attempted",
            "--build-reason",
            "build_completed",
            "--exit-code",
            "0",
        ],
    )
    if stage.exit_code != 0:
        mapped_failure = "tool_missing" if stage.failure_class == "component_missing" else "build_failed"
        mapped_code = 2 if mapped_failure == "tool_missing" else 1
        _mark_stage("library", "ran", "tool_missing" if mapped_failure == "tool_missing" else "build_failed")
        _append_failure(
            run_dir,
            stage,
            failure_class=mapped_failure,
            stdout_path=library_dir / "01_stdout.txt",
            stderr_path=library_dir / "02_stderr.txt",
        )
        return _finish(
            exit_code=mapped_code,
            build_success=False,
            build_action="attempted",
            build_reason="tool_missing" if mapped_failure == "tool_missing" else "build_failed",
            failure_class=mapped_failure,
            failed_stage="40_library",
        )

    _mark_stage("library", "ran", "ok")
    _write_run_summary(
        run_dir=run_dir,
        run_id=run_id,
        env_hash=env_hash_value,
        plan_hash=plan_hash_value,
        build_success=True,
        env_hash_reason=env_hash_reason,
        plan_hash_reason=plan_hash_reason,
        build_detected=build_detected,
        build_system=build_system,
        build_detect_reason=build_detect_reason,
        build_action="attempted",
        build_reason="build_completed",
        components_state=",".join(
            [
                f"envcapsule:{stage_state['envcapsule']['status']}({stage_state['envcapsule']['reason']})",
                f"graph:{stage_state['graph']['status']}({stage_state['graph']['reason']})",
                f"buildcore:{stage_state['buildcore']['status']}({stage_state['buildcore']['reason']})",
                f"library:{stage_state['library']['status']}({stage_state['library']['reason']})",
            ]
        ),
        exit_code=0,
        conflict_detected=bool(conflict_outcome.get("conflict_detected", False)),
        conflict_type=str(conflict_outcome.get("conflict_type", "none")),
        conflicting_inputs=",".join(str(item) for item in conflict_outcome.get("conflicting_inputs", [])),
        conflict_resolution=str(conflict_outcome.get("selected_resolution", "none")),
        conflict_confidence=str(conflict_outcome.get("confidence", "")),
        unresolved_risk=str(conflict_outcome.get("unresolved_risk", "")),
    )

    _print_result(f"run_id={run_id}")
    _print_result(f"proof_dir={run_dir}")
    _print_result("exit_code=0")
    _register_bundle_safely(run_dir)
    return 0


def cmd_term_run(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project_path", None))
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "term")
    cwd = Path(args.cwd).resolve() if args.cwd else None
    plan = detect_shell(args.command)
    enabled, source = resolve_smart_terminal_enabled(args.smart_terminal)

    if enabled:
        code, run_dir = run_shell(plan, pf=pf, cwd=cwd)
    else:
        code, run_dir = run_shell_direct(args.command, pf=pf, cwd=cwd, plan=plan)

    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)

    _print_result(f"smart_terminal_enabled={enabled}")
    _print_result(f"smart_terminal_source={source}")
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"term_run_dir={run_dir}")
    _print_result(f"exit_code={code}")
    return int(code)


def cmd_render_doc(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project_path", None))
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "render_doc")
    code, details = run_docengine_render(pf=pf, devfabric_root=DEVFABRIC_ROOT)
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"docengine_exit_code={code}")
    _print_result(f"docengine_root={details.get('ngkslibrary_root', '')}")
    if details.get("stdout"):
        _print_result(f"docengine_stdout={str(details.get('stdout')).strip()}")
    if details.get("stderr"):
        _print_result(f"docengine_stderr={str(details.get('stderr')).strip()}")
    return int(code)


def cmd_doc_gate(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project_path", None))
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "doc_gate")
    code, report = doc_gate(pf=pf)
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"doc_gate_status={report.get('status', 'UNKNOWN')}")
    _print_result(f"doc_gate_exit_code={code}")
    _print_result(f"doc_gate_report={pf / 'devfabric' / 'doc_gate_report.json'}")
    return int(code)


def _eco_pkg_entry(dist_name: str, module_name: str) -> tuple[str, str]:
    version = "not-installed"
    location = "not-importable"
    try:
        version = importlib.metadata.version(dist_name)
    except Exception:
        pass
    try:
        mod = importlib.import_module(module_name)
        location = str(getattr(mod, "__file__", ""))
    except Exception:
        pass
    return version, location


def cmd_eco_doctor(args: argparse.Namespace) -> int:
    del args
    entries = [
        ("ngksdevfabric", "ngksdevfabric"),
        ("ngksgraph", "ngksgraph"),
        ("ngksbuildcore", "ngksbuildcore"),
        ("ngksenvcapsule", "ngksenvcapsule"),
        ("ngkslibrary", "ngkslibrary"),
    ]
    rows: list[tuple[str, str, str]] = []
    versions: list[str] = []
    for dist_name, module_name in entries:
        version, location = _eco_pkg_entry(dist_name, module_name)
        rows.append((dist_name, version, location))
        versions.append(version)

    mismatch = len({v for v in versions if v != "not-installed"}) > 1
    for name, version, location in rows:
        _print_result(f"{name}: version={version} module_file={location}")
    if mismatch:
        _print_result("eco_doctor=mismatch_detected")
        return 2
    _print_result("eco_doctor=ok")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    project = _resolve_project_root(getattr(args, "project_path", None))
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "devfab_explain_engine")

    query_mode = str(getattr(args, "explain_cmd", "")).strip()
    query: dict[str, object] = {"mode": query_mode}
    if query_mode == "file":
        query["path"] = str(getattr(args, "path", ""))
    elif query_mode == "route":
        query["route_id"] = str(getattr(args, "route_id", ""))
    elif query_mode == "dependency":
        query["component"] = str(getattr(args, "component", ""))

    result, ctx = run_explain_query(query, project)
    saved = persist_explain_bundle(pf=pf, project_root=project, query=query, result=result, ctx=ctx)

    if backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _register_bundle_safely(pf)

    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"entity={result.get('entity', '')}")
    _print_result(f"entity_type={result.get('entity_type', '')}")
    _print_result(f"confidence={result.get('confidence', '')}")
    _print_result(f"queries_executed={saved.get('queries_executed', 0)}")
    _print_result(f"final_gate={saved.get('final_gate', 'PARTIAL')}")
    _print_result("exit_code=0")
    return 0


def _resolve_baseline_arg(project_root: Path, baseline: str, compare: str, fallback_baseline_root: Path | None = None) -> Path:
    baseline_raw = (baseline or "").strip()
    compare_raw = (compare or "").strip()

    if baseline_raw:
        candidate = Path(baseline_raw)
        return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()

    if compare_raw:
        compare_candidate = Path(compare_raw)
        if compare_candidate.is_absolute() and compare_candidate.exists():
            return compare_candidate.resolve()

        direct = (project_root / compare_raw).resolve()
        if direct.exists():
            return direct

        cert_named = (project_root / "certification" / compare_raw).resolve()
        if cert_named.exists():
            return cert_named

        proof_named = (project_root / "_proof" / compare_raw).resolve()
        if proof_named.exists():
            return proof_named

    if fallback_baseline_root is not None:
        return fallback_baseline_root.resolve()

    raise ValueError("baseline_required: provide --baseline <path> or --compare <baseline_name_or_path>")


def cmd_certify_target_check(args: argparse.Namespace) -> int:
    target_project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "certification_target_check")

    contract_path_raw = str(getattr(args, "target_contract", "") or "").strip()
    contract_path = Path(contract_path_raw).resolve() if contract_path_raw else None
    require_contract = str(getattr(args, "require_contract", "on") or "on").lower() != "off"

    target_result = run_target_validation_precheck(
        project_root=target_project_root,
        pf=pf,
        explicit_contract_path=contract_path,
        require_contract=require_contract,
    )

    _register_bundle_safely(pf)
    _print_result(f"project_root={target_project_root}")
    _print_result(f"project_name={target_result.project_name}")
    _print_result(f"target_capability_state={target_result.state}")
    _print_result(f"baseline_root={target_result.baseline_root}")
    _print_result(f"scenario_index_path={target_result.scenario_index_path}")
    _print_result(f"subtarget_count={len(target_result.subtargets)}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result(f"GATE={'PASS' if target_result.state != 'CERTIFICATION_NOT_READY' else 'FAIL'}")
    return 0 if target_result.state != "CERTIFICATION_NOT_READY" else 1


def cmd_certify(args: argparse.Namespace) -> int:
    target_project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()
    expected_proof_root = (repo_root / "_proof").resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "certification_compare")

    contract_path_raw = str(getattr(args, "target_contract", "") or "").strip()
    contract_path = Path(contract_path_raw).resolve() if contract_path_raw else None
    require_contract = str(getattr(args, "require_contract", "on") or "on").lower() != "off"

    target_result = run_target_validation_precheck(
        project_root=target_project_root,
        pf=pf,
        explicit_contract_path=contract_path,
        require_contract=require_contract,
    )

    if target_result.state == "CERTIFICATION_NOT_READY":
        _register_bundle_safely(pf)
        _print_result(f"project_root={target_project_root}")
        _print_result(f"target_capability_state={target_result.state}")
        _print_result(f"PF={pf.resolve()}")
        _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
        _print_result("GATE=FAIL")
        return 1

    baseline_path = Path("")
    current_run_path = Path("")
    if not target_result.subtargets:
        baseline_path = _resolve_baseline_arg(
            target_project_root,
            str(getattr(args, "baseline", "") or ""),
            str(getattr(args, "compare", "") or ""),
            target_result.baseline_root,
        )
        current_run_path_raw = str(getattr(args, "current_run", "") or "").strip()
        if current_run_path_raw:
            current_run_path = Path(current_run_path_raw).resolve()
        else:
            current_run_path = target_project_root

        if not baseline_path.exists():
            raise ValueError(f"baseline_path_missing:{baseline_path}")
        if not current_run_path.exists():
            raise ValueError(f"current_run_path_missing:{current_run_path}")

    proof_root = pf.resolve().parent.parent
    proof_root_match = proof_root == expected_proof_root
    _write_text(
        pf / "14_proof_root_check.txt",
        "\n".join(
            [
                f"repo={repo_root}",
                f"proofRoot={proof_root}",
                f"expectedProofRoot={expected_proof_root}",
                f"match={str(proof_root_match).lower()}",
                "",
            ]
        ),
    )
    if not proof_root_match:
        _print_result(f"baseline_path={baseline_path}")
        _print_result(f"current_run_path={current_run_path}")
        _print_result(f"PF={pf.resolve()}")
        _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
        _print_result("GATE=FAIL")
        return 1

    policy = ComparisonPolicy(
        diagnostic_score_tolerance=float(getattr(args, "tolerance", 0.02) or 0.02),
        diagnostic_score_improvement_threshold=float(getattr(args, "improvement_threshold", 0.03) or 0.03),
        severe_core_drop_threshold=float(getattr(args, "severe_drop_threshold", 0.15) or 0.15),
    )
    if target_result.subtargets:
        result = run_subtarget_rollup_comparison(
            repo_root=repo_root,
            project_root=target_project_root,
            pf=pf,
            target_result=target_result,
            comparison_policy=policy,
        )
    else:
        result = run_certification_comparison(
            repo_root=repo_root,
            baseline_path=baseline_path,
            current_path=current_run_path,
            pf=pf,
            policy=policy,
            supported_baseline_versions=target_result.supported_baseline_versions,
            profile_project_root=target_project_root,
        )

    actual_pf = Path(str(result.get("pf", pf.resolve()))).resolve()
    actual_zip = Path(str(result.get("zip", pf.with_suffix(".zip").resolve()))).resolve()
    pf_starts = str(actual_pf).lower().startswith(str(expected_proof_root).lower())
    zip_starts = str(actual_zip).lower().startswith(str(expected_proof_root).lower())
    comparison_gate_pass = str(result.get("gate", "FAIL")).upper() == "PASS"
    compatibility_ok = str(result.get("compatibility_state", "INCOMPATIBLE")).upper() != "INCOMPATIBLE"
    target_ready = target_result.state != "CERTIFICATION_NOT_READY"
    gate_rule_satisfied = pf_starts and zip_starts and proof_root_match and comparison_gate_pass and compatibility_ok and target_ready
    final_gate = "PASS" if gate_rule_satisfied else "FAIL"

    _write_text(
        actual_pf / "15_pf_zip_assertions.txt",
        "\n".join(
            [
                f"pf={actual_pf}",
                f"zip={actual_zip}",
                f"pf_starts_with_expected={str(pf_starts).lower()}",
                f"zip_starts_with_expected={str(zip_starts).lower()}",
                f"gate_rule_satisfied={str(gate_rule_satisfied).lower()}",
                "",
            ]
        ),
    )

    _register_bundle_safely(actual_pf)
    if target_result.subtargets:
        _print_result("baseline_path=rollup_subtarget_mode")
        _print_result("current_run_path=rollup_subtarget_mode")
    else:
        _print_result(f"baseline_path={baseline_path}")
        _print_result(f"current_run_path={current_run_path}")
    _print_result(f"target_capability_state={target_result.state}")
    _print_result(f"overall_classification={result.get('classification', '')}")
    _print_result(f"compatibility_state={result.get('compatibility_state', '')}")
    _print_result(f"strongest_improvement={result.get('strongest_improvement', {}).get('metric', 'none')}")
    _print_result(f"worst_regression={result.get('worst_regression', {}).get('metric', 'none')}")
    _print_result(f"PF={actual_pf}")
    _print_result(f"ZIP={actual_zip}")
    _print_result(f"GATE={final_gate}")
    return 0 if final_gate == "PASS" else 1


def cmd_certify_validate(args: argparse.Namespace) -> int:
    target_project_root = _resolve_project_root(getattr(args, "project", None))

    repo_root = DEVFABRIC_ROOT.parent.resolve()
    pf = _default_pf(repo_root, "certification_validate")
    contract_path_raw = str(getattr(args, "target_contract", "") or "").strip()
    contract_path = Path(contract_path_raw).resolve() if contract_path_raw else None
    require_contract = str(getattr(args, "require_contract", "on") or "on").lower() != "off"
    target_result = run_target_validation_precheck(
        project_root=target_project_root,
        pf=pf,
        explicit_contract_path=contract_path,
        require_contract=require_contract,
    )
    if target_result.state == "CERTIFICATION_NOT_READY":
        _register_bundle_safely(pf)
        _print_result(f"project_root={target_project_root}")
        _print_result(f"target_capability_state={target_result.state}")
        _print_result(f"PF={pf.resolve()}")
        _print_result("GATE=FAIL")
        return 1

    baseline_path = Path("")
    current_run_path = Path("")
    if not target_result.subtargets:
        baseline_path = _resolve_baseline_arg(
            target_project_root,
            str(getattr(args, "baseline", "") or ""),
            str(getattr(args, "compare", "") or ""),
            target_result.baseline_root,
        )
        current_run_path_raw = str(getattr(args, "current_run", "") or "").strip()
        current_run_path = Path(current_run_path_raw).resolve() if current_run_path_raw else target_project_root

    result = run_decision_validation(
        repo_root=DEVFABRIC_ROOT.parent.resolve(),
        baseline_path=baseline_path,
        current_path=current_run_path,
    )
    _print_result(f"baseline_path={baseline_path}")
    _print_result(f"current_run_path={current_run_path}")
    _print_result(f"validation_dir={result.get('validation_dir', '')}")
    _print_result(f"validation_zip={result.get('validation_zip', '')}")
    _print_result(f"validation_cases={len(result.get('cases', []))}")
    _print_result(f"validation_mismatches={len(result.get('mismatches', []))}")
    _print_result(f"GATE={result.get('gate', 'FAIL')}")
    return 0 if str(result.get("gate", "FAIL")).upper() == "PASS" else 1


def cmd_certify_gate(args: argparse.Namespace) -> int:
    target_project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "certification_gate")

    contract_path_raw = str(getattr(args, "target_contract", "") or "").strip()
    contract_path = Path(contract_path_raw).resolve() if contract_path_raw else None
    require_contract = str(getattr(args, "require_contract", "on") or "on").lower() != "off"
    target_result = run_target_validation_precheck(
        project_root=target_project_root,
        pf=pf,
        explicit_contract_path=contract_path,
        require_contract=require_contract,
    )

    if target_result.state == "CERTIFICATION_NOT_READY":
        _register_bundle_safely(pf)
        _print_result(f"project_root={target_project_root}")
        _print_result(f"target_capability_state={target_result.state}")
        _print_result(f"PF={pf.resolve()}")
        _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
        _print_result("GATE=FAIL")
        return 1

    baseline_path = _resolve_baseline_arg(
        target_project_root,
        str(getattr(args, "baseline", "") or ""),
        str(getattr(args, "compare", "") or ""),
        target_result.baseline_root,
    )
    current_run_path_raw = str(getattr(args, "current_run", "") or "").strip()
    current_run_path = Path(current_run_path_raw).resolve() if current_run_path_raw else target_project_root

    compare_policy = ComparisonPolicy(
        diagnostic_score_tolerance=float(getattr(args, "tolerance", 0.02) or 0.02),
        diagnostic_score_improvement_threshold=float(getattr(args, "improvement_threshold", 0.03) or 0.03),
        severe_core_drop_threshold=float(getattr(args, "severe_drop_threshold", 0.15) or 0.15),
    )
    strict_mode = str(getattr(args, "strict_mode", "on") or "on").lower() != "off"
    enforcement_policy = GateEnforcementPolicy(strict_mode=strict_mode)

    if target_result.subtargets:
        result = run_subtarget_rollup_gate(
            repo_root=repo_root,
            project_root=target_project_root,
            pf=pf,
            target_result=target_result,
            comparison_policy=compare_policy,
            enforcement_policy=enforcement_policy,
        )
    else:
        result = run_certification_gate(
            repo_root=repo_root,
            baseline_path=baseline_path,
            current_path=current_run_path,
            pf=pf,
            comparison_policy=compare_policy,
            enforcement_policy=enforcement_policy,
            supported_baseline_versions=target_result.supported_baseline_versions,
            profile_project_root=target_project_root,
        )

    _register_bundle_safely(Path(str(result.get("pf", pf))))
    if target_result.subtargets:
        _print_result("baseline_path=rollup_subtarget_mode")
        _print_result("current_run_path=rollup_subtarget_mode")
    else:
        _print_result(f"baseline_path={baseline_path}")
        _print_result(f"current_run_path={current_run_path}")
    _print_result(f"certification_decision={result.get('decision', '')}")
    _print_result(f"target_capability_state={target_result.state}")
    _print_result(f"compatibility_state={result.get('compatibility_state', '')}")
    _print_result(f"compare_gate={result.get('compare_gate', '')}")
    _print_result(f"enforced_gate={result.get('enforced_gate', '')}")
    _print_result(f"exit_code={result.get('exit_code', 1)}")
    _print_result(f"enforcement_reason={result.get('enforcement_reason', '')}")
    _print_result(f"recommended_next_action={result.get('recommended_next_action', '')}")
    _print_result(f"PF={result.get('pf', '')}")
    _print_result(f"ZIP={result.get('zip', '')}")
    _print_result(f"GATE={result.get('enforced_gate', 'FAIL')}")
    return int(result.get("exit_code", 1))


def cmd_predict_risk(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "predictive_risk")

    manifest_raw = str(getattr(args, "change_manifest", "") or "").strip()
    manifest_path = Path(manifest_raw).resolve() if manifest_raw else None
    trend_raw = str(getattr(args, "trend_root", "") or "").strip()
    trend_path = Path(trend_raw).resolve() if trend_raw else None

    direct_components = [
        str(component).strip()
        for component in list(getattr(args, "components", []) or [])
        if str(component).strip()
    ]

    result = analyze_premerge_regression_risk(
        project_root=project_root,
        pf=pf,
        change_manifest_path=manifest_path,
        touched_components=direct_components,
        trend_root=trend_path,
    )

    _register_bundle_safely(pf)
    prediction = result.get("prediction", {}) if isinstance(result.get("prediction", {}), dict) else {}
    _print_result(f"project_root={project_root}")
    _print_result(f"history_root={result.get('history_root', '')}")
    _print_result(f"trend_root={result.get('trend_root', '')}")
    _print_result(f"change_id={prediction.get('change_id', 'manual_input')}")
    _print_result(f"overall_regression_risk={prediction.get('overall_risk_score', 0.0)}")
    _print_result(f"overall_risk_class={prediction.get('overall_risk_class', 'LOW')}")
    _print_result(f"highest_risk_component={prediction.get('highest_risk_component', '')}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result("GATE=PASS")
    return 0


def cmd_plan_validation(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "validation_plan")

    manifest_raw = str(getattr(args, "change_manifest", "") or "").strip()
    manifest_path = Path(manifest_raw).resolve() if manifest_raw else None

    direct_components = [
        str(component).strip()
        for component in list(getattr(args, "components", []) or [])
        if str(component).strip()
    ]

    evidence_raw = str(getattr(args, "evidence_run", "") or "").strip()
    evidence_run = Path(evidence_raw).resolve() if evidence_raw else None

    result = plan_premerge_validation(
        project_root=project_root,
        pf=pf,
        change_manifest_path=manifest_path,
        touched_components=direct_components,
        evidence_run_root=evidence_run,
    )

    _register_bundle_safely(pf)
    plan = result.get("plan", {}) if isinstance(result.get("plan", {}), dict) else {}

    _print_result(f"project_root={project_root}")
    _print_result(f"plan_class={plan.get('plan_class', 'STANDARD')}")
    _print_result(f"aggregate_plan_score={plan.get('aggregate_plan_score', 0.0)}")
    _print_result(f"required_scenario_count={plan.get('required_scenario_count', 0)}")
    _print_result(f"optional_scenario_count={plan.get('optional_scenario_count', 0)}")
    _print_result(f"touched_components={','.join(plan.get('touched_components', []) or [])}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result("GATE=PASS")
    return 0


def cmd_run_validation_plan(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "validation_execution")

    manifest_raw = str(getattr(args, "change_manifest", "") or "").strip()
    manifest_path = Path(manifest_raw).resolve() if manifest_raw else None

    direct_components = [
        str(component).strip()
        for component in list(getattr(args, "components", []) or [])
        if str(component).strip()
    ]

    policy_raw = str(getattr(args, "execution_policy", "BALANCED") or "BALANCED").strip().upper()

    result = run_validation_orchestrator(
        project_root=project_root,
        pf=pf,
        execution_policy=policy_raw,
        change_manifest_path=manifest_path,
        touched_components=direct_components,
    )

    _register_bundle_safely(pf)
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}

    _print_result(f"project_root={project_root}")
    _print_result(f"execution_policy={summary.get('execution_policy', 'BALANCED')}")
    _print_result(f"plan_class={summary.get('plan_class', 'STANDARD')}")
    _print_result(f"completed_scenario_count={summary.get('completed_scenario_count', 0)}")
    _print_result(f"critical_regression_count={summary.get('critical_regression_count', 0)}")
    _print_result(f"early_stop_reason={summary.get('early_stop_reason', '')}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result("GATE=PASS")
    return 0


def cmd_run_validation_and_certify(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "validation_chain")

    manifest_raw = str(getattr(args, "change_manifest", "") or "").strip()
    manifest_path = Path(manifest_raw).resolve() if manifest_raw else None
    policy_raw = str(getattr(args, "execution_policy", "BALANCED") or "BALANCED").strip().upper()
    strict_chain = bool(getattr(args, "strict_chain", False))
    skip_rerun_if_no_execution = bool(getattr(args, "skip_rerun_if_no_execution", False))

    direct_components = [
        str(component).strip()
        for component in list(getattr(args, "components", []) or [])
        if str(component).strip()
    ]

    result = run_validation_and_certify_pipeline(
        project_root=project_root,
        repo_root=repo_root,
        pf=pf,
        execution_policy=policy_raw,
        change_manifest_path=manifest_path,
        touched_components=direct_components,
        skip_rerun_if_no_execution=skip_rerun_if_no_execution,
        strict_chain=strict_chain,
    )

    _register_bundle_safely(pf)
    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}

    _print_result(f"project_root={project_root}")
    _print_result(f"execution_policy={summary.get('execution_policy', policy_raw)}")
    _print_result(f"executed_scenario_count={summary.get('executed_scenario_count', 0)}")
    _print_result(f"early_stop_reason={summary.get('early_stop_reason', '')}")
    _print_result(f"rerun_decision={summary.get('rerun_decision', '')}")
    _print_result(f"certification_decision={summary.get('certification_decision', '')}")
    _print_result(f"final_combined_state={summary.get('final_combined_state', 'EXECUTION_CHAIN_INCONCLUSIVE')}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result(f"GATE={summary.get('chain_gate', 'FAIL')}")
    return 0 if str(summary.get("chain_gate", "FAIL")) == "PASS" else 1


def cmd_run_validation_plugins(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    repo_root = DEVFABRIC_ROOT.parent.resolve()

    if getattr(args, "pf", None):
        pf = _canonical_pf(repo_root, Path(str(args.pf)))
    else:
        pf = _default_pf(repo_root, "validation_plugins")

    result = evaluate_validation_policy(
        project_root=project_root,
        pf=pf,
        stage="build",
        profile="debug",
        target="build",
    )

    _register_bundle_safely(pf)
    _print_result(f"project_root={project_root}")
    _print_result(f"validation_plugin_status={result.get('gate_status', 'PASS')}")
    _print_result(f"validation_plugin_count={len(result.get('selected_plugins', []))}")
    _print_result(f"validation_plugin_fail_count={len(result.get('blocking_failures', []))}")
    _print_result(f"validation_plugin_warning_count={len(result.get('advisory_failures', []))}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"ZIP={pf.with_suffix('.zip').resolve()}")
    _print_result(f"GATE={result.get('gate_status', 'PASS')}")

    return 0 if str(result.get("gate_status", "PASS")).upper() == "PASS" else 1


def _has_delivery_payload_bundle(pf: Path) -> bool:
    hot = pf / "hotspots"
    required = [
        hot / "29_github_delivery_payload.json",
        hot / "30_jira_delivery_payload.json",
        hot / "31_email_delivery_payload.json",
        hot / "32_webhook_delivery_payload.json",
    ]
    return all(path.is_file() for path in required)


def _resolve_latest_delivery_pf(project_root: Path) -> Path | None:
    runs_root = (project_root / "_proof" / "runs").resolve()
    if not runs_root.is_dir():
        return None
    candidates = [path for path in runs_root.iterdir() if path.is_dir()]
    for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        if _has_delivery_payload_bundle(candidate):
            return candidate.resolve()
    return None


def cmd_deliver_connectors(args: argparse.Namespace) -> int:
    project_root = _resolve_project_root(getattr(args, "project", None))
    pf_raw = str(getattr(args, "pf", "") or "").strip()

    if pf_raw:
        pf = Path(pf_raw).resolve()
    else:
        discovered = _resolve_latest_delivery_pf(project_root)
        if discovered is None:
            raise ValueError("delivery_payloads_not_found: run certify first or provide --pf")
        pf = discovered

    if not _has_delivery_payload_bundle(pf):
        raise ValueError(f"delivery_payloads_missing_in_pf: {pf}")

    mode_raw = str(getattr(args, "mode", "") or "").strip().upper()
    mode_override = mode_raw if mode_raw in {"DRY_RUN", "LIVE"} else None

    result = run_connector_transport(
        project_root=project_root,
        pf=pf,
        mode_override=mode_override,
    )
    _register_bundle_safely(pf)

    summary = result.get("summary", {}) if isinstance(result.get("summary", {}), dict) else {}
    mode = str(summary.get("mode", "DRY_RUN"))
    total_requests = int(summary.get("total_request_count", 0) or 0)
    total_success = int(summary.get("total_success_count", 0) or 0)
    total_failure = int(summary.get("total_failure_count", 0) or 0)
    total_skipped = int(summary.get("total_skipped_count", 0) or 0)
    gate = "PASS" if total_failure == 0 else "FAIL"

    _print_result(f"project_root={project_root}")
    _print_result(f"transport_mode={mode}")
    _print_result(f"transport_total_requests={total_requests}")
    _print_result(f"transport_total_success={total_success}")
    _print_result(f"transport_total_failures={total_failure}")
    _print_result(f"transport_total_skipped={total_skipped}")
    _print_result(f"PF={pf.resolve()}")
    _print_result(f"GATE={gate}")
    return 0 if gate == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ngksdevfabric")
    sub = parser.add_subparsers(dest="cmd", required=True)

    probe_parser = sub.add_parser("probe")
    probe_parser.add_argument("project_path", nargs="?", default=".")
    probe_parser.add_argument("--pf", required=False)
    probe_parser.add_argument("--backup-root", required=False)
    probe_parser.set_defaults(func=cmd_probe)

    profile_parser = sub.add_parser("profile")
    profile_sub = profile_parser.add_subparsers(dest="profile_cmd", required=True)
    profile_init_parser = profile_sub.add_parser("init")
    profile_init_parser.add_argument("project_path", nargs="?", default=".")
    profile_init_parser.add_argument("--pf", required=False)
    profile_init_parser.add_argument("--backup-root", required=False)
    profile_init_parser.add_argument("--write-project", action="store_true")
    profile_init_parser.set_defaults(func=cmd_profile_init)

    build_parser_ = sub.add_parser("build")
    build_parser_.add_argument("project_path", nargs="?", default=".")
    build_parser_.add_argument("--pf", required=False)
    build_parser_.add_argument("--backup-root", required=False)
    build_parser_.add_argument("--mode", choices=["debug", "release", "debug_x64", "release_x64"], default="debug")
    build_parser_.add_argument("--profile", required=False)
    build_parser_.add_argument("--backend", choices=["auto", "buildcore"], default="auto")
    build_parser_.add_argument("--target", required=False)
    build_parser_.add_argument("-j", "--jobs", type=int, required=False)
    build_parser_.add_argument("--render-doc", action="store_true")
    build_parser_.add_argument("--doc-gate", action="store_true")
    build_parser_.set_defaults(func=cmd_build)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("project_path", nargs="?", default=".")
    doctor_parser.add_argument("--pf", required=False)
    doctor_parser.add_argument(
        "--backup-root",
        required=False,
        help="Backup root for mirrored proof output. If omitted, backup mirroring is disabled.",
    )
    doctor_parser.add_argument("--no-prompt", action="store_true", help="Do not prompt for backup-root fixes when an invalid backup root is provided.")
    doctor_parser.set_defaults(func=cmd_doctor)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--project", required=False, default=".")
    run_parser.add_argument("--profile", required=False)
    run_parser.add_argument("--target", required=False)
    run_parser.add_argument("--mode", choices=["ecosystem"], default="ecosystem")
    run_parser.set_defaults(func=cmd_run)

    ngks_parser = sub.add_parser("ngks")
    ngks_sub = ngks_parser.add_subparsers(dest="ngks_cmd", required=True)

    ngks_doctor = ngks_sub.add_parser("doctor")
    ngks_doctor.add_argument("--project", required=False, default=".")
    ngks_doctor.add_argument("--pf", required=False)
    ngks_doctor.set_defaults(func=cmd_ngks_doctor)

    ngks_plan = ngks_sub.add_parser("plan")
    ngks_plan.add_argument("--project", required=False, default=".")
    ngks_plan.add_argument("--pf", required=False)
    ngks_plan.set_defaults(func=cmd_ngks_plan)

    ngks_build = ngks_sub.add_parser("build")
    ngks_build.add_argument("--project", required=False, default=".")
    ngks_build.add_argument("--pf", required=False)
    ngks_build.add_argument("--mode", choices=["debug", "release", "debug_x64", "release_x64"], default="debug")
    ngks_build.add_argument("--profile", required=False, default="debug")
    ngks_build.add_argument("--target", required=False)
    ngks_build.add_argument("-j", "--jobs", type=int, required=False)
    ngks_build.set_defaults(func=cmd_ngks_build)

    ngks_test = ngks_sub.add_parser("test")
    ngks_test.add_argument("--project", required=False, default=".")
    ngks_test.add_argument("--pf", required=False)
    ngks_test.add_argument("--path", required=False, default="")
    ngks_test.set_defaults(func=cmd_ngks_test)

    ngks_ship = ngks_sub.add_parser("ship")
    ngks_ship.add_argument("--project", required=False, default=".")
    ngks_ship.set_defaults(func=cmd_ngks_ship)

    ngks_monitor = ngks_sub.add_parser("graph-monitor")
    ngks_monitor.add_argument("--project", required=False, default=".")
    ngks_monitor.add_argument("--pf", required=False)
    ngks_monitor.add_argument("--poll-seconds", type=float, default=2.0)
    ngks_monitor.add_argument("--max-cycles", type=int, default=0)
    ngks_monitor.set_defaults(func=cmd_ngks_graph_monitor)

    eco_parser = sub.add_parser("eco")
    eco_sub = eco_parser.add_subparsers(dest="eco_cmd", required=True)
    eco_doctor = eco_sub.add_parser("doctor")
    eco_doctor.set_defaults(func=cmd_eco_doctor)

    term_parser = sub.add_parser("term")
    term_sub = term_parser.add_subparsers(dest="term_cmd", required=True)
    term_run_parser = term_sub.add_parser("run")
    term_run_parser.add_argument("command")
    term_run_parser.add_argument("--project-path", required=False)
    term_run_parser.add_argument("--pf", required=False)
    term_run_parser.add_argument("--backup-root", required=False)
    term_run_parser.add_argument("--cwd", required=False)
    term_run_parser.add_argument("--smart-terminal", choices=["on", "off"], required=False)
    term_run_parser.set_defaults(func=cmd_term_run)

    render_doc_parser = sub.add_parser("render-doc")
    render_doc_parser.add_argument("--project-path", required=False)
    render_doc_parser.add_argument("--pf", required=False)
    render_doc_parser.add_argument("--backup-root", required=False)
    render_doc_parser.set_defaults(func=cmd_render_doc)

    doc_gate_parser = sub.add_parser("doc-gate")
    doc_gate_parser.add_argument("--project-path", required=False)
    doc_gate_parser.add_argument("--pf", required=False)
    doc_gate_parser.add_argument("--backup-root", required=False)
    doc_gate_parser.set_defaults(func=cmd_doc_gate)

    explain_parser = sub.add_parser("explain")
    explain_parser.add_argument("--project-path", required=False)
    explain_parser.add_argument("--pf", required=False)
    explain_parser.add_argument("--backup-root", required=False)
    explain_sub = explain_parser.add_subparsers(dest="explain_cmd", required=True)

    explain_file = explain_sub.add_parser("file")
    explain_file.add_argument("path")
    explain_file.set_defaults(func=cmd_explain)

    explain_rebuild = explain_sub.add_parser("rebuild")
    explain_rebuild.set_defaults(func=cmd_explain)

    explain_route = explain_sub.add_parser("route")
    explain_route.add_argument("route_id")
    explain_route.set_defaults(func=cmd_explain)

    explain_dependency = explain_sub.add_parser("dependency")
    explain_dependency.add_argument("component")
    explain_dependency.set_defaults(func=cmd_explain)

    certify_parser = sub.add_parser("certify")
    certify_parser.add_argument("--project", required=False, default=".")
    certify_parser.add_argument("--baseline", required=False, default="")
    certify_parser.add_argument("--compare", required=False, default="")
    certify_parser.add_argument("--current-run", required=False, default="")
    certify_parser.add_argument("--target-contract", required=False, default="")
    certify_parser.add_argument("--require-contract", choices=["on", "off"], default="on")
    certify_parser.add_argument("--pf", required=False)
    certify_parser.add_argument("--tolerance", type=float, default=0.02)
    certify_parser.add_argument("--improvement-threshold", type=float, default=0.03)
    certify_parser.add_argument("--severe-drop-threshold", type=float, default=0.15)
    certify_parser.set_defaults(func=cmd_certify)

    certify_validate_parser = sub.add_parser("certify-validate")
    certify_validate_parser.add_argument("--project", required=False, default=".")
    certify_validate_parser.add_argument("--baseline", required=False, default="")
    certify_validate_parser.add_argument("--compare", required=False, default="")
    certify_validate_parser.add_argument("--current-run", required=False, default="")
    certify_validate_parser.add_argument("--target-contract", required=False, default="")
    certify_validate_parser.add_argument("--require-contract", choices=["on", "off"], default="on")
    certify_validate_parser.set_defaults(func=cmd_certify_validate)

    certify_gate_parser = sub.add_parser("certify-gate")
    certify_gate_parser.add_argument("--project", required=False, default=".")
    certify_gate_parser.add_argument("--baseline", required=False, default="")
    certify_gate_parser.add_argument("--compare", required=False, default="")
    certify_gate_parser.add_argument("--current-run", required=False, default="")
    certify_gate_parser.add_argument("--target-contract", required=False, default="")
    certify_gate_parser.add_argument("--require-contract", choices=["on", "off"], default="on")
    certify_gate_parser.add_argument("--pf", required=False)
    certify_gate_parser.add_argument("--tolerance", type=float, default=0.02)
    certify_gate_parser.add_argument("--improvement-threshold", type=float, default=0.03)
    certify_gate_parser.add_argument("--severe-drop-threshold", type=float, default=0.15)
    certify_gate_parser.add_argument("--strict-mode", choices=["on", "off"], default="on")
    certify_gate_parser.set_defaults(func=cmd_certify_gate)

    certify_target_check_parser = sub.add_parser("certify-target-check")
    certify_target_check_parser.add_argument("--project", required=False, default=".")
    certify_target_check_parser.add_argument("--target-contract", required=False, default="")
    certify_target_check_parser.add_argument("--require-contract", choices=["on", "off"], default="on")
    certify_target_check_parser.add_argument("--pf", required=False)
    certify_target_check_parser.set_defaults(func=cmd_certify_target_check)

    predict_risk_parser = sub.add_parser("predict-risk")
    predict_risk_parser.add_argument("--project", required=False, default=".")
    predict_risk_parser.add_argument("--change-manifest", required=False, default="")
    predict_risk_parser.add_argument("--component", dest="components", action="append", default=[])
    predict_risk_parser.add_argument("--trend-root", required=False, default="")
    predict_risk_parser.add_argument("--pf", required=False)
    predict_risk_parser.set_defaults(func=cmd_predict_risk)

    plan_validation_parser = sub.add_parser("plan-validation")
    plan_validation_parser.add_argument("--project", required=False, default=".")
    plan_validation_parser.add_argument("--change-manifest", required=False, default="")
    plan_validation_parser.add_argument("--component", dest="components", action="append", default=[])
    plan_validation_parser.add_argument("--evidence-run", required=False, default="")
    plan_validation_parser.add_argument("--pf", required=False)
    plan_validation_parser.set_defaults(func=cmd_plan_validation)

    run_validation_plan_parser = sub.add_parser("run-validation-plan")
    run_validation_plan_parser.add_argument("--project", required=False, default=".")
    run_validation_plan_parser.add_argument("--change-manifest", required=False, default="")
    run_validation_plan_parser.add_argument("--execution-policy", choices=["STRICT", "BALANCED", "FAST"], default="BALANCED")
    run_validation_plan_parser.add_argument("--component", dest="components", action="append", default=[])
    run_validation_plan_parser.add_argument("--pf", required=False)
    run_validation_plan_parser.set_defaults(func=cmd_run_validation_plan)

    run_validation_and_certify_parser = sub.add_parser("run-validation-and-certify")
    run_validation_and_certify_parser.add_argument("--project", required=False, default=".")
    run_validation_and_certify_parser.add_argument("--change-manifest", required=False, default="")
    run_validation_and_certify_parser.add_argument("--execution-policy", choices=["STRICT", "BALANCED", "FAST"], default="BALANCED")
    run_validation_and_certify_parser.add_argument("--component", dest="components", action="append", default=[])
    run_validation_and_certify_parser.add_argument("--skip-rerun-if-no-execution", action="store_true")
    run_validation_and_certify_parser.add_argument("--strict-chain", action="store_true")
    run_validation_and_certify_parser.add_argument("--pf", required=False)
    run_validation_and_certify_parser.set_defaults(func=cmd_run_validation_and_certify)

    run_validation_plugins_parser = sub.add_parser("run-validation-plugins")
    run_validation_plugins_parser.add_argument("--project", required=False, default=".")
    run_validation_plugins_parser.add_argument("--view", required=False, default="runtime_default_view")
    run_validation_plugins_parser.add_argument("--layout-snapshot", required=False, default="")
    run_validation_plugins_parser.add_argument("--pf", required=False)
    run_validation_plugins_parser.set_defaults(func=cmd_run_validation_plugins)

    deliver_connectors_parser = sub.add_parser("deliver-connectors")
    deliver_connectors_parser.add_argument("--project", required=False, default=".")
    deliver_connectors_parser.add_argument("--pf", required=False, default="")
    deliver_connectors_parser.add_argument("--mode", choices=["DRY_RUN", "LIVE"], required=False)
    deliver_connectors_parser.set_defaults(func=cmd_deliver_connectors)

    return parser


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(argv) if argv is not None else list(sys.argv[1:])
    policy_code = _enforce_notebook_policy(effective_argv)
    if policy_code != 0:
        return policy_code

    if not _enforce_workspace_integrity(pf=None, scope="cli_startup"):
        return 2

    parser = build_parser()
    try:
        args = parser.parse_args(effective_argv)
        return int(args.func(args))
    except ValueError as exc:
        _print_result(f"error={exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())