# NGKsDevFabEco — Workspace Instructions for GitHub Copilot

## What This System Is

**NGKsDevFabEco** is a custom deterministic build intelligence fabric for Windows/MSVC/Qt C++ development. It is **not** CMake, MSBuild, or Ninja. It is a Python-based ecosystem that controls the entire lifecycle: environment locking → plan generation → compilation → proof/audit artifacts.

All C++ projects in `C:\Users\suppo\Desktop\NGKsSystems\` that have an `ngksgraph.toml` use this system.

---

## Module Hierarchy (Chain of Custody)

```
NGKsEnvCapsule  →  environment resolution & locking
NGKsGraph       →  source scanning, build intent, plan generation
NGKsBuildCore   →  DAG execution (actual compilation)
NGKsDevFabric   →  certification gates, risk prediction, workflow orchestration
NGKsLibrary     →  reporting, SUMMARY.md, proof indexes
```

Each step feeds the next. All produce proof artifacts under `_proof/`.

---

## Installed Package Versions

| Location | ngksgraph | ngksbuildcore | ngksdevfabric | Note |
|---|---|---|---|---|
| DevFabEco/.venv | 0.2.1 (**editable**) | 0.2.0 (editable) | 1.3.4 | Source lives in `NGKsGraph/` and `NGKsBuildCore/` |
| Project venvs (most) | 0.2.1 (wheel) | 0.2.0 (wheel) | 1.3.4 | Fixed installed wheels |
| OfficeSuiteCpp/.venv | 0.2.2 (wheel) | 0.2.1 (wheel) | 1.3.4 | Slightly newer wheels |

**DevFabEco is the source of truth.** Changes to `NGKsGraph/ngksgraph/` and `NGKsBuildCore/ngksbuildcore/` are live in the DevFabEco venv but must be packaged and reinstalled into project venvs to take effect there.

---

## The Critical Build Bypass: `NGKS_ALLOW_DIRECT_BUILDCORE`

Project venvs contain `ngksbuildcore` 0.2.0 which **intercepts all `ngksbuildcore run` calls** and delegates to the ngksdevfabric orchestrator (`ngksdevfabric build <project_root>`). That orchestrator runs only certification bootstrap — it does **not** compile anything.

**Always set this env var before building:**
```powershell
$env:NGKS_ALLOW_DIRECT_BUILDCORE = "1"
```

Or in a batch file:
```batch
set NGKS_ALLOW_DIRECT_BUILDCORE=1
```

Without this flag, `ngksbuildcore run` silently exits 0 and produces no binary.

---

## Canonical Build Sequence for C++ Projects

```batch
@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" > nul 2>&1
cd /d <PROJECT_ROOT>
call .venv\Scripts\activate.bat
set NGKS_ALLOW_DIRECT_BUILDCORE=1

:: Step 1: Generate the buildcore plan
python -m ngksgraph build --profile debug --target <TARGET_NAME>

:: Step 2: Execute the plan (compile + link + windeployqt)
python -m ngksbuildcore run --plan build_graph\debug\ngksbuildcore_plan.json
```

- `ngksgraph build` generates `build_graph/<profile>/ngksbuildcore_plan.json` (does NOT compile)
- `ngksbuildcore run` executes the DAG (compile → link → windeployqt)
- Binary output: `build/<profile>/bin/<TARGET_NAME>.exe`

Proof artifacts go to `_proof/run_<timestamp>.zip`.

---

## ngksgraph.toml — Inheritance Rules (Critical)

Global-level keys (`cflags`, `include_dirs`, `defines`, `ldflags`) in `ngksgraph.toml` are **defaults** that `[[targets]]` can inherit from. However, if a `[[targets]]` block explicitly sets these to `[]`, the global values are **silently dropped** in older installed wheels (≤ 0.2.1).

### Rules for Target Sections
- If `include_dirs = []` in a target → project-local dirs like `src/` are NOT added. Always set `include_dirs = ["src"]` explicitly if source files use relative includes.
- If `cflags = []` in a target → global cflags including `/Zc:__cplusplus` are NOT included. Always set required flags explicitly.
- Profile cflags (`[profiles.debug]`) are merged **on top of** target cflags during `apply_profile`.

### Minimum required cflags for Qt 6 on MSVC
```toml
cflags = ["/Zc:__cplusplus", "/permissive-"]
```

Qt 6 hard-requires `/Zc:__cplusplus` for `__cplusplus` to report the correct value. Without it, Qt headers emit `fatal error C1189: #error: "Qt requires a C++17 compiler..."` regardless of `/std:c++20`.

### apply_profile inheritance fix (DevFabEco source)
`NGKsGraph/ngksgraph/config.py` `apply_profile()` was patched to prepend global cflags/defines/ldflags before target + profile values. Earlier installed wheel versions do NOT have this fix; downstream projects need explicit target-level flags.

---

## Qt Build Details

| Item | Value |
|---|---|
| Qt Root | `C:/Qt/6.10.2/msvc2022_64` |
| moc.exe | `C:/Qt/6.10.2/msvc2022_64/bin/moc.exe` |
| windeployqt.exe | `C:/Qt/6.10.2/msvc2022_64/bin/windeployqt.exe` |
| moc-generated files | Pre-generated into `build/<profile>/qt/` before plan execution |
| Qt include base | `C:/Qt/6.10.2/msvc2022_64/include` |

The build plan compiles moc-generated `moc_*.cpp` files directly — they are expected to exist in `build/<profile>/qt/` before compilation starts.

