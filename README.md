# NGKsDevFabEco

**The Deterministic Developer OS**

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Platform-Windows-blue)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

A production-ready **build intelligence fabric** that turns complex software projects — especially C++/MSVC, Qt, and monorepos — into a fully deterministic, reproducible, auditable, and forensically transparent “operating system” for developers.

---

## Overview

**NGKsDevFabEco (v1.2.0)** is a modular Python CLI ecosystem that provides end-to-end deterministic build intelligence:

- Scans source trees and detects **60+ languages**, frameworks, and build systems
- Builds stable dependency graphs with temporal intelligence
- Generates executable JSON DAG plans
- Executes builds with immutable proof artifacts
- Creates portable **reproducibility capsules**
- Performs deep forensic analysis (“why did this rebuild?”)
- Enforces certification gates with risk prediction and audit ledgers

It is MSVC-native and especially powerful for Windows C++ development involving Qt, JUCE, CMake, and large mixed-language monorepos.

---

## Core Philosophy

- **Determinism First** — Stable ordering, hash-based change detection, no surprises
- **Reproducibility** — Portable capsules + environment lockfiles
- **Forensics & Auditability** — Complete proof ledger (events, commands, env snapshots, git state)
- **Certification** — Immutable evidence for gates and compliance
- **Fail-Closed** — Never guess; always explain

---

## Scope & Chain Of Custody (Critical)

NGKsDevFabEco is the authoritative execution chain for this ecosystem:

1. **NGKsEnvCapsule** resolves and locks environment state
2. **NGKsGraph** detects and plans deterministic build intent
3. **NGKsBuildCore** executes the approved DAG
4. **NGKsLibrary / NGKsDevFabric** assemble proof and enforce certification policy

The chain of custody is valid only when this chain is preserved end-to-end.

**Important:** detection of external tools (for example `build.ninja`, CMake cache files, or foreign generated metadata) does **not** make those tools authoritative. They are treated as foreign context unless explicitly imported under policy.

If a downstream repository replaces NGKsBuildCore execution with external executors (Ninja, ad-hoc scripts, direct CMake driver runs, etc.), that run is out-of-contract and should be treated as **chain-of-custody broken** for DevFabEco certification and audit claims.

---

## Modules

| Module              | Role                                   | Key Capabilities |
|---------------------|----------------------------------------|------------------|
| **NGKsGraph**       | Intelligence & Planning Engine        | Source scanning, graph analysis, requirement inference, forensics (`why`, `explain`, `trace`, `diff`, `rebuild-cause`), Qt moc/uic/rcc handling |
| **NGKsBuildCore**   | Deterministic Executor                | DAG execution, parallel builds, proof artifact collection |
| **NGKsEnvCapsule**  | Environment Management                | `doctor`, `resolve`, `lock`, `verify`, deterministic env freezing |
| **NGKsLibrary**     | Reporting & Documentation             | SUMMARY.md, proof indexes, audit reports |
| **NGKsDevFabric**   | Certification & Workflows             | Certification gates, risk prediction, plan validation |

All modules share a unified proof directory system and JSON contracts.

---

## Supported Languages & Ecosystems (60+)

**Compiled**: C, C++, Rust, Go, Zig, D, Nim, Fortran, Ada, Assembly  
**Managed**: C#, Java, Kotlin, Scala, Visual Basic .NET, F#  
**Web & Runtime**: JavaScript, TypeScript, PHP, Ruby, Elixir, Erlang  
**Scripting**: Python, Lua, Perl, PowerShell, Bash  
**Data & Scientific**: R, MATLAB, Julia  
**Mobile & Game**: GDScript, Unity, Unreal Engine markers, Flutter  

**Build Systems Detected**: CMake, MSBuild, Ninja, Gradle, Maven, Bazel, Meson, QMake, etc.  
Detection is for intelligence and compatibility analysis. Detection alone does not grant execution authority inside the DevFabEco proof chain.
**Frameworks**: Qt5/Qt6 (full moc/uic/rcc support), JUCE, Electron, PySide6, Django, React.

---

## Installation

### Recommended (Windows)

```powershell
# Clone the repo
git clone https://github.com/NGKsSystems/NGKsDevFabEco.git
cd NGKsDevFabEco

# Run the official installer (creates .venv by default, full proof logging)
.\install_ngksdevfabeco.ps1
```

