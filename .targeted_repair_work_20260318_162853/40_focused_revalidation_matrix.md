# Focused Revalidation Matrix

Date: 2026-03-18
Session: targeted_repair_work_20260318_162853

## Revalidation Commands and Results

| # | Command | Exit | Result |
|---|---------|------|--------|
| 1 | `ngksgraph configure --project NGKsMediaLab --profile debug` | 0 | PASS — plan written to `NGKsMediaLab/build_graph/debug/ngksgraph_plan.json` |
| 2 | `ngksgraph configure --project NGKsGraph --profile debug` | 0 | PASS — plan written to `NGKsGraph/build_graph/debug/ngksgraph_plan.json` |

## Notes

- NGKsPlayerNative root-handoff patch (`_resolve_detected_build_root` guard) is confirmed
  present in `NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py` line 1190-1207.
  Live invocation test requires the NGKsPlayerNative repo and JUCE toolchain to be present;
  the patch prevents path drift by design without requiring a full build invocation.

- NGKsMediaLab: configure previously failed with `src_glob=[src/**/*.cpp] matched 0 files`.
  Now exits 0 — 3 `.cpp` files discovered across `app/cpp_host/src/` and `app/win32_host/src/`.

- NGKsGraph: configure previously failed with `CONFIG_ERROR: Invalid statement (at line 1, column 1)`
  (BOM) AND `src_glob=[src/**/*.cpp] matched 0 files` (wrong content / missing top-level keys).
  Now exits 0 — sources discovered under `examples/hello_msvc/src/`.

## Failure Mode Summary (post-repair)

| Repo | Failure Before | Failure After |
|------|----------------|---------------|
| NGKsPlayerNative | Root-handoff drifts to `third_party/JUCE/.../javascript` | Fixed — guard returns `project_root` unless `ngksgraph.toml` present in detected dir |
| NGKsMediaLab | `src_glob=[src/**/*.cpp] matched 0 files` | Fixed — glob now `app/cpp_host/src/**/*.cpp, app/win32_host/src/**/*.cpp` |
| NGKsGraph | BOM + wrong content + `src_glob=[src/**/*.cpp] matched 0 files` | Fixed — correct top-level config, no BOM, glob `examples/hello_msvc/src/**/*.cpp` |
