# NGKsDevFabEco — Capability Model Notes
## 60 — Capability Model Design Notes (Post-Hardening)

**Date:** 2026-03-18  
**Author:** Certification run — hardening pass

---

## The Bug: Qt6EntryPoint False-Negative

### What Happened

`canonical_target_spec.py::_required_capabilities()` derived a `qt.<module>` required capability for every lib starting with `Qt`. This included `Qt6EntryPoint`, producing required capability `qt.entrypoint`.

`capability_detector.py` detects Qt module capabilities by checking for the existence of `<qt_root>/include/Qt<Module>/` directories. The directory `include/QtEntrypoint` does not exist in any Qt installation — `Qt6EntryPoint` is a **Windows linker bootstrap library** (link-only, no public headers).

Result: `qt.entrypoint` was always `missing` → `build_allowed = false`.

### Root Classification

**ECOSYSTEM_BUG** — The capability derivation function conflated linker-only Windows bootstrap libraries with Qt SDK modules. The fix is minimal and surgical.

---

## The Fix

**File:** `NGKsGraph/ngksgraph/targetspec/canonical_target_spec.py`

```python
# Qt6EntryPoint is a Windows linker bootstrap library (link-only, no public include headers).
# It must not generate a qt.entrypoint capability requirement — there is no include/QtEntrypoint
# directory in any Qt installation, so the capability detector would always mark it missing.
_LINK_ONLY_QT_LIBS: frozenset[str] = frozenset({"entrypoint"})
```

The guard in `_required_capabilities()`:
```python
if module_name and module_name.lower() not in _LINK_ONLY_QT_LIBS:
    required.append(f"qt.{module_name.lower()}")
```

### Why This Is The Correct Design

Qt6EntryPoint characteristics:
- Ships as `lib/Qt6EntryPoint.lib` and `lib/Qt6EntryPointd.lib`
- Has no include directory (`include/QtEntrypoint` never exists)
- Is a pure linker-level artifact — provides `mainCRTStartup` entry point for Windows GUI subsystem apps using `/SUBSYSTEM:WINDOWS`
- Is not a Qt SDK module — it has no public API, no headers, no moc/uic/rcc processing

A "required capability" in NGKsGraph models something the build system must detect and verify before compiling. Qt6EntryPoint does not meet this definition — its presence is verified implicitly through `lib_dirs` resolution, not through include-directory detection.

---

## Design Invariant (After Fix)

> **A Qt lib generates a `qt.<module>` required capability IF AND ONLY IF it has a corresponding `include/Qt<Module>/` directory in the Qt installation.**

`_LINK_ONLY_QT_LIBS` maintains an explicit exclusion list for libs that violate this invariant. Currently: `{"entrypoint"}`.

---

## How To Extend `_LINK_ONLY_QT_LIBS`

If a future Qt version introduces additional link-only libraries (no include headers):

1. Verify the lib has no `include/Qt<Name>/` directory in the Qt root
2. Verify it is a pure linker artifact (no public API)
3. Add the normalized name (lowercase, no `Qt6` prefix, no `.lib` suffix) to `_LINK_ONLY_QT_LIBS`
4. Add a test in `tests/test_capability_derivation.py`

**Do NOT** extend the set based on speculation. Evidence (filesystem check + lib semantics) is required.

---

## Qt Lib Inventory (as of 2026-03-18)

Scanned across all active repos with `ngksgraph.toml`:

| Repo | Qt Libs Used | Link-Only Libs |
|---|---|---|
| NGKsFileVisionary | Core, Gui, Widgets, Concurrent, Sql, **EntryPoint** | **EntryPoint** |
| NGKsMediaLab | (none — Qt disabled) | — |
| NGKsPlayerNative | (none) | — |
| NGKsUI_Runtime | (none) | — |
| NGKsGraph (self) | (none — Qt disabled) | — |

**Only NGKsFileVisionary uses Qt libs. `Qt6EntryPoint` is the only link-only lib in the codebase.**

---

## Test Coverage

All cases are covered in `tests/test_capability_derivation.py`:

| Test | Assertion |
|---|---|
| `test_link_only_set_contains_entrypoint` | `_LINK_ONLY_QT_LIBS` contains `"entrypoint"` |
| `test_link_only_qt_lib_excluded` | `qt.entrypoint` NOT in required caps |
| `test_normal_qt_module_included` | `qt.core` IS in required caps |
| `test_multiple_normal_qt_modules_included` | All 5 normal modules present |
| `test_semantic_normalization_still_correct` | Normalization path unchanged |
| `test_normalization_dotlib_suffix_stripped` | `.lib` suffix handling correct |
| `test_normalization_cxx_standard_included` | `cxx.standard:N` reflects target |
| `test_non_qt_libs_do_not_generate_qt_capabilities` | Non-Qt libs don't pollute caps |
| `test_no_false_missing_capability_from_qt_entrypoint` | Resolver gate: `build_allowed=True` |
| `test_full_fvisionary_libs_no_missing_capabilities` | Full NGKsFileVisionary libs: clean |
