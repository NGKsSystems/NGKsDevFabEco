================================================================================
NGKsDevFabEco Release Bundle (v1.2.0)
Deterministic Developer OS — Handoff Package
================================================================================

MISSION:
This bundle enables you to run NGKsDevFabEco on a new machine or without 
extensive setup knowledge. It provides:

- Prerequisite validation
- Single-command orchestration
- HTML dashboard for results
- Clear PASS/FAIL semantics for ship decisions
- Complete proof artifact capture

WHAT THIS BUNDLE DOES:
1. Validates your system prerequisites (Python, MSVC, Qt if needed)
2. Runs the deterministic build and certification workflow
3. Collects all proof artifacts in auditable folders
4. Generates an HTML dashboard summarizing results
5. Tells you if the build passed certification or failed

WHAT THIS BUNDLE DOES NOT DO:
- It does not modify your source code
- It does not weaken existing certification gates
- It does not create hidden dependencies
- It does not run unauditable external tools
- It does not assume tribal knowledge

QUICK START:
1. Read QUICKSTART.txt (5 minutes)
2. Read PREREQS.txt and verify your system
3. Run: .\run.ps1
4. View: status/dashboard.html
5. Interpret results with GATE_SEMANTICS.txt

DIRECTORY STRUCTURE:
- run.ps1              : Main orchestration script (use this)
- run.cmd             : Batch wrapper (alternative launcher)
- QUICKSTART.txt      : Get running in 5 minutes
- PREREQS.txt         : Install prerequisites
- FAILURE_GUIDE.txt   : Troubleshooting
- docs/               : Detailed policies and reference
- tools/              : Helper scripts (called automatically)
- status/             : Generated output (results appear here)

CHAIN OF CUSTODY:
This bundle enforces the authoritative DevFabEco execution chain:
  NGKsEnvCapsule (environment) 
  → NGKsGraph (planning) 
  → NGKsBuildCore (execution) 
  → NGKsLibrary/DevFabric (proof & certification)

See docs/CUSTODY_POLICY.txt for non-negotiable requirements.

SAFETY GUARANTEES:
✓ Fail-closed: Gates cannot be weakened
✓ Auditable: All actions logged with timestamps
✓ Portable: Self-contained bundle, no side effects
✓ Deterministic: Same inputs produce same outputs
✓ Proof-kept: All artifacts preserved for investigation

SUPPORT:
For questions about:
- Prerequisites: see PREREQS.txt and docs/
- Failures: see FAILURE_GUIDE.txt
- Semantics: see docs/GATE_SEMANTICS.txt
- Proof retention: see docs/PROOF_LIFECYCLE.txt

NEXT STEPS:
→ Read QUICKSTART.txt
================================================================================
