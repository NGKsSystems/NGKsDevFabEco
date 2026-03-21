# NGKsGraph Codebase Analysis
**Scope:** Target discovery, multi-target support, test auto-discovery, configure command behavior, and plan generation  
**Analysis Date:** March 21, 2026

---

## Executive Summary

NGKsGraph uses **primarily declarative TOML configuration** for target specification, with optional filesystem scanning during the `init` subcommand. It **fully supports multi-target projects** via `[[targets]]` TOML arrays. The `configure` command reads the config file, expands glob patterns, validates contracts, and generates a deterministic build plan. **Test target auto-discovery is not automatic** during configure, but the `init` command can detect test patterns and suggest configurations.

---

## 1. Target Discovery Mechanism

### 1.1 Primary Discovery: Declarative Configuration (Not Automatic Scanning)

**Key Finding:** NGKsGraph does **NOT** perform automatic filesystem scanning during the `configure` command. All target definitions come from explicit TOML declarations.

#### How It Works:

1. **Configuration Phase (`configure` command):**
   - Reads `ngksgraph.toml` via `load_config()` ([config.py lines 345–450](ngksgraph/config.py#L345))
   - Parses target definitions from `[[targets]]` array sections OR legacy top-level fields
   - Normalizes configuration (validate, deduplicate, sort)
   
2. **Source Discovery Phase:**
   - Calls `scan_sources_by_target()` ([scan.py](ngksgraph/scan.py)) to expand `src_glob` patterns
   - **Pattern Expansion:** `src_glob: ["src/**/*.cpp", "src/**/*.c"]` → glob patterns matched against filesystem
   - Returns `dict[target_name] -> list[discovered_source_files]`
   - Only `.cpp` and `.c` files are accepted (hardcoded suffix filters in scan.py)

3. **Graph Construction:**
   - Calls `build_graph_from_project()` ([graph.py lines 140–305](ngksgraph/graph.py#L140))
   - Creates Target objects with discovered sources + TOML metadata (libs, flags, etc.)
   - Validates graph integrity (no cycles, all edge references valid)
   - Outputs BuildGraph structure

#### Key Point:
- **Declarative first:** Targets must be declared in TOML
- **Glob-based discovery:** Individual source files within declared globs are discovered
- **No implicit target detection:** No automatic `.cpp` → target mapping

---

### 1.2 Alternative: Automatic Init (One-Time Setup)

The `init` subcommand (**not `configure`**) performs filesystem scanning to generate an initial `ngksgraph.toml`:

**Process:**
- Scans repo for source files and structural patterns
- Uses `repo_classifier.py` to detect repo family:
  - `native-single-target`: Single main.cpp + sources → single exe target
  - `engine-multi-target`: `engine/` + `apps/*/main.cpp` → multi-target graph
  - `qt-app`: Detects Qt UI patterns, enables Qt support
  - `flutter-app`, `juce-app`: Framework-specific patterns
- Auto-detects test patterns (indirectly, see Section 3)
- Writes suggested `ngksgraph.toml` 

**Important:** `init` only runs **once** to create the config. After that, all discovery is manual (via TOML edits).

---

## 2. Multi-Target Support

### 2.1 Fully Supported: `[[targets]]` Array in TOML

**YES** — NGKsGraph has first-class multi-target support via TOML array syntax.

#### Example Multi-Target Config:
```toml
[build]
default_target = "app"

[[targets]]
name = "core"
type = "staticlib"
src_glob = ["src/core/**/*.cpp"]
include_dirs = ["src/core"]
libs = []
links = []

[[targets]]
name = "app"
type = "exe"
src_glob = ["src/app/**/*.cpp"]
include_dirs = ["src/core"]
libs = ["user32"]
links = ["core"]  # Depends on 'core' target
```

See template: [templates/multi_target_ngksgraph.toml](templates/multi_target_ngksgraph.toml)

#### Key Features:

1. **Target Declaration via `[[targets]]` Array:**
   - Each target has URL-style name, type (exe/staticlib), source glob, include dirs, libs
   - Type checked: `TargetConfig.type` must be `"exe"` or `"staticlib"`
   - Unlimited number of targets supported

2. **Backward-Compat: Legacy Single-Target Format Still Works:**
   ```toml
   name = "myapp"
   target_type = "exe"
   src_glob = ["src/**/*.cpp"]
   ```
   - No `[[targets]]` section → config normalization auto-creates a single implicit target
   - See [config.py lines 155–165](ngksgraph/config.py#L155) for this conversion

3. **Linking Between Targets:**
   - Each target has a `links: [...]` array field
   - Declares dependencies on other targets (must exist)
   - BuildGraph validates: all `links` references must resolve to another target
   - Duplicate target names are rejected ([config.py line 173](ngksgraph/config.py#L173))

4. **Build Order & Dependency Resolution:**
   - Graph uses topological sort: `BuildGraph.build_order()` ([graph.py lines 99–117](ngksgraph/graph.py#L99))
   - Cycle detection: raises if circular dependency detected
   - Link closure: computes transitive deps for a target

5. **Profile Overlay:**
   - Profiles (debug/release) apply flags uniformly to all targets
   - See [config.py lines 243–259](ngksgraph/config.py#L243): profile flags are added to each target's cflags/defines/ldflags

### 2.2 Config Structure: TargetConfig Class

```python
@dataclass
class TargetConfig:
    name: str           # Unique target identifier
    type: str           # "exe" or "staticlib"
    src_glob: list[str] # Glob patterns: ["src/**/*.cpp", ...]
    include_dirs: list[str]
    defines: list[str]
    cflags: list[str]
    libs: list[str]     # External libs (e.g., ["user32", "Qt6Core"])
    lib_dirs: list[str]
    ldflags: list[str]
    cxx_std: int        # C++ standard (e.g., 20)
    links: list[str]    # Dependencies on OTHER targets (e.g., ["core"])
```

See [config.py lines 68–89](ngksgraph/config.py#L68).

---

## 3. Test Target Auto-Discovery

### 3.1 Status: NO Automatic Test Discovery During Configure

**Test targets are NOT auto-discovered** during the `configure` command. No special naming conventions are recognized.

### 3.2 Init Command Can Suggest Tests (Indirect)

The `init` subcommand detects certain repo patterns that *imply* tests exist:

#### Detected Patterns:
1. **Engine-Multi-Target Family:**
   - Presence of `engine/` directory
   - Presence of `apps/*/main.cpp`
   - Suggests app-layer test targets
   - **Not automatic:** User must edit TOML to add test targets

2. **Visual Signals (Detected but Not Acted Upon):**
   - File names like `*_tests.cpp`, `*_unit.cpp` → counted but not auto-configured
   - QtTest framework patterns (detected via `#include <QtTest>`)
   - JUCE testing patterns
   - Counted in `RepoClassification.qt_signal_count` etc., but not converted to targets

3. **Example: repo_classifier.py Signals for Tests**
   - Scans for Qt includes: `#include <QtTest>`, `Q_OBJECT`, etc.
   - Counts JUCE signals, Flutter indicators
   - Outputs `RepoClassification` with signal counts
   - **BUT:** No automatic target generation based on signals

#### To Enable Tests:

Users must manually add target sections to `ngksgraph.toml`:
```toml
[[targets]]
name = "core_tests"
type = "exe"
src_glob = ["tests/core/**/*.cpp"]
include_dirs = ["src/core", "tests/core"]
libs = ["Qt6Test"]
links = ["core"]  # Link against main library

[[targets]]
name = "app_tests"
type = "exe"
src_glob = ["tests/app/**/*.cpp"]
include_dirs = ["src/app", "tests/app"]
links = ["app"]
```

---

## 4. The `configure` Command: What Gets Read/Scanned

### 4.1 Overview

The `configure` command is the main entry point for building. It orchestrates:
1. Config loading
2. Source scanning
3. Qt integration detection
4. Graph building
5. Caching
6. Contract validation
7. Plan generation

See [build.py lines 603–900+](ngksgraph/build.py#L603).

### 4.2 Step-by-Step Flow

```
configure_project(repo_root, config_path, msvc_auto, target, profile, no_cache, clear_cache)
  ↓
1. load_config(config_path) → Config object
   - Reads ngksgraph.toml
   - Parses [[targets]] array or legacy fields
   - Returns Config with all target definitions
   ↓
2. Check cache (fingerprint-based):
   - Compute source file fingerprint from config + discovered sources
   - Compare against cached fingerprint
   - If cache hit: skip to step 5 (use cached plan)
   ↓
3. scan_sources_by_target(repo_root, config) → dict[target_name] → list[sources]
   - For each target, expand src_glob against filesystem
   - Only .cpp / .c files accepted
   - Returns dict mapping target to discovered sources
   ↓
4. integrate_qt(repo_root, config, source_map, out_dir)
   - Detects Qt via moc/uic/rcc paths in config
   - Scans sources for #include <Q*>
   - Generates Qt metadata if enabled
   ↓
5. build_graph_from_project(config, source_map, msvc_auto) → BuildGraph
   - Creates Target objects with sources + TOML metadata
   - Validates: no cycles, all refs valid
   - Computes build order (topological sort)
   ↓
6. _generate_artifacts(repo_root, config, source_map, paths, msvc_auto, qt_result)
   - Builds compile commands (compdb)
   - Emits build plan (ngksgraph_plan.json)
   - Validates contracts: compdb_contract, graph_contract
   ↓
7. _write_snapshot(...)
   - Writes snapshot JSON with build metadata
   ↓
8. Return configured dictionary:
   {
     "ok": True,
     "config": Config,
     "profile": profile_name,
     "source_map": dict[target_name] -> list[sources],
     "graph": BuildGraph,
     "graph_payload": dict (JSON-serializable graph),
     "compdb": list[compile_command],
     "snapshot_info": {...},
     "paths": {...},
     "cache_hit": bool,
     "durations": {...}
   }
```

### 4.3 What Gets Read from Filesystem

**Only What's in `src_glob` Patterns:**
- `src_glob: ["src/**/*.cpp", "src/**/*.c"]` → files matching glob
- Extensions limited to `.cpp`, `.c` (hardcoded in scan.py)
- Ignored directories: `.git`, `.venv`, `build`, `dist`, `_proof`, `_artifacts`, `third_party`, `node_modules`

**NOT auto-scanned:**
- No automatic discovery of unmentioned directories
- No implicit test detection
- No header-only libraries (unless in src_glob)

---

## 5. Plan Generation & ngksgraph_plan.json

### 5.1 What Feeds Into the Plan

The **BuildGraph + config metadata** is converted into the build plan:

**Inputs:**
- `BuildGraph.targets` — all Target objects with sources, flags, libs
- `BuildGraph.edges` — dependency relationships
- Selected `profile` (debug/release) — applies overlay flags
- Qt integration results (if enabled)

**Process:**
- `emit_build_plan()` ([plan/__init__.py](ngksgraph/plan/__init__.py)) iterates over each target
- For each source file in target: generates a **compile step**
- For each target: generates a **link step**
- Steps are deterministically ordered and hashed

### 5.2 Plan Structure Example

```json
{
  "repo_root": "/path/to/repo",
  "profile": "debug",
  "targets": [
    {
      "name": "core",
      "kind": "staticlib",
      "sources": ["src/core/lib.cpp"],
      "steps": [
        {
          "kind": "compile",
          "id": "compile_abc123",
          "inputs": ["src/core/lib.cpp"],
          "outputs": ["build/debug/obj/core/src/core/lib.obj"],
          "defines": ["DEBUG"],
          "include_dirs": ["src/core"],
          "cflags": ["/Od", "/Zi"],
          "libs": [],
          "toolchain": "cl/link"
        },
        {
          "kind": "link",
          "id": "link_def456",
          "inputs": ["build/debug/obj/core/src/core/lib.obj"],
          "outputs": ["build/debug/lib/core.lib"],
          "libs": [],
          "toolchain": "cl/link"
        }
      ]
    },
    {
      "name": "app",
      "kind": "exe",
      "sources": ["src/app/main.cpp"],
      "steps": [
        {
          "kind": "compile",
          "inputs": ["src/app/main.cpp"],
          "outputs": ["build/debug/obj/app/src/app/main.obj"],
          "defines": ["DEBUG"],
          "libs": ["user32"],
          "depends_on": ["core"]  # Link-time dependency
        },
        {
          "kind": "link",
          "inputs": ["build/debug/obj/app/src/app/main.obj", "build/debug/lib/core.lib"],
          "outputs": ["build/debug/bin/app.exe"]
        }
      ]
    }
  ],
  "generated_at": "2026-03-21T12:34:56Z",
  "schema_version": "1.0"
}
```

### 5.3 Determinism & Hashing

- **Path normalization:** All paths use `/` separator (Windows: `C:/path/to/file`)
- **Sort order:** Sources and steps sorted lexicographically
- **Hash calculation:** `_step_fingerprint()` hashes step inputs/outputs/defines/flags
- **Excludes:** Timestamps (`generated_at`) and specific build machine details

See [plan/__init__.py lines 41–70](ngksgraph/plan/__init__.py#L41).

### 5.4 Output Location

```
build/
  <profile>/
    ngksgraph_plan.json       ← Main build plan (deterministic, human-readable)
    ngksgraph.lock.json       ← Cache lock (check if plan is fresh)
    compile_commands.json     ← compdb format (for IDE integration)
    graph.json                ← BuildGraph JSON representation
    snapshot/
      <timestamp>/            ← Timestamped configuration snapshot
        config.json
        plan.json
        build_report.json
```

---

## 6. Key Source Files

| File | Purpose | Key Functions |
|------|---------|---|
| [config.py](ngksgraph/config.py) | TOML parsing, Config/TargetConfig dataclasses | `load_config()`, `TargetConfig.normalize()` |
| [scan.py](ngksgraph/scan.py) | Glob expansion, source discovery | `scan_target_sources()`, `scan_sources_by_target()` |
| [graph.py](ngksgraph/graph.py) | BuildGraph construction, validation, topological sort | `build_graph_from_project()`, `BuildGraph.build_order()` |
| [build.py](ngksgraph/build.py) | Orchestrates configure, caching, plan emission | `configure_project()`, `emit_build_plan()` |
| [plan/__init__.py](ngksgraph/plan/__init__.py) | Build plan serialization, deterministic hashing | `emit_build_plan()`, `_step_fingerprint()` |
| [repo_classifier.py](ngksgraph/repo_classifier.py) | Repo family detection (used by `init` command) | `classify_repo()`, `synthesize_init_toml()` |
| [targetspec/canonical_target_spec.py](ngksgraph/targetspec/canonical_target_spec.py) | Target capability mapping | `derive_canonical_target_spec()` |
| [cli.py](ngksgraph/cli.py) | Command-line interface | `main()`, subcommand routing |

---

## 7. Summary: How Multi-Targets Flow Through the System

```
ngksgraph.toml (TOML declaration)
  ↓
load_config() → Config(targets=[TargetConfig, TargetConfig, ...])
  ↓
scan_sources_by_target() → {
  "core": ["src/core/lib.cpp"],
  "app": ["src/app/main.cpp"]
}
  ↓
build_graph_from_project() → BuildGraph(
  targets={
    "core": Target(name="core", type="staticlib", ...),
    "app": Target(name="app", type="exe", links=["core"], ...)
  },
  edges=[
    Edge(frm="app", to="core", type="links_to")
  ]
)
  ↓
build_order() → ["core", "app"]  (topological sort)
  ↓
emit_build_plan() → ngksgraph_plan.json (contains all compile + link steps)
```

---

## 8. Key Distinctions

| Aspect | Answer |
|--------|--------|
| **Auto-discovery on `configure`?** | NO — purely declarative TOML-driven |
| **Multi-target TOML support?** | YES — `[[targets]]` array with unlimited entries |
| **Multi-target in plan?** | YES — separate steps/outputs per target, respects link deps |
| **Auto-test detection?** | NO during configure. YES during `init` (only suggests, doesn't auto-add) |
| **Config reads filesystem?** | Only to expand src_glob patterns; no structural scanning |
| **Plan is deterministic?** | YES — normalized paths, sorted, content-hashed |

---

## 9. Examples & Testing

### Example 1: Simple Single-Target (Backward-Compat)
```toml
name = "myapp"
target_type = "exe"
src_glob = ["src/**/*.cpp"]
cxx_std = 20
```
→ Normalized to one implicit target, scanned, built.

### Example 2: Multi-Target (Modern)
```toml
[[targets]]
name = "core"
type = "staticlib"
src_glob = ["lib/**/*.cpp"]

[[targets]]
name = "app"
type = "exe"
src_glob = ["app/**/*.cpp"]
links = ["core"]

[build]
default_target = "app"
```
→ Two targets, dependency graph, plan respects link order.

### Example 3: With Test Target (Manual)
```toml
[[targets]]
name = "lib"
type = "staticlib"
src_glob = ["src/**/*.cpp"]

[[targets]]
name = "lib_tests"
type = "exe"
src_glob = ["tests/**/*.cpp"]
libs = ["Qt6Test"]
links = ["lib"]

[build]
default_target = "lib"
```
→ Both targets built; user chooses which to execute.

---

## Appendix: Test Coverage

Tests for multi-target and discovery:
- [tests/test_init_repo_classifier.py](tests/test_init_repo_classifier.py):
  - `test_init_autodetects_engine_multi_target_and_prefers_widget_sandbox`
  - `test_init_autodetects_qt_when_ui_and_qobject_signals_present`
- [tests/](tests/) — Additional config/graph/scan tests assert multi-target behavior

