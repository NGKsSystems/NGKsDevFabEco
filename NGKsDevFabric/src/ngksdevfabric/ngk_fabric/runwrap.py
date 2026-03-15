from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .receipts import (
    clear_proof_context,
    hash_command,
    run_command_capture,
    set_proof_context,
    tool_version,
    utc_now_iso,
    write_json,
    write_text,
)
from .resolver import resolve_tools
from .proof_contract import reconcile_ledger, repo_state, write_component_report


def parse_sln_solution_configs(sln_path: str) -> list[tuple[str, str]]:
    path = Path(sln_path)
    if not path.exists() or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    start_marker = "GlobalSection(SolutionConfigurationPlatforms) = preSolution"
    end_marker = "EndGlobalSection"
    start_index = text.find(start_marker)
    if start_index < 0:
        return []
    end_index = text.find(end_marker, start_index)
    if end_index < 0:
        return []

    section = text[start_index:end_index]
    pattern = re.compile(r"^\s*([^=]+?)\s*=\s*.+$", re.MULTILINE)
    pairs: set[tuple[str, str]] = set()
    for match in pattern.finditer(section):
        left = match.group(1).strip()
        if "|" not in left:
            continue
        conf, plat = left.split("|", 1)
        conf = conf.strip()
        plat = plat.strip()
        if conf and plat:
            pairs.add((conf, plat))
    return sorted(pairs)


def _mode_to_request(mode: str) -> tuple[str, str, str]:
    lower = mode.lower()
    conf = "Release" if lower.startswith("release") else "Debug"
    if "anycpu" in lower or "any_cpu" in lower:
        plat = "Any CPU"
    elif "x64" in lower:
        plat = "x64"
    else:
        plat = "x64"
    return lower, conf, plat


def _resolve_sln_config(configs: list[tuple[str, str]], mode: str) -> tuple[str | None, str | None, dict[str, Any]]:
    mode_key, requested_conf, requested_plat = _mode_to_request(mode)
    requested = f"{requested_conf}|{requested_plat}"
    if not configs:
        return None, None, {
            "requested": requested,
            "resolved": None,
            "reason": "no SolutionConfigurationPlatforms found",
        }

    exact = next(
        (item for item in configs if item[0].lower() == requested_conf.lower() and item[1].lower() == requested_plat.lower()),
        None,
    )
    if exact:
        return exact[0], exact[1], {"requested": requested, "resolved": f"{exact[0]}|{exact[1]}", "reason": "exact match"}

    mode_match = next((item for item in configs if item[0].lower() == requested_conf.lower()), None)
    if mode_match:
        return mode_match[0], mode_match[1], {
            "requested": requested,
            "resolved": f"{mode_match[0]}|{mode_match[1]}",
            "reason": "requested platform not found in SolutionConfigurationPlatforms",
        }

    first = configs[0]
    return first[0], first[1], {
        "requested": requested,
        "resolved": f"{first[0]}|{first[1]}",
        "reason": f"requested mode '{mode_key}' not found; selected first available tuple",
    }


def _quote_if_needed(value: str) -> str:
    stripped = value.strip()
    if " " in stripped and not (stripped.startswith('"') and stripped.endswith('"')):
        return f'"{stripped}"'
    return stripped


def _normalize_solution_build_log(build_cmd: list[str]) -> list[str]:
    normalized: list[str] = []
    for index, part in enumerate(build_cmd):
        if index == 2:
            normalized.append(_quote_if_needed(part))
            continue
        if part.startswith("-p:Platform="):
            value = part.split("=", 1)[1]
            normalized.append(f"-p:Platform={_quote_if_needed(value)}")
            continue
        normalized.append(part)
    return normalized


def _classify_failure(stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    combined = ""
    if stdout_path.exists():
        combined += stdout_path.read_text(encoding="utf-8", errors="replace") + "\n"
    if stderr_path.exists():
        combined += stderr_path.read_text(encoding="utf-8", errors="replace")

    patterns = [
        ("MSB4126", "CONFIGURATION_ERROR"),
        ("NU", "NUGET_ERROR"),
        ("CS", "COMPILER_ERROR"),
        ("LNK", "LINKER_ERROR"),
    ]
    for token, category in patterns:
        if token == "NU":
            if re.search(r"\bNU\d{4}\b", combined):
                return {"classification": category, "matched": "NUxxxx"}
            continue
        if token == "CS":
            if re.search(r"\bCS\d{4}\b", combined):
                return {"classification": category, "matched": "CSxxxx"}
            continue
        if token == "LNK":
            if re.search(r"\bLNK\d{4}\b", combined):
                return {"classification": category, "matched": "LNKxxxx"}
            continue
        if token in combined:
            return {"classification": category, "matched": token}
    return {"classification": "UNKNOWN_ERROR", "matched": None}


def _sln_fingerprint_files(solution_path: Path) -> list[Path]:
    files: list[Path] = []
    root = solution_path.parent
    if solution_path.exists():
        files.append(solution_path)
    files.extend(sorted(root.glob("**/*.csproj")))
    for name in ["global.json", "Directory.Build.props", "Directory.Build.targets"]:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            files.append(candidate)

    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path.resolve()).lower()] = path.resolve()
    return sorted(unique.values(), key=lambda p: str(p).lower())


def _collect_dotnet_fingerprint_files(project_path: Path, selected_csproj: Path | None) -> list[Path]:
    files: list[Path] = []
    if selected_csproj and selected_csproj.exists():
        files.append(selected_csproj.resolve())

    for name in ["Directory.Build.props", "Directory.Build.targets", "global.json", "NuGet.Config"]:
        candidate = project_path / name
        if candidate.exists() and candidate.is_file():
            files.append(candidate.resolve())

    root_depth = len(project_path.parts)
    for dirpath, _, filenames in project_path.walk(top_down=True):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        if depth > 6:
            continue
        for filename in filenames:
            lower = filename.lower()
            if lower.endswith(".props") or lower.endswith(".targets"):
                files.append((current / filename).resolve())

    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path).lower()] = path
    return sorted(unique.values(), key=lambda p: str(p).lower())


def _collect_strategy_fingerprint_files(
    backend: str,
    project_path: Path,
    selected_solution_path: Path | None,
    selected_csproj: Path | None,
) -> list[Path]:
    if backend == "sln" and selected_solution_path is not None:
        return _sln_fingerprint_files(selected_solution_path)
    if backend == "csproj":
        return _collect_dotnet_fingerprint_files(project_path, selected_csproj)
    return []


