# NGKsDevFabEco — Gap Analysis
## 50 — Post-Hardening Gap Analysis

**Run Date:** 2026-03-18  
**Post-fix state:** `canonical_target_spec.py` `_LINK_ONLY_QT_LIBS` exclusion applied

---

## 1. Remaining Ecosystem Issues

**Count: 0**

All ecosystem-level issues have been resolved:

| Issue | Status |
|---|---|
| `Qt6EntryPoint` false-negative capability detection | FIXED |
| `qt.entrypoint` blocking builds in NGKsFileVisionary | FIXED |
| Capability derivation treats link-only libs as Qt modules | FIXED via `_LINK_ONLY_QT_LIBS` |

---

## 2. Repo-Specific Issues

**Count: 0**

All 5 active repos pass all certification gates: probe/doctor/configure/build/resolution.

| Repo | Issues |
|---|---|
| NGKsFileVisionary | None |
| NGKsMediaLab | None |
| NGKsPlayerNative | None |
| NGKsUI_Runtime | None |
| NGKsGraph (self) | None |

---

## 3. Environment Gaps

**Count: 0 blocking**

| Gap | Classification | Blocking? |
|---|---|---|
| `pdb.debug` optional capability absent | environment | No (optional, non-blocking by policy) |

`pdb.debug` is consistently optional-missing in all Qt-enabled builds. It is non-blocking by design (`fail_on_missing_required_capability` policy only covers required capabilities). No action required.

---

## 4. Regression Check

The `Qt6EntryPoint` fix was contained to one function (`_required_capabilities()`) in one file (`canonical_target_spec.py`). All 173 existing tests continue to pass. No regressions detected in any repo.

---

## 5. Summary

- **Ecosystem issues before hardening:** 1 (`qt.entrypoint` false-negative)
- **Ecosystem issues after hardening:** 0
- **Repos blocked before:** 1 (NGKsFileVisionary)
- **Repos blocked after:** 0
- **Net improvement:** 100% certification rate across all 5 active repos
