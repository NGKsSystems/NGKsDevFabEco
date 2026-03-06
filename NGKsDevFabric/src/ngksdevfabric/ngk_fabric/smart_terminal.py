from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Thread
from typing import Optional, TextIO

from .receipts import ensure_dir, write_text


@dataclass
class ShellPlan:
    shell: str
    confidence: float
    reasons: list[str]
    raw_input: str
    normalized_command: str


def resolve_smart_terminal_enabled(cli_mode: str | None) -> tuple[bool, str]:
    if cli_mode == "on":
        return True, "cli:on"
    if cli_mode == "off":
        return False, "cli:off"

    env_value = os.environ.get("NGK_SMART_TERMINAL")
    if env_value is not None:
        if env_value.strip() == "0":
            return False, "env:NGK_SMART_TERMINAL=0"
        return True, "env:NGK_SMART_TERMINAL"

    return True, "default:on"


def detect_shell(command: str) -> ShellPlan:
    raw_input = command
    stripped = command.strip()
    lowered = stripped.lower()

    if lowered.startswith("ps:"):
        normalized = stripped[3:].strip()
        return ShellPlan(
            shell="powershell",
            confidence=1.0,
            reasons=["prefix ps:"],
            raw_input=raw_input,
            normalized_command=normalized,
        )

    if lowered.startswith("cmd:"):
        normalized = stripped[4:].strip()
        return ShellPlan(
            shell="cmd",
            confidence=1.0,
            reasons=["prefix cmd:"],
            raw_input=raw_input,
            normalized_command=normalized,
        )

    if re.search(r"\.ps1(\s|$|'|\")", stripped, flags=re.IGNORECASE):
        return ShellPlan(
            shell="powershell",
            confidence=0.95,
            reasons=["contains .ps1 extension"],
            raw_input=raw_input,
            normalized_command=stripped,
        )

    if re.search(r"\.(cmd|bat)(\s|$|'|\")", stripped, flags=re.IGNORECASE):
        return ShellPlan(
            shell="cmd",
            confidence=0.95,
            reasons=["contains .cmd/.bat extension"],
            raw_input=raw_input,
            normalized_command=stripped,
        )

    ps_tokens = ["$env:", "get-childitem", "join-path", "out-file", "set-content"]
    if any(token in lowered for token in ps_tokens):
        return ShellPlan(
            shell="powershell",
            confidence=0.9,
            reasons=["powershell heuristic token match"],
            raw_input=raw_input,
            normalized_command=stripped,
        )

    cmd_tokens = ["set ", "call ", "%var%", "&&", "if exist"]
    if any(token in lowered for token in cmd_tokens):
        return ShellPlan(
            shell="cmd",
            confidence=0.9,
            reasons=["cmd heuristic token match"],
            raw_input=raw_input,
            normalized_command=stripped,
        )

    return ShellPlan(
        shell="powershell",
        confidence=0.6,
        reasons=["default powershell fallback"],
        raw_input=raw_input,
        normalized_command=stripped,
    )


def _stream_reader(pipe: TextIO, sink: TextIO, terminal: TextIO) -> None:
    for line in iter(pipe.readline, ""):
        sink.write(line)
        sink.flush()
        terminal.write(line)
        terminal.flush()


def _execute_and_stream(exec_cmd: list[str], run_dir: Path, cwd: Optional[Path]) -> int:
    stdout_path = run_dir / "10_stdout.txt"
    stderr_path = run_dir / "11_stderr.txt"

    ensure_dir(stdout_path.parent)
    with stdout_path.open("w", encoding="utf-8", newline="\n") as out_handle, stderr_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as err_handle:
        try:
            proc = subprocess.Popen(
                exec_cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            err_handle.write(f"tool missing: {exc}\n")
            err_handle.flush()
            return 127
        except Exception as exc:
            err_handle.write(f"execution error: {exc}\n")
            err_handle.flush()
            return 126

        out_thread = Thread(target=_stream_reader, args=(proc.stdout, out_handle, sys.stdout), daemon=True)
        err_thread = Thread(target=_stream_reader, args=(proc.stderr, err_handle, sys.stderr), daemon=True)
        out_thread.start()
        err_thread.start()
        proc.wait()
        out_thread.join()
        err_thread.join()
        return int(proc.returncode)


def _allocate_run_dir(pf: Path) -> Path:
    root = pf / "run_smartterm"
    ensure_dir(root)

    existing_indices: list[int] = []
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith("run_"):
            suffix = child.name[4:]
            if suffix.isdigit():
                existing_indices.append(int(suffix))

    next_index = (max(existing_indices) + 1) if existing_indices else 1
    run_dir = root / f"run_{next_index:04d}"
    ensure_dir(run_dir)
    write_text(root / "last_run_dir.txt", str(run_dir) + "\n")
    return run_dir


def run_shell(plan: ShellPlan, pf: Path, cwd: Optional[Path]) -> tuple[int, Path]:
    run_dir = _allocate_run_dir(pf)
    started = time.perf_counter()

    write_text(run_dir / "01_request.txt", plan.raw_input + "\n")
    (run_dir / "02_detected_shell.json").write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")

    if plan.shell == "cmd":
        exec_cmd = ["cmd.exe", "/d", "/s", "/c", plan.normalized_command]
    else:
        pwsh = shutil.which("pwsh")
        shell_exe = pwsh if pwsh else "powershell.exe"
        exec_cmd = [shell_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", plan.normalized_command]

    write_text(run_dir / "03_exec_commandline.txt", " ".join(exec_cmd) + "\n")
    code = _execute_and_stream(exec_cmd, run_dir, cwd)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    write_text(run_dir / "98_elapsed_ms.txt", f"{elapsed_ms}\n")
    write_text(run_dir / "99_exitcode.txt", f"{code}\n")
    return code, run_dir


def run_shell_direct(command: str, pf: Path, cwd: Optional[Path], plan: Optional[ShellPlan] = None) -> tuple[int, Path]:
    run_dir = _allocate_run_dir(pf)
    started = time.perf_counter()

    write_text(run_dir / "01_request.txt", command + "\n")
    detection = asdict(plan) if plan else {
        "shell": "direct",
        "confidence": 1.0,
        "reasons": ["bypass enabled via NGK_SMART_TERMINAL=0"],
        "raw_input": command,
        "normalized_command": command,
    }
    detection["bypass_enabled"] = True
    (run_dir / "02_detected_shell.json").write_text(json.dumps(detection, indent=2), encoding="utf-8")

    exec_cmd = ["cmd.exe", "/d", "/s", "/c", command]
    write_text(run_dir / "03_exec_commandline.txt", " ".join(exec_cmd) + "\n")
    code = _execute_and_stream(exec_cmd, run_dir, cwd)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    write_text(run_dir / "98_elapsed_ms.txt", f"{elapsed_ms}\n")
    write_text(run_dir / "99_exitcode.txt", f"{code}\n")
    return code, run_dir
