from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from ngksgraph.cli import main
from ngksgraph.hashutil import sha256_json


CONFIG_TEXT = "\n".join(
    [
        'name = "headless"',
        'out_dir = "build"',
        '',
        '[profiles.debug]',
        'cflags = ["/Od", "/Z7"]',
        'defines = ["DEBUG"]',
        'ldflags = []',
        '',
        '[[targets]]',
        'name = "headless"',
        'type = "exe"',
        'src_glob = ["src/**/*.cpp"]',
        'include_dirs = ["include"]',
        'defines = []',
        'cflags = []',
        'libs = []',
        'lib_dirs = []',
        'ldflags = []',
        'cxx_std = 20',
        'links = []',
    ]
)


def test_plan_command_emits_build_plan_json(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "include").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(CONFIG_TEXT, encoding="utf-8")

    rc = main(
        [
            "plan",
            "--project",
            str(tmp_path),
            "--target",
            "headless",
            "--profile",
            "debug",
            "--format",
            "json",
        ]
    )
    assert rc == 0

    plan_path = tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json"
    assert plan_path.exists()

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["project_root"].replace("\\", "/").endswith(str(tmp_path).replace("\\", "/"))
    assert isinstance(payload.get("graph_version"), str) and payload["graph_version"]
    assert isinstance(payload.get("generated_at"), str) and payload["generated_at"].endswith("Z")
    assert payload["project"] == "headless"
    assert payload["profile"] == "debug"
    assert payload["target"] == "headless"
    assert isinstance(payload.get("plan_id"), str) and payload["plan_id"]

    assert len(payload["targets"]) == 1
    assert payload["targets"][0]["output_path"].endswith("headless.exe")
    steps = payload["targets"][0]["steps"]
    kinds = {step["kind"] for step in steps}
    assert "compile" in kinds
    assert "link" in kinds
    for step in steps:
        assert isinstance(step.get("step_id"), str) and step["step_id"]
        assert isinstance(step.get("inputs"), list)
        assert isinstance(step.get("outputs"), list)
        assert isinstance(step.get("defines"), list)
        assert isinstance(step.get("include_dirs"), list)
        assert isinstance(step.get("cflags"), list)
        assert isinstance(step.get("ldflags"), list)
        assert isinstance(step.get("libs"), list)
        assert isinstance(step.get("toolchain"), str)
        assert isinstance(step.get("fingerprint"), str) and step["fingerprint"]

    exe_path = tmp_path / "build" / "debug" / "bin" / "headless.exe"
    assert not exe_path.exists(), "plan command must not execute build steps"
    assert not (tmp_path / "build" / "debug" / "bin" / "headless.exe").exists(), "plan command must not emit build binaries"
    assert not (tmp_path / "build" / "debug" / "compile_commands.json").exists(), "plan command must not emit compdb"


def test_plan_fingerprints_and_plan_id_stable_for_identical_input(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "include").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(CONFIG_TEXT, encoding="utf-8")

    args = [
        "plan",
        "--project",
        str(tmp_path),
        "--target",
        "headless",
        "--profile",
        "debug",
        "--format",
        "json",
    ]
    assert main(args) == 0
    first = json.loads((tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json").read_text(encoding="utf-8"))

    assert main(args) == 0
    second = json.loads((tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json").read_text(encoding="utf-8"))

    assert first["plan_id"] == second["plan_id"]

    first_fingerprints = [step["fingerprint"] for step in first["targets"][0]["steps"]]
    second_fingerprints = [step["fingerprint"] for step in second["targets"][0]["steps"]]
    assert first_fingerprints == second_fingerprints


def test_plan_id_matches_normalized_payload_without_timestamp(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "include").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(CONFIG_TEXT, encoding="utf-8")

    args = [
        "plan",
        "--project",
        str(tmp_path),
        "--target",
        "headless",
        "--profile",
        "debug",
        "--format",
        "json",
    ]
    assert main(args) == 0

    payload = json.loads((tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json").read_text(encoding="utf-8"))
    expected_plan_id = payload["plan_id"]

    canonical = dict(payload)
    canonical.pop("plan_id", None)
    canonical.pop("generated_at", None)
    recomputed = sha256_json(canonical)
    assert recomputed == expected_plan_id


def test_repeated_plan_json_changes_only_timestamp(tmp_path: Path):
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "include").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}", encoding="utf-8")
    (tmp_path / "ngksgraph.toml").write_text(CONFIG_TEXT, encoding="utf-8")

    args = [
        "plan",
        "--project",
        str(tmp_path),
        "--target",
        "headless",
        "--profile",
        "debug",
        "--format",
        "json",
    ]

    assert main(args) == 0
    first = json.loads((tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json").read_text(encoding="utf-8"))

    time.sleep(1.1)

    assert main(args) == 0
    second = json.loads((tmp_path / "build_graph" / "debug" / "ngksgraph_plan.json").read_text(encoding="utf-8"))

    assert first["generated_at"] != second["generated_at"]

    first_norm = dict(first)
    second_norm = dict(second)
    first_norm.pop("generated_at", None)
    second_norm.pop("generated_at", None)
    assert first_norm == second_norm


def test_plan_missing_target_exit_2_and_stderr(tmp_path: Path):
    proj = tmp_path / "p"
    proj.mkdir()

    (proj / "ngksgraph.toml").write_text(
        """
[build]
default_target = "app"

[profiles.debug]

[[targets]]
name = "app"
type = "exe"
src_glob = ["src/app/main.cpp"]
""".lstrip(),
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        "-m",
        "ngksgraph",
        "plan",
        "--project",
        str(proj),
        "--target",
        "does_not_exist",
        "--profile",
        "debug",
        "--format",
        "json",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "TARGET_NOT_FOUND: does_not_exist" in result.stderr
    assert "Traceback" not in result.stderr
