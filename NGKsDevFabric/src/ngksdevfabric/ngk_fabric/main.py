from __future__ import annotations

import argparse
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
from .proof_contract import doc_gate, ensure_unified_pf, repo_state, run_docengine_render, write_component_report
from .probe import probe_project
from .profile import init_profile
from .runwrap import doctor_toolchain, run_build
from .smart_terminal import detect_shell, resolve_smart_terminal_enabled, run_shell, run_shell_direct

DEVFABRIC_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class StageResult:
    stage: str
    exit_code: int
    stdout: str
    stderr: str
    failure_class: str = "stage_failed"


def _print_result(message: str) -> None:
    print(message)


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
    proof_root = (project / "_proof").resolve()
    proof_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return proof_root / f"{prefix}_{stamp}"


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
        return Path(args.pf).resolve()
    return _default_pf(project_root, prefix)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_required_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise ValueError(f"expected_output_missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


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

    try:
        proc = subprocess.run(argv, cwd=str(project_root), check=False, capture_output=True, text=True)
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

    profile_path = Path(args.profile).resolve() if args.profile else None
    components = ["graph", "devfabric", "buildcore"] if args.backend == "buildcore" else ["devfabric"]

    ensure_unified_pf(
        pf=pf,
        intent=_build_intent(args),
        components=components,
        repo_root=DEVFABRIC_ROOT,
    )

    started_at = _iso_now()
    code = run_build(
        project,
        pf,
        mode=args.mode,
        profile_path=profile_path,
        backend=args.backend,
        target=args.target,
        jobs=args.jobs,
    )
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

    _print_result(f"build_run_dir={pf / 'run_build'}")
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
    _print_result(f"project_root={project}")
    _print_result(f"backup_root={backup_root if backup_root is not None else 'disabled'}")
    _print_result(f"proof_dir={pf}")
    _print_result(f"exit_code={code}")
    return int(code)


def cmd_doctor(args: argparse.Namespace) -> int:
    project = _resolve_project_root(args.project_path)
    _print_doc_notice(project)
    backup_root = _resolve_backup_root(args, project)
    pf = _resolve_pf(args, project, "doctor")
    code = doctor_toolchain(project, pf)
    if code == 0 and backup_root is not None:
        _mirror_docs_to_backup(project, backup_root, pf)
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
    run_dir = project_root / "_proof" / f"devfabric_run_{run_id}"

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
            failure_class=failure_class,
            failed_stage=failed_stage,
        )
        _print_result(f"run_id={run_id}")
        _print_result(f"proof_dir={run_dir}")
        _print_result(f"exit_code={int(exit_code)}")
        return int(exit_code)

    if not build_detected:
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

    node_package_json = _resolve_node_package_json(project_root, build_detect_reason)

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
    )

    _print_result(f"run_id={run_id}")
    _print_result(f"proof_dir={run_dir}")
    _print_result("exit_code=0")
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except ValueError as exc:
        _print_result(f"error={exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())