def _compute_fingerprint(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file_path in files:
        digest.update(str(file_path).encode("utf-8"))
        digest.update(b"\n")
        digest.update(file_path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def _load_profile(project_path: Path, profile_path: Path | None, pf: Path) -> tuple[dict[str, Any], Path]:
    """
    Profile load contract (NO implicit writes/reads in target project):
      1) If --profile provided -> load that file.
      2) Else load PF/profile.json.
      3) Else fail (no fallback to project_path/.ngk/profile.json).
    """
    project_path = project_path.resolve()
    pf = pf.resolve()

    if profile_path:
        path = profile_path.resolve()
    else:
        path = (pf / "profile.json").resolve()

    if not path.exists() or not path.is_file():
        default_profile: dict[str, Any] = {
            "profile_name": "default",
            "build_type": "debug",
            "compiler": "auto",
            "capabilities": [],
            "generated_by": "DevFabEco",
            "version": 1,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_profile, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid profile JSON at {path}: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ValueError(f"Profile JSON is empty/invalid at {path}")

    return data, path


def _detect_backend(project_path: Path, profile: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    sln_candidates = profile.get("solution", {}).get("solution_candidates", []) if isinstance(profile, dict) else []
    if not sln_candidates:
        sln_candidates = [p.name for p in project_path.glob("*.sln")]
    csproj_candidates = [p.name for p in project_path.glob("*.csproj")]

    details = {
        "sln_candidates": sln_candidates,
        "csproj_candidates": csproj_candidates,
        "priority_order": ["sln", "csproj", "unknown"],
    }

    if sln_candidates:
        return "sln", details
    if csproj_candidates:
        return "csproj", details
    return "unknown", details


def _select_path(profile: dict[str, Any], project_path: Path) -> tuple[str, str, dict[str, Any]]:
    backend, backend_details = _detect_backend(project_path, profile)
    detected = profile.get("detected", {}) if isinstance(profile, dict) else {}
    details = {
        "profile_primary": str(detected.get("primary_path", "unknown")),
        "backend_details": backend_details,
    }
    return "graph", backend, details


def _bootstrap_command(bootstrap: str) -> list[str]:
    normalized = bootstrap.strip()
    if not normalized:
        return []
    lower = normalized.lower()
    if lower.endswith(".cmd"):
        return ["cmd.exe", "/c", normalized]
    if lower.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", normalized]
    return ["powershell", "-NoProfile", "-Command", normalized]


def _run_graph_cli_if_available(project_path: Path, run_dir: Path, graph_plan_path: Path) -> tuple[str, int | None]:
    graph_cli = os.environ.get("NGKSGRAPH_CLI", "").strip()
    if not graph_cli:
        return "graph unavailable", None
    graph_cli_path = Path(graph_cli)
    if not graph_cli_path.exists() or not graph_cli_path.is_file():
        return "graph unavailable", None

    command = [str(graph_cli_path), str(graph_plan_path)]
    write_text(run_dir / "graph_call.txt", " ".join(shlex.quote(part) for part in command) + "\n")
    code = run_command_capture(command, project_path, run_dir / "graph_stdout.txt", run_dir / "graph_stderr.txt")
    return "graph cli invoked", code


def generate_build_plan(
    run_dir: Path,
    project_path: Path,
    bootstrap_cmd: list[str],
    configure_cmd: list[str],
    build_cmd: list[str],
    backend: str,
) -> tuple[str, Path]:
    if not build_cmd:
        raise RuntimeError("BuildPlan generation failed: build command is empty.")

    plan_payload = {
        "strategy": "graph",
        "backend": backend,
        "project_path": str(project_path),
        "steps": [
            {"name": "bootstrap", "command": bootstrap_cmd},
            {"name": "configure", "command": configure_cmd},
            {"name": "build", "command": build_cmd},
        ],
    }
    encoded = json.dumps(plan_payload, sort_keys=True).encode("utf-8")
    plan_id = hashlib.sha256(encoded).hexdigest()[:16]
    plan_payload["plan_id"] = plan_id
    plan_path = run_dir / "graph_plan.json"
    write_json(plan_path, plan_payload)
    write_text(run_dir / "graph_plan_id.txt", plan_id + "\n")
    return plan_id, plan_path


def _mode_to_graph_profile(mode: str) -> str:
    return "release" if mode.lower().startswith("release") else "debug"


def _append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _resolve_graph_invocation(project_path: Path, pf: Path) -> tuple[list[str] | None, Path | None, dict[str, Any]]:
    sibling_graph = (project_path.parent / "NGKsGraph").resolve()
    graph_exe = os.environ.get("NGKS_GRAPH_EXE", "").strip()
    details: dict[str, Any] = {
        "source": "env" if graph_exe else "default",
        "raw": graph_exe,
        "mode": "",
        "cwd": "",
        "argv": [],
    }

    graph_cwd = sibling_graph if sibling_graph.exists() else project_path.resolve()

    if graph_exe:
        normalized = graph_exe.strip()
        if normalized.lower() == "python -m ngksgraph":
            argv = [sys.executable, "-m", "ngksgraph"]
            details["mode"] = "exact_python_module"
        elif " " in normalized:
            argv = ["cmd.exe", "/d", "/s", "/c", normalized]
            details["mode"] = "cmd_wrapper"
        else:
            argv = [normalized]
            details["mode"] = "single_executable"
    else:
        argv = [sys.executable, "-m", "ngksgraph"]
        details["mode"] = "default_python_module"

    details["cwd"] = str(graph_cwd)
    details["argv"] = list(argv)
    _append_text(pf / "commands.txt", "GRAPH_RESOLVE " + json.dumps(details, ensure_ascii=True) + "\n")
    return argv, graph_cwd, details


def _resolve_graph_project(project_path: Path, pf: Path) -> tuple[Path | None, dict[str, Any]]:
    configured = os.environ.get("NGKS_GRAPH_PROJECT", "").strip()
    candidate_project = project_path.resolve()
    sibling_graph = (project_path.parent / "NGKsGraph").resolve()
    candidate_sample = (sibling_graph / "artifacts" / "phaseA_sample").resolve()
    candidate_repo = sibling_graph
    details: dict[str, Any] = {
        "source": "env" if configured else "default",
        "configured": configured,
        "candidates": [str(candidate_project), str(candidate_sample), str(candidate_repo)],
        "selected": None,
    }

    if configured:
        selected = Path(configured).resolve()
        if selected.exists():
            details["selected"] = str(selected)
            return selected, details
        details["error"] = "NGKS_GRAPH_PROJECT set but path not found"
        return None, details

    if (candidate_project / "ngksgraph.toml").exists():
        details["selected"] = str(candidate_project)
        return candidate_project, details

    if (candidate_sample / "ngksgraph.toml").exists():
        details["selected"] = str(candidate_sample)
        return candidate_sample, details
    if candidate_repo.exists() and (candidate_repo / "ngksgraph.toml").exists():
        details["selected"] = str(candidate_repo)
        return candidate_repo, details

    details["error"] = "No default NGKS_GRAPH_PROJECT path found"
    return None, details


def _resolve_buildcore_command(project_path: Path, pf: Path) -> tuple[list[str] | None, Path | None, dict[str, Any]]:
    configured = os.environ.get("NGKS_BUILDCORE_PY", "").strip()
    sibling_root = (project_path.parent / "NGKsBuildCore").resolve()
    sibling_python = sibling_root / ".venv" / "Scripts" / "python.exe"
    details: dict[str, Any] = {
        "source": "env" if configured else "default",
        "configured": configured,
        "selected": None,
        "cwd": None,
        "command": None,
    }

    if configured:
        configured_path = Path(configured).resolve()
        cwd = sibling_root if (sibling_root / "ngksbuildcore").exists() else project_path.resolve()
        command = [str(configured_path), "-m", "ngksbuildcore"]
        details["selected"] = str(configured_path)
        details["cwd"] = str(cwd)
        details["command"] = command
        return command, cwd, details

    probe = subprocess.run(
        [sys.executable, "-m", "ngksbuildcore", "--help"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if probe.returncode == 0:
        command = [sys.executable, "-m", "ngksbuildcore"]
        details["selected"] = "python -m ngksbuildcore"
        details["cwd"] = str(project_path.resolve())
        details["command"] = command
        return command, project_path.resolve(), details

    if sibling_python.exists() and sibling_python.is_file():
        command = [str(sibling_python), "-m", "ngksbuildcore"]
        details["selected"] = str(sibling_python)
        details["cwd"] = str(sibling_root)
        details["command"] = command
        return command, sibling_root, details

    details["error"] = "Cannot resolve BuildCore entrypoint"
    _append_text(pf / "commands.txt", "BUILDCORE_RESOLVE_FAIL\n")
    return None, None, details


def _resolve_jobs(jobs: int | None) -> tuple[int, dict[str, Any]]:
    env_jobs = os.environ.get("NGKS_BUILD_JOBS", "").strip()
    if jobs is not None and jobs > 0:
        return jobs, {"source": "arg", "value": jobs}
    if env_jobs.isdigit() and int(env_jobs) > 0:
        return max(1, int(env_jobs)), {"source": "env", "value": max(1, int(env_jobs))}
    cpu = os.cpu_count() or 1
    value = max(1, min(16, int(cpu)))
    return value, {"source": "cpu_count", "cpu_count": cpu, "value": value}


def _write_blocker(pf: Path, message: str) -> int:
    write_text(pf / "BLOCKER.txt", message.strip() + "\n")
    return 2


def _safe_version(command: list[str]) -> str:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return text.splitlines()[0] if text else ""
    except Exception as exc:
        return f"error: {exc}"


def _ensure_buildcore_venv(project_path: Path) -> tuple[bool, Path | None, str]:
    buildcore_root = (project_path.parent / "NGKsBuildCore").resolve()
    if not buildcore_root.exists() or not (buildcore_root / "ngksbuildcore").exists():
        return False, None, "buildcore_repo_not_found"

    venv_dir = buildcore_root / ".venv"
    py_exe = venv_dir / "Scripts" / "python.exe"
    if py_exe.exists():
        return True, py_exe, "existing"

    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        cwd=str(buildcore_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0 and py_exe.exists():
        return True, py_exe, "created"
    return False, py_exe if py_exe.exists() else None, "create_failed"


def _probe_cl_via_vsdevcmd(vsdevcmd_path: str) -> dict[str, object]:
    """
    Probe cl.exe in a command-agnostic way by spawning cmd.exe, invoking VsDevCmd.bat,
    then running `where cl`. Returns transcript fields for auditability.
    """
    import os
    import subprocess
    import tempfile

    fd, probe_cmd_path = tempfile.mkstemp(prefix="ngks_probe_cl_", suffix=".cmd")
    os.close(fd)
    script = [
        "@echo off",
        f'call "{vsdevcmd_path}" -arch=x64 >nul',
        "where cl",
    ]
    Path(probe_cmd_path).write_text("\r\n".join(script) + "\r\n", encoding="utf-8")

    cmd = ["cmd.exe", "/d", "/c", probe_cmd_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    stdout = (p.stdout or "").strip()
    stderr = (p.stderr or "").strip()

    cl_path = ""
    if p.returncode == 0 and stdout:
        first = stdout.splitlines()[0].strip()
        cl_path = first

    try:
        Path(probe_cmd_path).unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "cl_path": cl_path,
        "cl_probe_cmd": " ".join(cmd),
        "cl_probe_stdout": stdout,
        "cl_probe_stderr": stderr,
        "cl_probe_exit_code": int(p.returncode),
    }


def doctor_toolchain(project_path: Path, pf: Path) -> int:
    """
    Writes a FULL toolchain_report.json (toolchain snapshot + doctor summary).
    Returns exit code:
      0 = OK
      2 = required missing
    """
    import json
    import os
    import platform
    import shutil
    import subprocess

    project_path = Path(project_path).resolve()
    pf = Path(pf).resolve()
    pf.mkdir(parents=True, exist_ok=True)

    def _which(exe: str) -> str:
        p = shutil.which(exe)
        return str(Path(p).resolve()) if p else ""

    def _run(cmd: list[str]) -> str:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
            out = (r.stdout or "").strip()
            return out
        except Exception:
            return ""

    def _read_first_line(path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
        except Exception:
            return ""

    # --- snapshot ---
    python_path = str(Path(sys.executable).resolve())
    python_version = platform.python_version()
    git_path = _which("git")
    git_version = _run([git_path, "--version"]) if git_path else ""

    vswhere_path = _which("vswhere")
    if not vswhere_path:
        # common fallback path
        candidate = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
        vswhere_path = str(candidate) if candidate.exists() else ""

    vs_installation = ""
    vsdevcmd_path = ""
    cl_path = ""
    cl_probe_cmd = ""
    cl_probe_stdout = ""
    cl_probe_stderr = ""
    cl_probe_exit_code = -1
    windows_sdk = ""

    if vswhere_path:
        # installation path
        vs_installation = _run(
            [
                vswhere_path,
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ]
        ).strip()

        if vs_installation:
            candidate = Path(vs_installation) / "Common7" / "Tools" / "VsDevCmd.bat"
            vsdevcmd_path = str(candidate) if candidate.exists() else ""

        if vsdevcmd_path:
            probe = _probe_cl_via_vsdevcmd(vsdevcmd_path)
            cl_path = str(probe.get("cl_path", "")).strip()
            cl_probe_cmd = str(probe.get("cl_probe_cmd", "")).strip()
            cl_probe_stdout = str(probe.get("cl_probe_stdout", "")).strip()
            cl_probe_stderr = str(probe.get("cl_probe_stderr", "")).strip()
            cl_probe_exit_code = int(probe.get("cl_probe_exit_code", -1))

        # cl.exe might not be in PATH unless devcmd was run; keep _which("cl") result if present
        # windows sdk root (best-effort)
        kit = Path(r"C:\Program Files (x86)\Windows Kits\10")
        windows_sdk = str(kit) + "\\" if kit.exists() else ""

    cpu_count = os.cpu_count() or 0

    # graph/buildcore entrypoints are project-policy; keep safe defaults
    graph_entrypoint = f"{python_path} -m ngksgraph (cwd={project_path})"
    buildcore_entrypoint = ""
    buildcore_venv_state = ""
    buildcore_venv_python = ""

    # If you already have buildcore detection helpers elsewhere in runwrap.py, keep using them.
    # Otherwise, leave these as best-effort empty states.
    # (If your file already defines buildcore detection variables, you can wire them in here.)

    report: dict[str, object] = {
        "python_path": python_path,
        "python_version": f"Python {python_version}",
        "git_version": git_version,
        "vswhere_path": vswhere_path,
        "vs_installation": vs_installation,
        "vsdevcmd_path": vsdevcmd_path,
        "cl_path": cl_path,
        "cl_probe_cmd": cl_probe_cmd,
        "cl_probe_stdout": cl_probe_stdout,
        "cl_probe_stderr": cl_probe_stderr,
        "cl_probe_exit_code": cl_probe_exit_code,
        "windows_sdk": windows_sdk,
        "graph_entrypoint": graph_entrypoint,
        "buildcore_entrypoint": buildcore_entrypoint,
        "cpu_count": cpu_count,
        "buildcore_venv_state": buildcore_venv_state,
        "buildcore_venv_python": buildcore_venv_python,
        "doctor_warnings": {},
    }

    # --- required checks ---
    required_keys = [
        "python_path",
        "python_version",
        "git_version",
        "vswhere_path",
        "vs_installation",
        "vsdevcmd_path",
        "windows_sdk",
        "graph_entrypoint",
        "cpu_count",
    ]

    missing: list[str] = []
    for k in required_keys:
        v = report.get(k, "")
        if v is None:
            missing.append(k)
            continue
        if isinstance(v, int):
            if v <= 0:
                missing.append(k)
            continue
        if str(v).strip() == "":
            missing.append(k)

    if not cl_path:
        missing.append("cl_path")

    report["doctor_required_missing"] = missing
    report["doctor_exit_code"] = 2 if missing else 0

    (pf / "toolchain_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return int(report["doctor_exit_code"])

def resolve_msvc_env(proof_dir: Path) -> dict[str, str] | None:
    require_direct = os.environ.get("NGKS_REQUIRE_DIRECT_MSVC_CAPTURE", "").strip() == "1"
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    log_lines = [
        f"vswhere={vswhere}",
        f"require_direct={int(require_direct)}",
    ]

    if not vswhere.exists():
        log_lines.extend(["direct_capture=NO", "fallback_used=NO", "status=vswhere_missing"])
        write_text(proof_dir / "msvc_bootstrap.txt", "\n".join(log_lines) + "\n")
        write_text(proof_dir / "msvc_env_delta.txt", "status=NO_Msvc_ENV\n")
        write_text(proof_dir / "where_cl.txt", "rc=1\nstdout:\n\nstderr:\nvswhere missing\n")
        return None

    query_cmd = [
        str(vswhere),
        "-latest",
        "-products",
        "*",
        "-requires",
        "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
        "-property",
        "installationPath",
    ]
    query = subprocess.run(query_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    install_path = (query.stdout or "").strip().splitlines()
    install_root = Path(install_path[-1].strip()) if install_path else None
    log_lines.append("vswhere_cmd=" + " ".join(query_cmd))
    log_lines.append(f"vswhere_rc={query.returncode}")
    log_lines.append(f"installationPath={install_root if install_root else ''}")
    if query.returncode != 0 or install_root is None or not install_root.exists():
        log_lines.extend(["direct_capture=NO", "fallback_used=NO", "status=vs_install_not_found"])
        write_text(proof_dir / "msvc_bootstrap.txt", "\n".join(log_lines) + "\n")
        write_text(proof_dir / "msvc_env_delta.txt", "status=NO_Msvc_ENV\n")
        write_text(proof_dir / "where_cl.txt", "rc=1\nstdout:\n\nstderr:\ninstallationPath missing\n")
        return None

    vsdevcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
    log_lines.append(f"vsdevcmd={vsdevcmd}")
    if not vsdevcmd.exists():
        log_lines.extend(["direct_capture=NO", "fallback_used=NO", "status=vsdevcmd_missing"])
        write_text(proof_dir / "msvc_bootstrap.txt", "\n".join(log_lines) + "\n")
        write_text(proof_dir / "msvc_env_delta.txt", "status=NO_Msvc_ENV\n")
        write_text(proof_dir / "where_cl.txt", "rc=1\nstdout:\n\nstderr:\nVsDevCmd missing\n")
        return None

    capture_cmd_file = proof_dir / "msvc_capture_env.cmd"
    capture_script_lines = [
        "@echo off",
        "setlocal enableextensions",
        f"call \"{vsdevcmd}\" -arch=x64 -host_arch=x64",
        "if errorlevel 1 exit /b 111",
        "where cl",
        "if errorlevel 1 exit /b 112",
        "set",
    ]
    with capture_cmd_file.open("w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("\r\n".join(capture_script_lines) + "\r\n")

    cmd_invocation = f'cmd.exe /d /s /c "{capture_cmd_file}"'
    log_lines.append(f"cmd_invocation={cmd_invocation}")

    capture = subprocess.run(
        ["cmd.exe", "/d", "/s", "/c", str(capture_cmd_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    write_text(proof_dir / "msvc_capture_stdout.txt", capture.stdout or "")
    log_lines.append(f"return_code={capture.returncode}")

    if capture.returncode != 0:
        where_lines = [line for line in (capture.stdout or "").splitlines() if "cl.exe" in line.lower() or "could not find" in line.lower()]
        write_text(proof_dir / "where_cl.txt", "\n".join(where_lines) + ("\n" if where_lines else ""))
        log_lines.extend(["direct_capture=NO", "fallback_used=NO", "status=direct_capture_failed"])
        write_text(proof_dir / "msvc_bootstrap.txt", "\n".join(log_lines) + "\n")
        write_text(proof_dir / "msvc_env_delta.txt", "status=NO_Msvc_ENV\n")
        return None

    resolved: dict[str, str] = {}
    where_lines: list[str] = []
    for raw_line in (capture.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().endswith("cl.exe") or "could not find" in line.lower():
            where_lines.append(line)
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        resolved[key] = value

    write_text(proof_dir / "where_cl.txt", "\n".join(where_lines) + ("\n" if where_lines else ""))

    interesting = ["PATH", "INCLUDE", "LIB", "LIBPATH", "VCINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir"]
    delta_lines = []
    for key in interesting:
        before = os.environ.get(key, "")
        after = resolved.get(key, "")
        delta_lines.append(f"[{key}]\nBEFORE={before}\nAFTER={after}\n")

    log_lines.extend(["direct_capture=YES", "fallback_used=NO", "status=direct_capture_ok"])
    write_text(proof_dir / "msvc_bootstrap.txt", "\n".join(log_lines) + "\n")
    write_text(proof_dir / "msvc_env_delta.txt", "\n".join(delta_lines) + "\n")
    return resolved


def _node_command_text(node: dict[str, Any]) -> str:
    cmd = node.get("cmd")
    if isinstance(cmd, str):
        return cmd
    if isinstance(cmd, list):
        return " ".join(str(x) for x in cmd)
    return ""


def _plan_requires_msvc(nodes: list[dict[str, Any]]) -> bool:
    tokens = ("cl ", "cl.exe", " link ", "link.exe", " lib ", "lib.exe")
    for node in nodes:
        text = _node_command_text(node).lower()
        if any(token in f" {text} " for token in tokens):
            return True
    return False


def _validate_plan_payload(payload: dict[str, Any]) -> tuple[bool, str, list[dict[str, Any]]]:
    errors: list[str] = []
    if "version" not in payload:
        errors.append("missing top-level version")
    nodes_obj = payload.get("nodes")
    if not isinstance(nodes_obj, list):
        errors.append("nodes must be a list")
        return False, "\n".join(errors), []

    seen_ids: set[str] = set()
    node_list: list[dict[str, Any]] = []
    for idx, node in enumerate(nodes_obj):
        if not isinstance(node, dict):
            errors.append(f"node[{idx}] must be object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"node[{idx}] invalid id")
        elif node_id in seen_ids:
            errors.append(f"duplicate node id: {node_id}")
        else:
            seen_ids.add(node_id)

        cmd = node.get("cmd")
        if isinstance(cmd, str):
            if not cmd.strip():
                errors.append(f"node[{idx}] cmd string empty")
        elif isinstance(cmd, list):
            if len(cmd) == 0 or any((not isinstance(x, str) or not x.strip()) for x in cmd):
                errors.append(f"node[{idx}] cmd list invalid")
        else:
            errors.append(f"node[{idx}] cmd must be str or list[str]")

        deps = node.get("deps", [])
        if deps is not None and not (isinstance(deps, list) and all(isinstance(x, str) for x in deps)):
            errors.append(f"node[{idx}] deps must be list[str]")
        outputs = node.get("outputs", [])
        if outputs is not None and not (isinstance(outputs, list) and all(isinstance(x, str) for x in outputs)):
            errors.append(f"node[{idx}] outputs must be list[str]")

        node_list.append(node)

    for node in node_list:
        node_id = str(node.get("id", ""))
        for dep in node.get("deps", []) or []:
            if dep not in seen_ids:
                errors.append(f"node '{node_id}' depends on missing id '{dep}'")

    return len(errors) == 0, "\n".join(errors), node_list


def _precreate_output_dirs(nodes: list[dict[str, Any]], graph_project_path: Path) -> list[str]:
    created_dirs: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for out in node.get("outputs", []) or []:
            out_path = Path(str(out))
            if not out_path.is_absolute():
                out_path = (graph_project_path / out_path).resolve()
            parent = out_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            created_dirs.add(str(parent))
    return sorted(created_dirs)


def _resolve_windeployqt_exe(graph_env: dict[str, str]) -> str:
    configured = str(graph_env.get("NGKS_WINDEPLOYQT_EXE", "") or "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            return str(candidate.resolve())
    detected = shutil.which("windeployqt.exe", path=graph_env.get("PATH"))
    if detected:
        return str(Path(detected).resolve())
    return ""


def _inject_qt_deploy_fallback_nodes(
    payload: dict[str, Any],
    *,
    graph_project_path: Path,
    graph_env: dict[str, str],
) -> int:
    nodes_obj = payload.get("nodes")
    if not isinstance(nodes_obj, list):
        return 0

    nodes = [node for node in nodes_obj if isinstance(node, dict)]
    if not nodes:
        return 0

    has_deploy = any(
        str(node.get("id", "")).startswith("windeployqt:")
        or "deploy qt runtime" in str(node.get("desc", "")).lower()
        or "windeployqt" in _node_command_text(node).lower()
        for node in nodes
    )
    if has_deploy:
        return 0

    windeployqt_exe = _resolve_windeployqt_exe(graph_env)
    if not windeployqt_exe:
        return 0

    existing_ids = {str(node.get("id", "")) for node in nodes}
    additions: list[dict[str, Any]] = []
    for node in nodes:
        cmd_text = _node_command_text(node).lower()
        if "qt6" not in cmd_text and "qt5" not in cmd_text:
            continue
        outputs = node.get("outputs", []) or []
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            out_value = str(output).strip()
            if not out_value or not out_value.lower().endswith(".exe"):
                continue
            stem = Path(out_value).stem or "app"
            deploy_id_base = f"windeployqt:{stem}:deploy:fallback"
            deploy_id = deploy_id_base
            suffix = 1
            while deploy_id in existing_ids:
                suffix += 1
                deploy_id = f"{deploy_id_base}:{suffix}"
            existing_ids.add(deploy_id)
            dep_id = str(node.get("id", "")).strip()
            additions.append(
                {
                    "id": deploy_id,
                    "desc": f"Deploy Qt runtime for {stem}",
                    "cwd": str(graph_project_path.resolve()),
                    "cmd": f'{_quote_if_needed(windeployqt_exe)} {_quote_if_needed(out_value)}',
                    "deps": [dep_id] if dep_id else [],
                    "inputs": [out_value],
                    "outputs": [],
                    "env": {},
                }
            )

    if not additions:
        return 0

    nodes_obj.extend(additions)
    return len(additions)


def _run_buildcore_backend(project_path: Path, pf: Path, mode: str, target: str | None, jobs: int | None) -> int:
    pf.mkdir(parents=True, exist_ok=True)
    run_dir = pf / "run_buildcore"
    run_dir.mkdir(parents=True, exist_ok=True)

    graph_cmd, graph_cwd, graph_resolution = _resolve_graph_invocation(project_path, pf)
    buildcore_cmd_base, buildcore_cwd, buildcore_resolution = _resolve_buildcore_command(project_path, pf)
    graph_project_path, graph_project_resolution = _resolve_graph_project(project_path, pf)
    build_jobs, jobs_resolution = _resolve_jobs(jobs)

    if graph_cmd is None or graph_cwd is None:
        return _write_blocker(pf, "Missing Graph invocation. Set NGKS_GRAPH_EXE or ensure sibling NGKsGraph exists.")
    if buildcore_cmd_base is None or buildcore_cwd is None:
        return _write_blocker(pf, "Missing BuildCore python. Set NGKS_BUILDCORE_PY or ensure sibling NGKsBuildCore/.venv/Scripts/python.exe exists.")
    if graph_project_path is None:
        return _write_blocker(pf, "Cannot resolve Graph project path. Checked sibling NGKsGraph defaults and NGKS_GRAPH_PROJECT.")

    env_resolution = {
        "graph": graph_resolution,
        "graph_project": graph_project_resolution,
        "buildcore": buildcore_resolution,
        "jobs": jobs_resolution,
    }
    write_json(pf / "env_resolution.json", env_resolution)

    graph_plan_dir = run_dir / "graph_plan"
    graph_plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = graph_plan_dir / "plan.json"

    profile = _mode_to_graph_profile(mode)

    graph_command = [
        *graph_cmd,
        "buildplan",
        "--project",
        str(graph_project_path),
        "--profile",
        profile,
        "--out",
        str(plan_path),
    ]
    if target:
        graph_command.extend(["--target", target])

    buildcore_proof = run_dir / "buildcore_run"
    buildcore_command = [
        *buildcore_cmd_base,
        "run",
        "--plan",
        str(plan_path),
        "-j",
        str(max(1, build_jobs)),
        "--proof",
        str(buildcore_proof),
    ]

    commands_text = "\n".join([
        "GRAPH: " + " ".join(shlex.quote(part) for part in graph_command),
        "BUILDCORE: " + " ".join(shlex.quote(part) for part in buildcore_command),
    ]) + "\n"
    write_text(run_dir / "commands.txt", commands_text)
    _append_text(pf / "commands.txt", commands_text)

    graph_stdout = run_dir / "graph_stdout.txt"
    graph_stderr = run_dir / "graph_stderr.txt"
    require_direct_capture = os.environ.get("NGKS_REQUIRE_DIRECT_MSVC_CAPTURE", "").strip() == "1"
    msvc_env = resolve_msvc_env(pf)
    if require_direct_capture and msvc_env is None:
        return _write_blocker(pf, "Direct MSVC capture required but failed.")
    graph_env = dict(os.environ)
    if msvc_env:
        graph_env.update(msvc_env)
    graph_rc = run_command_capture(graph_command, graph_cwd, graph_stdout, graph_stderr, env=graph_env)
    if graph_rc != 0:
        write_text(run_dir / "99_exitcode.txt", f"{graph_rc}\n")
        return graph_rc

    if not plan_path.exists():
        write_text(run_dir / "99_exitcode.txt", "2\n")
        return 2

    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        write_text(run_dir / "plan_validation.txt", f"FAIL\nreason=plan_json_parse_error\nerror={exc}\n")
        write_text(run_dir / "99_exitcode.txt", "2\n")
        return 2

    valid, validation_errors, nodes = _validate_plan_payload(payload if isinstance(payload, dict) else {})
    fallback_added = 0
    if valid and isinstance(payload, dict):
        fallback_added = _inject_qt_deploy_fallback_nodes(
            payload,
            graph_project_path=graph_project_path,
            graph_env=graph_env,
        )
        if fallback_added > 0:
            write_json(plan_path, payload)
            valid, validation_errors, nodes = _validate_plan_payload(payload)

    graph_nodes_count = len(nodes)
    validation_lines = [
        f"status={'PASS' if valid else 'FAIL'}",
        f"nodes_count={graph_nodes_count}",
        f"fallback_qt_deploy_nodes_added={fallback_added}",
        f"errors_count={(0 if valid else len([x for x in validation_errors.splitlines() if x.strip()]))}",
    ]
    if validation_errors:
        validation_lines.append("errors=")
        validation_lines.extend(validation_errors.splitlines())
    write_text(run_dir / "plan_validation.txt", "\n".join(validation_lines) + "\n")
    write_text(pf / "plan_validation.txt", "\n".join(validation_lines) + "\n")
    if not valid:
        write_text(run_dir / "99_exitcode.txt", "2\n")
        return 2

    if graph_nodes_count <= 0:
        write_text(run_dir / "99_exitcode.txt", "2\n")
        return 2

    created_dirs = _precreate_output_dirs(nodes, graph_project_path)
    write_text(run_dir / "created_dirs.txt", "\n".join(created_dirs) + ("\n" if created_dirs else ""))
    write_text(pf / "created_dirs.txt", "\n".join(created_dirs) + ("\n" if created_dirs else ""))

    requires_msvc = _plan_requires_msvc(nodes)
    where_cmd = ["cmd.exe", "/d", "/s", "/c", "where cl"]
    where_result = subprocess.run(where_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=graph_env, check=False)
    where_text = (
        f"rc={where_result.returncode}\n"
        f"stdout:\n{where_result.stdout or ''}\n"
        f"stderr:\n{where_result.stderr or ''}\n"
        f"requires_msvc={requires_msvc}\n"
    )
    write_text(pf / "where_cl.txt", where_text)
    write_text(run_dir / "where_cl.txt", where_text)

    if where_result.returncode != 0 and requires_msvc:
        write_text(run_dir / "99_exitcode.txt", "2\n")
        write_text(
            run_dir / "gate_summary.txt",
            "\n".join(
                [
                    f"graph_nodes_count={graph_nodes_count}",
                    "buildcore_run_nodes=0",
                    "buildcore_skipped_nodes=0",
                    "summary_path=",
                    "status=FAIL",
                    "reason=msvc_not_available_but_required",
                ]
            )
            + "\n",
        )
        write_text(
            pf / "gate_summary.txt",
            "\n".join(
                [
                    f"graph_nodes_count={graph_nodes_count}",
                    "buildcore_run_nodes=0",
                    "buildcore_skipped_nodes=0",
                    "summary_path=",
                    "status=FAIL",
                    "reason=msvc_not_available_but_required",
                ]
            )
            + "\n",
        )
        return 2

    build_stdout = run_dir / "buildcore_stdout.txt"
    build_stderr = run_dir / "buildcore_stderr.txt"
    build_env = dict(graph_env)
    build_env["NGKS_ALLOW_DIRECT_BUILDCORE"] = "1"
    build_rc = run_command_capture(buildcore_command, buildcore_cwd, build_stdout, build_stderr, env=build_env)

    summary_candidates = sorted(buildcore_proof.glob("buildcore_run_*/summary.json"), key=lambda p: str(p))
    summary_path = summary_candidates[-1] if summary_candidates else None
    run_nodes = 0
    skipped_nodes = 0
    if summary_path and summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            run_nodes = int(summary.get("run_nodes", 0))
            skipped_nodes = int(summary.get("skipped_nodes", 0))
        except Exception:
            pass

    final_status = "PASS" if (build_rc == 0 and summary_path is not None and summary_path.exists()) else "FAIL"
    gate_summary = "\n".join(
        [
            f"graph_nodes_count={graph_nodes_count}",
            f"buildcore_run_nodes={run_nodes}",
            f"buildcore_skipped_nodes={skipped_nodes}",
            f"summary_path={summary_path if summary_path else ''}",
            f"status={final_status}",
        ]
    ) + "\n"
    write_text(run_dir / "gate_summary.txt", gate_summary)
    write_text(pf / "gate_summary.txt", gate_summary)
    write_text(run_dir / "99_exitcode.txt", f"{build_rc}\n")
    return build_rc


def run_build(
    project_path: Path,
    pf: Path,
    mode: str,
    profile_path: Path | None = None,
    backend: str = "auto",
    target: str | None = None,
    jobs: int | None = None,
) -> int:
    if backend == "buildcore":
        return _run_buildcore_backend(project_path=project_path, pf=pf, mode=mode, target=target, jobs=jobs)

    input_path = project_path.resolve()
    input_kind = "file" if input_path.is_file() else "dir"
    normalized_input_path = str(input_path)

    direct_sln_input: Path | None = None
    direct_csproj_input: Path | None = None
    if input_path.is_file():
        suffix = input_path.suffix.lower()
        if suffix == ".sln":
            direct_sln_input = input_path
            project_path = input_path.parent
        elif suffix == ".csproj":
            direct_csproj_input = input_path
            project_path = input_path.parent
        else:
            project_path = input_path.parent
    else:
        project_path = input_path

    pf = pf.resolve()
    run_dir = pf / "run_build"
    run_dir.mkdir(parents=True, exist_ok=True)

    start_ts = utc_now_iso()
    start_perf = time.perf_counter()

    profile, loaded_profile_path = _load_profile(project_path, profile_path, pf)
    tool_resolve = resolve_tools(pf)
    resolved_strategy = str(tool_resolve.get("resolved_strategy", "")).strip().lower()
    if resolved_strategy != "graph":
        raise RuntimeError("Graph-only mode enforced.")
    assert resolved_strategy == "graph"

    if not profile:
        error_payload = {
            "error": "profile_missing",
            "message": "Profile not found or invalid. Run profile init first.",
            "project_path": str(project_path),
            "profile_path": str(loaded_profile_path) if loaded_profile_path else None,
        }
        write_json(run_dir / "00_selected_path.json", error_payload)
        write_text(run_dir / "01_bootstrap.txt", "NONE\n")
        write_text(run_dir / "02_cmd_configure.txt", "NONE\n")
        write_text(run_dir / "03_cmd_build.txt", "NONE\n")
        write_text(run_dir / "99_exitcode.txt", "2\n")
        write_json(
            run_dir / "build_receipt.json",
            {
                "start": start_ts,
                "end": utc_now_iso(),
                "exit_code": 2,
                "resolved_strategy": "graph",
                "selected_backend": "unknown",
                "build_skipped": False,
                "fingerprint": None,
                "cmdline": [],
                "elapsed_ms": int((time.perf_counter() - start_perf) * 1000),
                "tool_resolve_path": str(pf / "tool_resolve.json"),
                "tool_versions": {
                    "dotnet": tool_version("dotnet"),
                    "python": tool_version("python"),
                },
            },
        )
        return 2

    selected_strategy, selected_backend, details = _select_path(profile, project_path)
    if direct_sln_input is not None:
        selected_backend = "sln"
    elif direct_csproj_input is not None:
        selected_backend = "csproj"

    if selected_strategy != "graph":
        raise RuntimeError("Graph-only mode enforced.")
    assert selected_strategy == "graph"

    write_json(
        run_dir / "00_strategy_resolution.json",
        {
            "resolved_strategy": selected_strategy,
            "selected_backend": selected_backend,
            "input_kind": input_kind,
            "normalized_input_path": normalized_input_path,
            "details": details,
        },
    )

    selected_payload = {
        "selected_path": selected_strategy,
        "selected_backend": selected_backend,
        "reason": "graph-only mode",
        "details": details,
    }
    write_json(run_dir / "00_selected_path.json", selected_payload)

    bootstrap_text = str(profile.get("bootstrap", {}).get("command", ""))
    bootstrap_cmd = _bootstrap_command(bootstrap_text)
    write_text(run_dir / "01_bootstrap.txt", " ".join(bootstrap_cmd) + "\n" if bootstrap_cmd else "NONE\n")

    configure_cmd: list[str] = []
    build_cmd: list[str] = []
    selected_solution: str | None = None
    selected_solution_configuration: str | None = None
    selected_solution_platform: str | None = None
    selected_solution_resolution_reason: str | None = None
    available_solution_configs: list[tuple[str, str]] = []
    solution_path_for_fingerprint: Path | None = None
    selected_csproj_path: Path | None = None
    build_skipped = False

    dotnet_path = str(tool_resolve.get("dotnet", {}).get("path", ""))
    if selected_backend == "sln":
        selected_solution_path: Path | None = None
        if direct_sln_input is not None:
            selected_solution_path = direct_sln_input.resolve()
            selected_solution = str(selected_solution_path)
        else:
            sln_candidates = profile.get("solution", {}).get("solution_candidates", [])
            if sln_candidates:
                selected_solution = sln_candidates[0]
                selected_solution_path = (project_path / selected_solution).resolve()

        if selected_solution_path is not None:
            solution_path_for_fingerprint = selected_solution_path
            available_solution_configs = parse_sln_solution_configs(str(selected_solution_path))
            selected_conf, selected_plat, config_resolution = _resolve_sln_config(available_solution_configs, mode)
            selected_solution_configuration = selected_conf
            selected_solution_platform = selected_plat
            selected_solution_resolution_reason = str(config_resolution.get("reason"))
            write_json(run_dir / "01_config_resolution.json", config_resolution)
            if dotnet_path:
                build_cmd = [dotnet_path, "build", str(selected_solution_path)]
                if selected_solution_configuration:
                    build_cmd.append(f"-p:Configuration={selected_solution_configuration}")
                if selected_solution_platform:
                    build_cmd.append(f"-p:Platform={selected_solution_platform}")

    elif selected_backend == "csproj":
        csproj = direct_csproj_input if direct_csproj_input is not None else next(project_path.glob("*.csproj"), None)
        if csproj and dotnet_path:
            selected_csproj_path = csproj.resolve()
            config = "Debug" if mode.lower().startswith("debug") else "Release"
            build_cmd = [dotnet_path, "build", str(selected_csproj_path), "-c", config]

    write_text(run_dir / "02_cmd_configure.txt", " ".join(configure_cmd) + "\n" if configure_cmd else "NONE\n")
    if build_cmd:
        build_cmd_log = _normalize_solution_build_log(build_cmd)
        write_text(run_dir / "03_cmd_build.txt", " ".join(build_cmd_log) + "\n")
    else:
        write_text(run_dir / "03_cmd_build.txt", "NONE\n")

    if available_solution_configs:
        write_json(
            run_dir / "04_available_sln_configs.json",
            {
                "solution": selected_solution,
                "configs": [{"configuration": conf, "platform": plat} for conf, plat in available_solution_configs],
            },
        )

    if not build_cmd and selected_backend == "unknown":
        write_text(run_dir / "06_build_skipped.txt", "Build skipped: no supported dotnet backend detected for target profile.\n")
        write_text(run_dir / "99_exitcode.txt", "0\n")
        receipt = {
            "start": start_ts,
            "end": utc_now_iso(),
            "elapsed_ms": int((time.perf_counter() - start_perf) * 1000),
            "exit_code": 0,
            "resolved_strategy": selected_strategy,
            "selected_backend": selected_backend,
            "selected_solution": selected_solution,
            "selected_solution_configuration": selected_solution_configuration,
            "selected_solution_platform": selected_solution_platform,
            "selected_solution_resolution_reason": selected_solution_resolution_reason,
            "plan_id": None,
            "profile_path": str(loaded_profile_path) if loaded_profile_path else None,
            "tool_resolve_path": str(pf / "tool_resolve.json"),
            "tool_versions": {
                "dotnet": tool_version("dotnet"),
                "python": tool_version("python"),
            },
            "command_hashes": {
                "bootstrap": hash_command(bootstrap_cmd) if bootstrap_cmd else None,
                "configure": None,
                "build": None,
            },
            "cmdline": [],
            "fingerprint": None,
            "build_skipped": True,
            "graph_status": "skipped_no_supported_backend",
            "graph_exit_code": None,
        }
        write_json(run_dir / "build_receipt.json", receipt)
        return 0

    plan_id, graph_plan_path = generate_build_plan(
        run_dir=run_dir,
        project_path=project_path,
        bootstrap_cmd=bootstrap_cmd,
        configure_cmd=configure_cmd,
        build_cmd=build_cmd,
        backend=selected_backend,
    )

    graph_status, graph_exit_code = _run_graph_cli_if_available(project_path, run_dir, graph_plan_path)

    exit_code = 0
    fingerprint_files = _collect_strategy_fingerprint_files(selected_backend, project_path, solution_path_for_fingerprint, selected_csproj_path)
    current_fingerprint = _compute_fingerprint(fingerprint_files) if fingerprint_files else _compute_fingerprint([])

    target_for_state = direct_sln_input or direct_csproj_input or project_path
    state_key = f"{selected_backend}|{str(target_for_state.resolve()).lower()}"
    state_json_path = run_dir / "07_last_successful_fingerprint.json"
    state_payload: dict[str, Any] = {}
    if state_json_path.exists():
        try:
            state_payload = json.loads(state_json_path.read_text(encoding="utf-8"))
        except Exception:
            state_payload = {}

    entry = state_payload.get(state_key, {}) if isinstance(state_payload, dict) else {}
    previous_fingerprint = str(entry.get("fingerprint", "")).strip() if isinstance(entry, dict) else ""
    previous_exit = str(entry.get("exit_code", "")).strip() if isinstance(entry, dict) else ""
    if not previous_fingerprint:
        previous_fingerprint = None
    if not previous_exit:
        previous_exit = None

    changed = current_fingerprint != (previous_fingerprint or "")
    write_json(
        run_dir / "05_build_fingerprint.json",
        {
            "files_hashed": [str(path) for path in fingerprint_files],
            "fingerprint": current_fingerprint,
            "previous_fingerprint": previous_fingerprint,
            "changed": changed,
        },
    )

    if (not changed) and previous_fingerprint and previous_exit == "0":
        build_skipped = True
        write_text(run_dir / "06_build_skipped.txt", "Build skipped: fingerprint matches last successful build.\n")
        write_text(run_dir / "99_exitcode.txt", "0\n")
        exit_code = 0

    if selected_backend == "csproj":
        dotnet_info_path = run_dir / "dotnet_info.txt"
        if not dotnet_info_path.exists() and dotnet_path:
            run_command_capture([dotnet_path, "--info"], project_path, dotnet_info_path, run_dir / "dotnet_info.stderr.txt")

    if bootstrap_cmd:
        bootstrap_out = run_dir / "09_bootstrap_stdout.txt"
        bootstrap_err = run_dir / "09_bootstrap_stderr.txt"
        code = run_command_capture(bootstrap_cmd, project_path, bootstrap_out, bootstrap_err)
        if code != 0:
            exit_code = code

    if exit_code == 0 and configure_cmd:
        code = run_command_capture(
            configure_cmd,
            project_path,
            run_dir / "10_configure_stdout.txt",
            run_dir / "10_configure_stderr.txt",
        )
        if code != 0:
            exit_code = code

    build_stdout = run_dir / "10_build_stdout.txt"
    build_stderr = run_dir / "11_build_stderr.txt"
    if exit_code == 0 and build_cmd and not build_skipped:
        code = run_command_capture(build_cmd, project_path, build_stdout, build_stderr)
        if code != 0:
            exit_code = code

    if not build_cmd:
        write_json(
            run_dir / "build_failure.json",
            {
                "reason": "no supported graph backend command",
                "selected_backend": selected_backend,
                "tool_resolve": tool_resolve,
                "tool_resolve_path": str(pf / "tool_resolve.json"),
            },
        )
        exit_code = 127

    write_text(run_dir / "99_exitcode.txt", f"{exit_code}\n")

    if exit_code == 0:
        fingerprint_json = run_dir / "05_build_fingerprint.json"
        if fingerprint_json.exists():
            payload = json.loads(fingerprint_json.read_text(encoding="utf-8"))
            fingerprint_value = str(payload.get("fingerprint", "")).strip()
            write_text(run_dir / "07_last_successful_fingerprint.txt", fingerprint_value + "\n")
            if not isinstance(state_payload, dict):
                state_payload = {}
            state_payload[state_key] = {
                "fingerprint": fingerprint_value,
                "exit_code": 0,
            }
            write_json(state_json_path, state_payload)

    if exit_code != 0:
        classification = _classify_failure(build_stdout, build_stderr)
        write_json(run_dir / "98_failure_classification.json", classification)

    receipt = {
        "start": start_ts,
        "end": utc_now_iso(),
        "elapsed_ms": int((time.perf_counter() - start_perf) * 1000),
        "exit_code": exit_code,
        "resolved_strategy": selected_strategy,
        "selected_backend": selected_backend,
        "selected_solution": selected_solution,
        "selected_solution_configuration": selected_solution_configuration,
        "selected_solution_platform": selected_solution_platform,
        "selected_solution_resolution_reason": selected_solution_resolution_reason,
        "plan_id": plan_id,
        "profile_path": str(loaded_profile_path) if loaded_profile_path else None,
        "tool_resolve_path": str(pf / "tool_resolve.json"),
        "tool_versions": {
            "dotnet": tool_version("dotnet"),
            "python": tool_version("python"),
        },
        "command_hashes": {
            "bootstrap": hash_command(bootstrap_cmd) if bootstrap_cmd else None,
            "configure": hash_command(configure_cmd) if configure_cmd else None,
            "build": hash_command(build_cmd) if build_cmd else None,
        },
        "cmdline": build_cmd,
        "fingerprint": current_fingerprint,
        "build_skipped": build_skipped,
        "graph_status": graph_status,
        "graph_exit_code": graph_exit_code,
    }
    write_json(run_dir / "build_receipt.json", receipt)
    return exit_code
