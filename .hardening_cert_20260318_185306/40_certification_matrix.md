# NGKsDevFabEco — Capability Model Hardening + Full Re-Certification
## 40 — Certification Matrix

**Run Date:** 2026-03-18  
**NGKsGraph:** 0.1.0 (b58ea54)  
**NGKsBuildCore:** 0.1.0  
**Python:** 3.13.5  
**Fix applied:** `canonical_target_spec.py` — `_LINK_ONLY_QT_LIBS` exclusion for `Qt6EntryPoint`

---

| Repo | Probe | Doctor | Configure | Build | build_allowed | missing_count | Proof Compliance | Owner | Blocker |
|---|---|---|---|---|---|---|---|---|---|
| NGKsFileVisionary | PASS | PASS | PASS | PASS | true | 0 | ZIP ✓ | — | CLEAN_PASS |
| NGKsMediaLab | PASS | PASS | PASS | PASS | true | 0 | ZIP ✓ | — | CLEAN_PASS |
| NGKsPlayerNative | PASS | PASS | PASS | PASS | true | 0 | ZIP ✓ | — | CLEAN_PASS |
| NGKsUI_Runtime | PASS | PASS | PASS | PASS | true | 0 | ZIP ✓ | — | CLEAN_PASS |
| NGKsGraph (self) | PASS | PASS | PASS | PASS | true | 0 | ZIP ✓ | — | CLEAN_PASS |

**REPOS_CERTIFIED:** 5  
**PASS:** 5  
**PARTIAL:** 0  
**FAIL:** 0  

---

## Proof ZIP Locations

| Repo | Proof ZIP |
|---|---|
| NGKsFileVisionary | `_proof\run_20260318_163541.zip` |
| NGKsMediaLab | `_proof\run_20260318_163555.zip` |
| NGKsPlayerNative | `_proof\run_20260318_163604.zip` |
| NGKsUI_Runtime | `_proof\run_20260318_163612.zip` |
| NGKsGraph (self) | `_proof\run_20260318_163620.zip` |

---

## Capability Model Regression

| Check | Result |
|---|---|
| `qt.entrypoint` absent from NGKsFileVisionary required caps | PASS |
| `qt.core/gui/widgets/sql/concurrent` still present | PASS |
| Full test suite (173 tests) | 173 PASS / 0 FAIL |
| New capability derivation tests (10 tests) | 10 PASS / 0 FAIL |
| `_LINK_ONLY_QT_LIBS` frozenset correct | PASS |

**CAPABILITY_MODEL_REGRESSION:** PASS
