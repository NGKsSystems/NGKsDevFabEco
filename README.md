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
If you run `-UserInstall` outside a venv, the installer now prompts:
`You are not in a virtual environment. Create and activate .venv now? [Y/N]`
After installation:

Activate: .\.venv\Scripts\Activate.ps1
Or use -UserInstall for PATH-wide install

Alternative (pip)
PowerShellpip install ngksdevfabeco

Quick Start
PowerShell# 1. Initialize a project
ngksgraph init

# 2. Scan & configure (auto-detects MSVC, Qt, languages, requirements)
ngksgraph configure --profile debug

# 3. Build with full determinism
ngksgraph build --profile debug --msvc-auto

# 4. Forensic analysis
ngksgraph why build\debug\bin\app.exe --profile debug
ngksgraph rebuild-cause build\debug\bin\app.exe --profile debug
ngksgraph trace src\main.cpp --profile debug

# 5. Create reproducible capsule
ngksgraph freeze --profile debug
Environment commands
PowerShellngksenvcapsule doctor
ngksenvcapsule lock
ngksenvcapsule verify
Certification
PowerShellngksdevfabric certify-gate
ngksdevfabric predict-risk
Run ngksgraph --help, ngksenvcapsule --help, or ngksdevfabric --help for full options.

Key CLI Commands
NGKsGraph (main intelligence tool)

init • scan • configure • build • plan • explain
why • rebuild-cause • diff • trace • freeze • thaw
doctor • clean • graph

NGKsEnvCapsule

doctor • resolve • lock • verify

NGKsDevFabric (certification & workflows)

certify • certify-gate • certify-target-check
predict-risk • plan-validation • run-validation-and-certify

Others

ngksbuildcore run • ngkslibrary assemble


Unique Value

Reproducibility Capsules — Freeze entire build state (ZIP + hashes) and thaw anywhere
Build Forensics — Deep “why” analysis and rebuild classification
Certification Ledger — Immutable proof artifacts for every run
MSVC Auto-Discovery — Automatic Visual Studio environment bootstrapping
Proof Artifacts — events.jsonl, commands.jsonl, environment.txt, git_status.txt, tool_versions.txt, etc.

Every operation is logged with full audit trail — perfect for CI/CD and compliance.

Roadmap (Post-v1.2.0)
Next milestone (recommended now):

Full Transport/Delivery Layer (GitHub, Jira, webhooks, email)

Deferred (see DEFERRED_ITEMS.md):

Dashboard UX
Proof-root cleanup & retention policy
Organization/team ownership mapping
Dry-run vs live-send policies


Project Status

Phase: Wiring & stabilization complete (39 requirements validated)
Platform: Windows-first (MSVC native)
Testing: Extensive (fixtures + validation suite)
Releases: Meta-package ready (dist folders present)


Documentation

Comprehensive Capabilities & Validation Document
Certification Workflow
Release Notes
DEFERRED_ITEMS.md


Contributing
Contributions welcome!

New language detectors
Additional connectors
Documentation improvements
Bug reports / feature requests

Open an issue or PR — we’re in the wiring phase and open to collaboration.

License
This project is licensed under the MIT License (add a LICENSE file if you haven’t yet).

Built with precision by NGKsSystems
