from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_id = "devfab_runtime_validation_pass_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    proof_dir = repo_root / "_proof" / "runs" / run_id
    proof_dir.mkdir(parents=True, exist_ok=True)

    notebook_path = repo_root / "_proof" / "smoke_latest_proof.ipynb"
    smoke_script = repo_root / "tools" / "smoke_latest_proof.py"
    interpreter = repo_root / ".venv" / "Scripts" / "python.exe"

    _write(
        proof_dir / "00_run_manifest.json",
        json.dumps(
            {
                "app": "NGKsDevFabEco",
                "objective": "final_notebook_free_runtime_validation",
                "run_id": run_id,
                "timestamp": _now_iso(),
                "workspace_root": str(repo_root.resolve()),
            },
            indent=2,
        )
        + "\n",
    )

    _write(proof_dir / "interpreter_used.txt", str(interpreter.resolve()) + "\n")

    command = [str(interpreter.resolve()), str(smoke_script.resolve())]
    _write(proof_dir / "runtime_command.txt", " ".join(command) + "\n")

    proc = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env={**os.environ, **{"PYTHONPATH": str((repo_root / "NGKsDevFabric" / "src").resolve())}},
    )

    _write(proof_dir / "runtime_stdout.txt", proc.stdout or "")
    _write(proof_dir / "runtime_stderr.txt", proc.stderr or "")

    parsed_stdout: dict[str, object] = {}
    if proc.stdout:
        try:
            parsed_stdout = json.loads(proc.stdout)
        except Exception:
            parsed_stdout = {}

    bundle_path = Path(str(parsed_stdout.get("bundle_path", ""))) if parsed_stdout.get("bundle_path") else None
    smoke_artifacts = []
    if bundle_path and bundle_path.exists():
        for name in [
            "00_run_manifest.json",
            "18_summary.md",
            "artifact.txt",
            "smoke_start.marker",
            "smoke_done.marker",
        ]:
            if (bundle_path / name).is_file():
                smoke_artifacts.append(str((bundle_path / name).resolve()))

    latest_zip = repo_root / "_proof" / "latest_proof.zip"
    if latest_zip.is_file():
        smoke_artifacts.append(str(latest_zip.resolve()))

    jupyter_terms = ["jupyter", "ipykernel", ".ipynb", "notebook"]
    text_to_scan = (proc.stdout or "") + "\n" + (proc.stderr or "") + "\n" + " ".join(command)
    lowered = text_to_scan.lower()
    jupyter_called = "jupyter" in lowered
    ipykernel_called = "ipykernel" in lowered
    ipynb_executed = ".ipynb" in lowered or "run cell" in lowered

    smoke_created = len(smoke_artifacts) > 0 and bool(bundle_path and bundle_path.exists())
    gate = "PASS"
    if not smoke_created or proc.returncode != 0:
        gate = "PARTIAL"
    if jupyter_called or ipykernel_called or ipynb_executed:
        gate = "FAIL"

    _write(
        proof_dir / "smoke_output_files.json",
        json.dumps(
            {
                "bundle_path": str(bundle_path.resolve()) if bundle_path else "",
                "artifacts": smoke_artifacts,
                "process_return_code": int(proc.returncode),
            },
            indent=2,
        )
        + "\n",
    )

    _write(
        proof_dir / "notebook_free_runtime_validation.json",
        json.dumps(
            {
                "notebook_path_exists": notebook_path.exists(),
                "replacement_script_exists": smoke_script.exists(),
                "jupyter_called": jupyter_called,
                "ipykernel_called": ipykernel_called,
                "ipynb_executed": ipynb_executed,
                "process_return_code": int(proc.returncode),
                "final_runtime_gate": gate,
            },
            indent=2,
        )
        + "\n",
    )

    _write(
        proof_dir / "summary.md",
        "\n".join(
            [
                "# Runtime Validation Summary",
                "",
                f"- proof_folder: {proof_dir}",
                f"- notebook_path_exists: {str(notebook_path.exists()).lower()}",
                f"- replacement_script_exists: {str(smoke_script.exists()).lower()}",
                f"- interpreter: {interpreter.resolve()}",
                f"- runtime_command: {' '.join(command)}",
                f"- jupyter_called: {str(jupyter_called).lower()}",
                f"- ipykernel_called: {str(ipykernel_called).lower()}",
                f"- ipynb_executed: {str(ipynb_executed).lower()}",
                f"- smoke_artifacts_created: {len(smoke_artifacts)}",
                f"- final_runtime_gate: {gate}",
            ]
        )
        + "\n",
    )

    _write(
        proof_dir / "18_summary.md",
        "\n".join(
            [
                "# Runtime Validation Final Summary",
                "",
                f"- Notebook path absent: {'yes' if not notebook_path.exists() else 'no'}",
                f"- Replacement script present: {'yes' if smoke_script.exists() else 'no'}",
                f"- Plain Python command completed: {'yes' if proc.returncode == 0 else 'no'}",
                f"- Jupyter/ipykernel activity detected: {'yes' if (jupyter_called or ipykernel_called or ipynb_executed) else 'no'}",
                f"- Smoke artifacts observed: {'yes' if smoke_created else 'no'}",
                f"- Final gate: {gate}",
            ]
        )
        + "\n",
    )

    print(json.dumps({"proof_dir": str(proof_dir.resolve()), "final_runtime_gate": gate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