If you run `-UserInstall` outside a virtual environment, the installer prompts:

`You are not in a virtual environment. Create and activate .venv now? [Y/N]`

After installation:

- Activate venv: `.\.venv\Scripts\Activate.ps1`
- Or use `-UserInstall` for PATH-wide install

### Alternative (pip)

```powershell
pip install ngksdevfabeco
```

---

## Authoritative Workflow (Chain-Of-Custody Safe)

Use this sequence when you need DevFabEco certification-grade traceability:

```powershell
# 1) Initialize and detect project intent
ngksgraph init
ngksgraph configure --profile debug

# 2) Lock and verify environment state
ngksenvcapsule resolve
ngksenvcapsule lock
ngksenvcapsule verify

# 3) Execute approved deterministic plan
ngksgraph build --profile debug --msvc-auto

# 4) Perform forensic checks
ngksgraph why build\debug\bin\app.exe --profile debug
ngksgraph rebuild-cause build\debug\bin\app.exe --profile debug
ngksgraph trace src\main.cpp --profile debug

# 5) Generate certification artifacts
ngksdevfabric certify-gate
ngksdevfabric predict-risk
```

### Out-Of-Contract Patterns

The following patterns break DevFabEco chain-of-custody claims for certification/audit:

- Replacing `ngksbuildcore run` with direct Ninja execution
- Running ad-hoc external build scripts outside declared DevFabEco orchestration
- Treating foreign generated artifacts (`build.ninja`, cache files, stale compdb) as authoritative execution inputs

---

## Quick Start (General)

```powershell
# 1. Initialize a project
ngksgraph init

# 2. Scan and configure
ngksgraph configure --profile debug

# 3. Build with full determinism
ngksgraph build --profile debug --msvc-auto

# 4. Create reproducible capsule
ngksgraph freeze --profile debug
```

Useful help commands:

- `ngksgraph --help`
- `ngksenvcapsule --help`
- `ngksdevfabric --help`

---

## Key CLI Commands

### NGKsGraph (main intelligence tool)

`init` • `scan` • `configure` • `build` • `plan` • `explain`  
`why` • `rebuild-cause` • `diff` • `trace` • `freeze` • `thaw`  
`doctor` • `clean` • `graph`

### NGKsEnvCapsule

`doctor` • `resolve` • `lock` • `verify`

### NGKsDevFabric (certification and workflows)

`certify` • `certify-gate` • `certify-target-check`  
`predict-risk` • `plan-validation` • `run-validation-and-certify`

### Other

`ngksbuildcore run` • `ngkslibrary assemble`

---

## Unique Value

- Reproducibility Capsules: freeze entire build state (ZIP + hashes) and thaw anywhere
- Build Forensics: deep "why" analysis and rebuild classification
- Certification Ledger: immutable proof artifacts for every run
- MSVC Auto-Discovery: automatic Visual Studio environment bootstrapping
- Proof Artifacts: `events.jsonl`, `commands.jsonl`, `environment.txt`, `git_status.txt`, `tool_versions.txt`, and more

Every operation is logged with full audit trail for CI/CD and compliance.

---

## Roadmap (Post-v1.2.0)

Next milestone:

- Full transport/delivery layer (GitHub, Jira, webhooks, email)

Deferred (see `DEFERRED_ITEMS.md`):

- Dashboard UX
- Proof-root cleanup and retention policy
- Organization/team ownership mapping
- Dry-run vs live-send policies

---

## Project Status

- Phase: wiring and stabilization complete (39 requirements validated)
- Platform: Windows-first (MSVC native)
- Testing: extensive (fixtures + validation suite)
- Releases: meta-package ready (dist folders present)

---

## Documentation

- `NGKsDevFabEco_Comprehensive_Capabilities_Document.md`
- `certification_workflow.md`
- `RELEASE_NOTES_1.2.0.md`
- `DEFERRED_ITEMS.md`

---

## Contributing

Contributions welcome:

- New language detectors
- Additional connectors
- Documentation improvements
- Bug reports and feature requests

Open an issue or PR.

---

## License

This project is licensed under the MIT License.

Built with precision by NGKsSystems
