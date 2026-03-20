# NGKsDevFabEco — Certification Tier Definitions
**Version:** 1.0  
**Established:** 2026-03-19  
**Baseline:** Certification_Baseline_v1

---

## Overview

Every repo in the ecosystem certification baseline is assigned exactly one tier.  
Tier assignment is permanent until an explicit promotion/demotion is recorded in the manifest.

---

## TIER_1 — NGKSGRAPH_CERTIFIED

### Requirements

| Requirement | Details |
|---|---|
| `ngksgraph.toml` | Must exist at repo root |
| `ngksgraph configure` | Must exit 0 |
| `ngksgraph build` | Must exit 0 |
| `ngksdevfabric probe` | Must exit 0 |
| `ngksdevfabric doctor` | Must exit 0 |
| Proof zip | Must be produced by the build pipeline |
| `build_allowed` | Must be `true` in manifest |

### Baseline Fields

```json
{
  "tier": "TIER_1",
  "ecosystem_type": "cpp",
  "certification_scope": "full",
  "probe": "PASS",
  "doctor": "PASS",
  "configure": "PASS",
  "build": "PASS",
  "build_allowed": true
}
```

### Enforcement in `certify-baseline`

A TIER_1 repo fails the gate if **any** of the following are true:
- `probe` regresses from PASS → FAIL
- `doctor` regresses from PASS → FAIL
- `configure` regresses from PASS → FAIL
- `build` regresses from PASS → FAIL
- A PASS stage now exits non-zero in `--strict` mode

### Current TIER_1 repos (6)

| Repo | Primary Language | ngksgraph Target |
|---|---|---|
| NGKsFileVisionary | C++17 Qt6 | exe (FileVisionary) |
| NGKsMediaLab | C++20 Qt6 | exe (MediaLab) |
| NGKsPlayerNative | C++20 Qt6 | exe (PlayerNative) |
| NGKsUI_Runtime | C++20 Qt6 | exe (UI_Runtime) |
| NGKsGraph | Python (pure) | N/A — self-hosted |
| OfficeSuiteCpp | C++20 Qt6 | exe (WordApp) |

> **Note on NGKsGraph:** NGKsGraph is the build orchestrator itself. It is certified with `configure=PASS` / `build=PASS` reflecting its own build pipeline output, not ngksgraph self-hosting.

---

## TIER_2 — EXTERNAL_GOVERNED

### Requirements

| Requirement | Details |
|---|---|
| `ngksdevfabric probe` | Must exit 0 |
| `ngksdevfabric doctor` | Must exit 0 |
| Ecosystem declaration | `ecosystem_type` must be set |
| Classification reason | `classification_reason` must be set |

### Baseline Fields

```json
{
  "tier": "TIER_2",
  "ecosystem_type": "node|python|flutter|mixed",
  "certification_scope": "probe_doctor_only",
  "probe": "PASS",
  "doctor": "PASS",
  "configure": "N/A",
  "build": "N/A",
  "build_allowed": null
}
```

### Enforcement in `certify-baseline`

A TIER_2 repo fails the gate if **any** of the following are true:
- `probe` regresses from PASS → FAIL
- `doctor` regresses from PASS → FAIL

A TIER_2 repo **never** fails for `configure` or `build` — those stages are not in scope.

### What replaces the build stage

TIER_2 repos use their own native toolchain:

| Ecosystem | Native Build Toolchain |
|---|---|
| `npm+python` | `pnpm` / `npm run build` + `uvicorn`/`gunicorn` |
| `electron+node` | `electron-builder` / `npm run build` |
| `node+python-ai` | `vite build` + Python inference server startup |
| `flutter` | `flutter build` (manages its own DAG) |

### Current TIER_2 repos (4)

| Repo | Ecosystem Type | Reason |
|---|---|---|
| NGKsPINirvana | npm+python | FastAPI backend + Node frontend — no C++ sources |
| NGKs_ExecLedger | electron+node | Electron desktop + Node.js service — no C++ sources |
| NGKs_Zohan | node+python-ai | Vite/Node frontend + Python AI servers — no C++ sources |
| Content_Creator | flutter | Flutter/Dart app — toolchain manages its own build graph |

---

## Tier Promotion Rules

A repo may be promoted from TIER_2 → TIER_1 only when:
1. A valid `ngksgraph.toml` has been added to the repo root
2. `ngksgraph configure` exits 0
3. `ngksgraph build` exits 0
4. A successful `certify-baseline` run with `configure=PASS` and `build=PASS` is recorded
5. The manifest is updated and a new baseline run is created as evidence

A repo may be demoted from TIER_1 → TIER_2 only with explicit sign-off (manual review + commit).

---

## Tier Violation Rules

| Violation | Action |
|---|---|
| TIER_1 repo has `configure=N/A` | Contract violation — blocks the gate; update manifest to promote or demote the repo |
| TIER_1 repo has `configure=FAIL` | REGRESSION — blocks the gate |
| TIER_2 repo has `configure=PASS` | Contract violation — blocks the gate; promote to TIER_1 or reset configure to N/A |
| TIER_1 repo missing `ngksgraph.toml` | Must be added before next certification cycle |
| Repo missing `tier` field | Treated as TIER_1 if `configure != N/A`, else TIER_2 |

---

## Manifest Contract Summary

```
tier                 : "TIER_1" | "TIER_2"
ecosystem_type       : "cpp" | "node" | "python" | "flutter" | "mixed" | "npm+python" | "electron+node" | "node+python-ai"
certification_scope  : "full" | "probe_doctor_only"
```

All three fields are **required** as of 2026-03-19.  
Any manifest entry missing these fields will cause `certify-baseline` to emit a warning.
