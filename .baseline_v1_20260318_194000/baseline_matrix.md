# Certification Baseline v1 — Matrix
## NGKsDevFabEco Certification Matrix

**Baseline:** Certification_Baseline_v1  
**Date:** 2026-03-18  
**Ecosystem:** b58ea54c6ffc8f695c997b2bddfdaf161f203ae0

| Repo | Commit | Tier | Ecosystem | Proof Scope | Probe | Doctor | Configure | Build | build_allowed | missing_count | optional_missing | Proof Compliance | Owner | Blocker | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NGKsFileVisionary | 4e5ad33 | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | pdb.debug | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| NGKsMediaLab | af193f1 | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | none | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| NGKsPlayerNative | fefdef4 | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | none | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| NGKsUI_Runtime | 90ca09c | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | none | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| NGKsGraph | f07af35 | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | none | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| OfficeSuiteCpp | ae4ca5f | TIER_1 | cpp | full | PASS | PASS | PASS | PASS | true | 0 | none | ZIP ✓ | — | CLEAN_PASS | **PASS** |
| NGKsPINirvana | 8ba8836 | TIER_2 | npm+python | probe_doctor_only | PASS | PASS | N/A | N/A | N/A | N/A | — | N/A (external) | — | PROBE_DOCTOR_PASS | **PASS** |
| NGKs_ExecLedger | 10a0dc9 | TIER_2 | electron+node | probe_doctor_only | PASS | PASS | N/A | N/A | N/A | N/A | — | N/A (external) | — | PROBE_DOCTOR_PASS | **PASS** |
| NGKs_Zohan | 086e0b6 | TIER_2 | node+python-ai | probe_doctor_only | PASS | PASS | N/A | N/A | N/A | N/A | — | N/A (external) | — | PROBE_DOCTOR_PASS | **PASS** |
| Content_Creator | 197970c | TIER_2 | flutter | probe_doctor_only | PASS | PASS | N/A | N/A | N/A | N/A | — | N/A (external) | — | PROBE_DOCTOR_PASS | **PASS** |

**PASS: 10 / PARTIAL: 0 / FAIL: 0 — TIER_1: 6 / TIER_2: 4**

> **TIER_1 (NGKSGRAPH_CERTIFIED):** probe+doctor+configure+build all PASS; ngksgraph.toml required.  
> **TIER_2 (EXTERNAL_GOVERNED):** probe+doctor PASS; configure/build N/A — external toolchain (npm, electron, flutter).