### windeployqt flags
- Apps with QML: `windeployqt --qmldir <qml_src_dir> <exe>`
- Widgets-only apps (no QML): `windeployqt <exe>` (no `--qmldir`)
- Always add `--compiler-runtime` to bundle VC++ runtime
- Debug builds add `--debug`; release builds add `--release`

These flags are configured via `ngksgraph.toml` under `[qt]`:
```toml
[qt]
windeployqt_qmldir = "src/qml"   # omit or leave empty for widgets-only
```

---

## MSVC Compiler

```
C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat
```

**Required before any compilation.** ngksbuildcore does NOT auto-invoke vcvars — the calling environment must already have MSVC paths.

---

## Project Structure Pattern

```
<ProjectName>/
  .venv/                          ← Project's own Python venv
  src/                            ← C++ source tree
  build/<profile>/bin/            ← Compiled binaries
  build/<profile>/obj/            ← Object files
  build/<profile>/qt/             ← moc/uic/rcc generated files
  build_graph/<profile>/
    ngksbuildcore_plan.json       ← Execution plan (generated by ngksgraph build)
    ngksgraph_plan.json           ← NGKsGraph-format plan (intermediate)
  _proof/                         ← Proof artifacts (ZIP per run)
  ngksgraph.toml                  ← Build configuration (source of truth)
```

---

## DevFabEco Development (Editable Source)

The `NGKsDevFabEco` workspace contains the live source for:
- `NGKsGraph/` → `ngksgraph` package (editable installed into `.venv`)
- `NGKsBuildCore/` → `ngksbuildcore` package (editable installed into `.venv`)
- `NGKsDevFabric/` → (non-editable wheel in DevFabEco.venv)
- `NGKsEnvCapsule/` → (non-editable wheel)

**To test changes**: run from `NGKsDevFabEco/.venv` — changes to source are immediately live.

**To push changes to a project venv**: rebuild the wheel and `pip install` into the project's `.venv`.

Tests run from `_validation_venv/` using pytest. Key test locations:
- `NGKsGraph/tests/`
- `NGKsBuildCore/tests/`

---

## Known Issues / Important Quirks

1. **`ngksbuildcore run` is intercepted** without `NGKS_ALLOW_DIRECT_BUILDCORE=1`. Always set it.
2. **Qt 6 requires `/Zc:__cplusplus`** — must be in target `cflags` if the target has `cflags = [...]`.
3. **`include_dirs = []` drops globals** — explicit `include_dirs = ["src"]` needed when relative headers cross directory boundaries.
4. **`ngksgraph build` only generates the plan** — it does NOT compile. Must follow with `ngksbuildcore run`.
5. **`ngksgraph plan` generates `ngksgraph_plan.json`** — NOT the buildcore plan. Use `ngksgraph build` or `ngksgraph buildplan` for the buildcore-compatible JSON.
6. **`ngksdevfabric build` in ecosystem mode** calls `ngksdevfabric run --mode ecosystem` which does certification only, not compilation.
7. **moc files must exist before compilation** — `build/<profile>/qt/moc_*.cpp` are pre-generated (by a separate moc step or previous run). If missing, compilation of moc-dependent TUs fails.
8. **vcvars64.bat must be called first** — ngksbuildcore does not auto-detect MSVC.
9. **Semantic Qt versions** (`"6.9.9"`) in `ngksgraph.toml` are normalized to the major version integer. No crash; a note is emitted to stderr.
10. **`python -m ngksdevfabric.cli` does not work** — use `python -m ngksdevfabric` or the installed entry script.

---

## Proof Artifacts

Every run produces a timestamped ZIP at `_proof/run_<timestamp>.zip` containing:
- `events.jsonl` — every action taken
- `commands.jsonl` — raw commands executed  
- `environment.txt` — env snapshot
- `git_status.txt`, `git_head.txt` — repo state
- `tool_versions.txt` — compiler/tool versions
- `pipeline_summary.md` — human-readable summary

---

## Key File Locations

| File | Purpose |
|---|---|
| `NGKsGraph/ngksgraph/config.py` | Config parsing, apply_profile, target inheritance |
| `NGKsGraph/ngksgraph/compdb.py` | build_compile_command (MSVC flags) |
| `NGKsGraph/ngksgraph/plan/__init__.py` | buildcore plan generation, windeployqt command |
| `NGKsGraph/ngksgraph/graph.py` | BuildGraph, Target model, toolchain |
| `NGKsBuildCore/ngksbuildcore/cli.py` | NGKS_ALLOW_DIRECT_BUILDCORE gate, interception |
| `NGKsDevFabric/` | Certification, risk prediction, workflows |
| `NGKsEnvCapsule/` | Environment resolution and lock |

---

## All C++ Projects Using This System

Located at `C:\Users\suppo\Desktop\NGKsSystems\`:
- `NGKsFileVisionary` — Qt6 Widgets file manager (cxx_std=20)
- `NGKsPlayerNative` — Qt6 media player
- `NGKsMailcpp` — Qt6 mail client
- `NGKsMediaLab` — Qt6 media processing
- `OfficeSuiteCpp` — Qt6 office suite (WordApp sub-target)
- `OfficeSuiteCppPresentation` — Qt6 presentation app
- `CreatorNexus` — Qt6 app
- `NGKs_Content_Curator` — Qt6 app
- `NGKsUI Runtime` — Qt6 UI runtime
