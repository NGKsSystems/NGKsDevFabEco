from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path
import tomllib
import glob

root = Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco")
packet = Path((root / ".triage_work.txt").read_text(encoding="utf-8").strip())
raw_dir = packet / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)

ngksgraph = root / ".venv" / "Scripts" / "ngksgraph.exe"
ngksdevfabric = root / ".venv" / "Scripts" / "ngksdevfabric.exe"

repos = [
    {"name": "NGKsUI Runtime", "path": Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsUI Runtime"), "has_profiles": True, "profile": "debug"},
    {"name": "NGKsMediaLab", "path": Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab"), "has_profiles": False, "profile": None},
    {"name": "NGKsFileVisionary", "path": Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsFileVisionary"), "has_profiles": True, "profile": "debug"},
    {"name": "NGKsPlayerNative", "path": Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsPlayerNative"), "has_profiles": True, "profile": "debug"},
    {"name": "NGKsGraph", "path": Path(r"C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph"), "has_profiles": True, "profile": "debug"},
]

interesting_env = [
    "PATH", "INCLUDE", "LIB", "LIBPATH", "VCINSTALLDIR", "VCToolsInstallDir",
    "VSINSTALLDIR", "VisualStudioVersion", "Qt6_DIR", "QTDIR", "QT_PLUGIN_PATH", "CMAKE_PREFIX_PATH"
]

def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")

def run_cmd(args: list[str], cwd: Path) -> dict:
    p = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True)
    out = (p.stdout or "")
    err = (p.stderr or "")
    both = (out + ("\n" if out and err else "") + err).strip()
    return {
        "args": args,
        "cwd": str(cwd),
        "exit_code": int(p.returncode),
        "stdout": out,
        "stderr": err,
        "combined": both,
    }

def extract_plan_path(config_output: str) -> str | None:
    m = re.search(r"Configured plan:\s*(.+)", config_output)
    return m.group(1).strip() if m else None

def find_build_run_dir(build_output: str) -> str | None:
    m = re.search(r"build_run_dir=(.+)", build_output)
    return m.group(1).strip() if m else None

def scan_for_invocation_and_node(build_run_dir: Path | None, combined: str) -> tuple[str, str]:
    invocation = "not_found"
    failing_node = "not_found"
    lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
    for ln in lines:
        if "ngksbuildcore" in ln.lower():
            invocation = ln
            break
    for ln in lines:
        l = ln.lower()
        if "failing node" in l or "failed node" in l or "target=" in l or "target:" in l:
            failing_node = ln
            break

    if build_run_dir and build_run_dir.exists():
        for p in build_run_dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".txt", ".log", ".json", ".md"}:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if invocation == "not_found":
                for ln in txt.splitlines():
                    if "ngksbuildcore" in ln.lower() or "python -m ngksbuildcore" in ln.lower():
                        invocation = f"{p}: {ln.strip()}"
                        break
            if failing_node == "not_found":
                for ln in txt.splitlines():
                    l = ln.lower()
                    if "failing node" in l or "failed node" in l or "target=" in l or "target:" in l:
                        failing_node = f"{p}: {ln.strip()}"
                        break
            if invocation != "not_found" and failing_node != "not_found":
                break
    return invocation, failing_node

def classify_build_failure(output: str, code: int) -> str:
    low = output.lower()
    if code == 0:
        return "NONE"
    if "permission denied" in low or "being used by another process" in low or "access is denied" in low:
        return "PERMISSION_OR_LOCK_ISSUE"
    if "not recognized as an internal or external command" in low or "no such file or directory" in low:
        return "PATH_RESOLUTION_ERROR"
    if "cl.exe" in low or "msbuild" in low or ("qt" in low and "missing" in low):
        return "TOOLCHAIN_MISSING"
    if "invalid" in low and "plan" in low:
        return "INVALID_PLAN_STRUCTURE"
    if "workdir" in low or "working directory" in low:
        return "WORKDIR_ERROR"
    if "root_cause_stage=buildcore_execution_failure" in low or "buildcore_nonzero_exit" in low:
        return "SUBPROCESS_FAILURE"
    return "OTHER"

def classify_source_failure(output: str, code: int) -> str:
    low = output.lower()
    if code == 0 or "no_sources_matched" not in low:
        return "NONE"
    return "BAD_GLOB_OR_TARGET_CONFIG"

def ownership_for_build(ftype: str) -> str:
    if ftype in {"INVALID_PLAN_STRUCTURE", "WORKDIR_ERROR"}:
        return "ecosystem"
    if ftype in {"TOOLCHAIN_MISSING", "PATH_RESOLUTION_ERROR", "PERMISSION_OR_LOCK_ISSUE"}:
        return "environment"
    if ftype in {"SUBPROCESS_FAILURE", "OTHER"}:
        return "repo_or_environment"
    return "n/a"

def ownership_for_source(stype: str) -> str:
    if stype == "BAD_GLOB_OR_TARGET_CONFIG":
        return "repo"
    return "n/a"

all_rows = []
build_fail_rows = []
source_fail_rows = []

for repo in repos:
    name = repo["name"]
    rpath: Path = repo["path"]
    slug = safe(name)
    rdir = raw_dir / slug
    rdir.mkdir(parents=True, exist_ok=True)

    env_snapshot = {k: os.environ.get(k, "") for k in interesting_env}
    (rdir / "00_env_snapshot.json").write_text(json.dumps(env_snapshot, indent=2), encoding="utf-8")

    cfg_args = [str(ngksgraph), "configure", "--project", str(rpath)]
    if repo["has_profiles"] and repo["profile"]:
        cfg_args += ["--profile", str(repo["profile"])]
    cfg = run_cmd(cfg_args, cwd=rpath)
    (rdir / "10_configure.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    plan_path = extract_plan_path(cfg["combined"])
    plan_snippet = "plan_not_found"
    if plan_path:
        p = Path(plan_path)
        if p.exists():
            try:
                pobj = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(pobj, dict):
                    keys = list(pobj.keys())[:10]
                    plan_snippet = f"plan_keys={keys}; target={pobj.get('target')}"
                else:
                    plan_snippet = f"plan_type={type(pobj).__name__}"
            except Exception as ex:
                plan_snippet = f"plan_parse_error={ex}"

    build_args = [str(ngksdevfabric), "build", "."]
    if repo["has_profiles"] and repo["profile"]:
        build_args += ["--profile", str(repo["profile"])]
    bld = run_cmd(build_args, cwd=rpath)
    (rdir / "20_build.json").write_text(json.dumps(bld, indent=2), encoding="utf-8")

    build_run_dir_s = find_build_run_dir(bld["combined"])
    build_run_dir = Path(build_run_dir_s) if build_run_dir_s else None

    invocation, failing_node = scan_for_invocation_and_node(build_run_dir, bld["combined"])
    btype = classify_build_failure(bld["combined"], bld["exit_code"])
    bown = ownership_for_build(btype)

    source_type = classify_source_failure(cfg["combined"], cfg["exit_code"])
    sown = ownership_for_source(source_type)

    key_build_lines = []
    for ln in bld["combined"].splitlines():
        if any(tok in ln for tok in ["root_cause_stage", "root_cause_code", "exit_code=", "error", "ERROR", "failed", "Failed"]):
            key_build_lines.append(ln.strip())
    key_build_lines = key_build_lines[:12]

    key_cfg_lines = []
    for ln in cfg["combined"].splitlines():
        if any(tok in ln for tok in ["CONFIG_ERROR", "NO_SOURCES_MATCHED", "error", "ERROR", "Profiles are defined"]):
            key_cfg_lines.append(ln.strip())
    key_cfg_lines = key_cfg_lines[:12]

    row = {
        "repo": name,
        "repo_path": str(rpath),
        "configure": {
            "cmd": cfg_args,
            "exit_code": cfg["exit_code"],
            "plan_path": plan_path,
            "plan_snippet": plan_snippet,
            "key_lines": key_cfg_lines,
            "source_failure_type": source_type,
            "source_ownership": sown,
        },
        "build": {
            "cmd": build_args,
            "exit_code": bld["exit_code"],
            "build_run_dir": build_run_dir_s,
            "invocation": invocation,
            "first_failing_node": failing_node,
            "key_lines": key_build_lines,
            "build_failure_type": btype,
            "build_ownership": bown,
            "cwd": str(rpath),
        },
        "env_snapshot_file": str(rdir / "00_env_snapshot.json"),
    }
    all_rows.append(row)

    if bld["exit_code"] != 0:
        build_fail_rows.append(row)
    if source_type != "NONE":
        source_fail_rows.append(row)

    lines20 = [
        f"# BuildCore Analysis - {name}",
        "",
        f"- repo: {rpath}",
        f"- command: {' '.join(build_args)}",
        f"- working_directory: {rpath}",
        f"- exit_code: {bld['exit_code']}",
        f"- classification: {btype}",
        f"- ownership: {bown}",
        f"- plan_path: {plan_path or 'not_found'}",
        f"- first_failing_node: {failing_node}",
        f"- buildcore_invocation: {invocation}",
        "",
        "## Key stderr/stdout lines",
    ]
    if key_build_lines:
        lines20.extend([f"- {ln}" for ln in key_build_lines])
    else:
        lines20.append("- <none captured>")
    lines20 += [
        "",
        "## Evidence files",
        f"- env: {rdir / '00_env_snapshot.json'}",
        f"- configure: {rdir / '10_configure.json'}",
        f"- build: {rdir / '20_build.json'}",
    ]
    (packet / f"20_{safe(name)}_buildcore_analysis.md").write_text("\n".join(lines20) + "\n", encoding="utf-8")

    if source_type != "NONE":
        config_path = rpath / "ngksgraph.toml"
        src_glob = []
        targets_info = "unavailable"
        glob_matches: dict[str, list[str]] = {}
        if config_path.exists():
            try:
                cfg_obj = tomllib.loads(config_path.read_text(encoding="utf-8"))
                raw_glob = cfg_obj.get("src_glob", []) if isinstance(cfg_obj, dict) else []
                if isinstance(raw_glob, list):
                    src_glob = [str(x) for x in raw_glob]
                elif isinstance(raw_glob, str):
                    src_glob = [raw_glob]
                targets_info = str(cfg_obj.get("targets", "<no targets key>"))
            except Exception as ex:
                targets_info = f"toml_parse_error={ex}"
        for g in src_glob:
            glob_matches[g] = [str(Path(p)) for p in glob.glob(str(rpath / g), recursive=True)][:25]

        source_files = []
        for ext in ("*.c", "*.cc", "*.cpp", "*.cxx", "*.h", "*.hpp"):
            source_files.extend([str(p) for p in rpath.rglob(ext)])
            if len(source_files) > 50:
                break
        source_files = source_files[:50]

        lines21 = [
            f"# Sources Analysis - {name}",
            "",
            f"- repo: {rpath}",
            f"- configure_command: {' '.join(cfg_args)}",
            f"- configure_exit_code: {cfg['exit_code']}",
            f"- classification: {source_type}",
            f"- ownership: {sown}",
            "",
            "## ngksgraph.toml inspection",
            f"- config_path: {config_path}",
            f"- src_glob: {src_glob}",
            f"- targets: {targets_info}",
            "",
            "## Manual glob expansion",
        ]
        if glob_matches:
            for g, v in glob_matches.items():
                lines21.append(f"- {g}: {len(v)} matches; sample={v[:5]}")
        else:
            lines21.append("- <no globs>")
        lines21 += ["", "## Actual source files sample"]
        if source_files:
            lines21.extend([f"- {s}" for s in source_files])
        else:
            lines21.append("- <no source files found>")
        lines21 += ["", "## Error lines"]
        if key_cfg_lines:
            lines21.extend([f"- {ln}" for ln in key_cfg_lines])
        else:
            lines21.append("- <none captured>")
        lines21 += ["", "## Evidence files", f"- configure: {rdir / '10_configure.json'}"]

        (packet / f"21_{safe(name)}_sources_analysis.md").write_text("\n".join(lines21) + "\n", encoding="utf-8")

(packet / "30_triage_rows.json").write_text(json.dumps(all_rows, indent=2), encoding="utf-8")

build_lines = ["# BuildCore Root Causes", ""]
for r in build_fail_rows:
    b = r["build"]
    build_lines += [
        f"## {r['repo']}",
        f"- failure_type: {b['build_failure_type']}",
        f"- ownership: {b['build_ownership']}",
        f"- command: {' '.join(b['cmd'])}",
        f"- exit_code: {b['exit_code']}",
        f"- working_directory: {b['cwd']}",
        f"- buildcore_invocation: {b['invocation']}",
        f"- first_failing_node: {b['first_failing_node']}",
    ]
    for ln in b["key_lines"][:6]:
        build_lines.append(f"- evidence: {ln}")
    build_lines.append("")

(packet / "40_buildcore_root_causes.md").write_text("\n".join(build_lines) + "\n", encoding="utf-8")

src_lines = ["# Source Matching Root Causes", ""]
for r in source_fail_rows:
    c = r["configure"]
    src_lines += [
        f"## {r['repo']}",
        f"- failure_type: {c['source_failure_type']}",
        f"- ownership: {c['source_ownership']}",
        f"- command: {' '.join(c['cmd'])}",
        f"- exit_code: {c['exit_code']}",
        f"- plan_path: {c['plan_path']}",
        f"- plan_snippet: {c['plan_snippet']}",
    ]
    for ln in c["key_lines"][:6]:
        src_lines.append(f"- evidence: {ln}")
    src_lines.append("")

(packet / "41_sources_root_causes.md").write_text("\n".join(src_lines) + "\n", encoding="utf-8")

ecosystem = []
repo_issues = []
env_issues = []

for r in build_fail_rows:
    t = r["build"]["build_failure_type"]
    if t in {"INVALID_PLAN_STRUCTURE", "WORKDIR_ERROR"}:
        ecosystem.append((r["repo"], t, "H"))
    elif t in {"TOOLCHAIN_MISSING", "PATH_RESOLUTION_ERROR", "PERMISSION_OR_LOCK_ISSUE"}:
        env_issues.append((r["repo"], t, "M"))
    else:
        repo_issues.append((r["repo"], t, "M"))

for r in source_fail_rows:
    t = r["configure"]["source_failure_type"]
    if t == "BAD_GLOB_OR_TARGET_CONFIG":
        repo_issues.append((r["repo"], t, "L"))

plan = ["# Minimal Fix Plan", "", "## Ecosystem fixes", ""]
if ecosystem:
    for repo, cause, risk in ecosystem:
        plan.append(f"- repo: {repo} | root_cause: {cause} | smallest_fix: targeted CLI/graph/buildcore contract patch only where evidenced | risk: {risk}")
else:
    plan.append("- none identified as clear ecosystem root cause in this pass")

plan += ["", "## Repo fixes", ""]
if repo_issues:
    for repo, cause, risk in repo_issues:
        if cause == "BAD_GLOB_OR_TARGET_CONFIG":
            fix = "adjust src_glob/target mapping in ngksgraph.toml to match actual source layout"
        elif cause == "SUBPROCESS_FAILURE":
            fix = "inspect repo-specific build node command/tool args from pipeline_build_run and correct repo config inputs"
        else:
            fix = "apply smallest repo-local config correction tied to failing node"
        plan.append(f"- repo: {repo} | root_cause: {cause} | smallest_fix: {fix} | risk: {risk}")
else:
    plan.append("- none")

plan += ["", "## Environment requirements", ""]
if env_issues:
    for repo, cause, risk in env_issues:
        plan.append(f"- repo: {repo} | root_cause: {cause} | smallest_fix: install/configure missing toolchain component in environment | risk: {risk}")
else:
    plan.append("- none explicitly missing in captured logs; verify compiler/Qt availability if BuildCore subprocess failure persists")

(packet / "50_minimal_fix_plan.md").write_text("\n".join(plan) + "\n", encoding="utf-8")

summary = {
    "repos_analyzed": len(repos),
    "buildcore_failures": len(build_fail_rows),
    "source_match_failures": len(source_fail_rows),
    "ecosystem_issues": len(ecosystem),
    "repo_issues": len(repo_issues),
    "environment_issues": len(env_issues),
}
(packet / "60_triage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("packet", packet)
print(json.dumps(summary, indent=2))
