# Certification Baseline v1
## NGKsDevFabEco — Official Baseline Freeze

**Date:** 2026-03-18  
**Baseline Name:** `Certification_Baseline_v1`  
**Ecosystem Commit:** `b58ea54c6ffc8f695c997b2bddfdaf161f203ae0`  
**Status:** LOCKED / ALL GATES PASS

---

## What This Baseline Captures

This is the first official certified baseline for the NGKsDevFabEco ecosystem. It captures the state immediately after:

1. **Qt6EntryPoint false-negative capability bug was fixed** — `_LINK_ONLY_QT_LIBS` exclusion in `canonical_target_spec.py`
2. **10 deterministic capability derivation tests** added to `NGKsGraph/tests/test_capability_derivation.py`
3. **Full cross-repo re-certification** confirming all 5 active repos pass all gates
4. **173-test suite passes clean** with no regressions

---

## Certified Repos

| Repo | Commit | Probe | Doctor | Configure | Build | build_allowed | Gate |
|---|---|---|---|---|---|---|---|
| NGKsFileVisionary | `4e5ad33` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKsMediaLab | `af193f1` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKsPlayerNative | `fefdef4` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKsUI_Runtime | `90ca09c` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKsGraph | `f07af35` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKsPINirvana | `8ba8836` | PASS | PASS | N/A | N/A | N/A | **PASS** |
| OfficeSuiteCpp | `ae4ca5f` | PASS | PASS | PASS | PASS | true | **PASS** |
| NGKs_ExecLedger | `10a0dc9` | PASS | PASS | N/A | N/A | N/A | **PASS** |
| NGKs_Zohan | `086e0b6` | PASS | PASS | N/A | N/A | N/A | **PASS** |
| Content_Creator | `197970c` | PASS | PASS | N/A | N/A | N/A | **PASS** |

> **TIER_1** (NGKSGRAPH_CERTIFIED): NGKsFileVisionary, NGKsMediaLab, NGKsPlayerNative, NGKsUI_Runtime, NGKsGraph, OfficeSuiteCpp — probe+doctor+configure+build all PASS.  
> **TIER_2** (EXTERNAL_GOVERNED): NGKsPINirvana, NGKs_ExecLedger, NGKs_Zohan, Content_Creator — probe+doctor PASS; configure/build N/A (external toolchain).  
> See [certification_tiers.md](certification_tiers.md) for full tier contract definitions.

**Repos Locked:** 10 — TIER_1 (NGKSGRAPH_CERTIFIED): 6 / TIER_2 (EXTERNAL_GOVERNED): 4  
**All Gates Pass:** YES  
**Optional-Missing Only:** YES (`pdb.debug` in NGKsFileVisionary — non-blocking by policy)

---

## Package Versions at Baseline

| Package | Version |
|---|---|
| ngksdevfabeco | 1.2.5 |
| ngksdevfabric | 1.2.3 |
| ngksgraph | 0.1.13 |
| ngksbuildcore | 0.1.7 |
| ngksenvcapsule | 0.1.5 |
| ngkslibrary | 0.1.5 |
| Python | 3.13.5 |

## Toolchain at Baseline

| Component | Value |
|---|---|
| MSVC | 18.3.11520.95 (Visual Studio 2022 v18) |
| Windows SDK | 10.0.26100.0 |
| Qt | 6.10.2 msvc2022_64 |

---

## Capability Model State

The `_required_capabilities()` function in `canonical_target_spec.py` now correctly excludes link-only Qt libraries from required capability generation via `_LINK_ONLY_QT_LIBS = frozenset({"entrypoint"})`.

**Invariant:** A Qt lib generates a `qt.<module>` required capability **if and only if** it has a corresponding `include/Qt<Module>/` directory in the Qt installation root.

---

## Optional-Missing Notes

| Repo | Optional Missing | Blocking? |
|---|---|---|
| NGKsFileVisionary | `pdb.debug` | No (optional by policy) |
| All others | none | — |

`pdb.debug` absence is expected — no separate PDB debugger is configured on this machine. It is classified optional in the capability policy and has no effect on `build_allowed`.

---

## Proof References

| Run | ZIP |
|---|---|
| NGKsFileVisionary cert | `_proof\run_20260318_163541.zip` |
| NGKsMediaLab cert | `_proof\run_20260318_163555.zip` |
| NGKsPlayerNative cert | `_proof\run_20260318_163604.zip` |
| NGKsUI_Runtime cert | `_proof\run_20260318_163612.zip` |
| NGKsGraph self-cert | `_proof\run_20260318_163620.zip` |
| Hardening cert packet | `_proof\hardening_cert_20260318_185306.zip` |

---

## Gate Result

```
BASELINE_NAME=Certification_Baseline_v1
REPOS_LOCKED=10
ALL_GATES_PASS=PASS
OPTIONAL_MISSING_ONLY=PASS
TIER_1_COUNT=6
TIER_2_COUNT=4
GATE=PASS
```

**Release gate command (mandatory pre-release):**
```
ngksdevfabric release-gate --eco-root <path>
```
No release bundle is valid unless `release-gate` exits 0 and produces `verdict=PASS`.  
See [release_gate.md](release_gate.md) for full contract.
