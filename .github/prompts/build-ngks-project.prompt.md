---
mode: agent
description: "Build a Qt C++ project using the NGKsDevFabEco pipeline. Use when: build project, compile, ngksgraph build, ngksbuildcore run, rebuild, debug build, release build."
---

# Build NGKs C++ Project

Build the project at `${input:projectRoot}` for target `${input:targetName}` using profile `${input:profile|debug}`.

## Steps

1. Check that `${input:projectRoot}/ngksgraph.toml` exists and has the target `${input:targetName}`.
2. Verify that `${input:projectRoot}/.venv` exists.
3. Check `ngksgraph.toml` target for:
   - `cflags` includes `/Zc:__cplusplus` and `/permissive-` (required for Qt 6 MSVC)
   - `include_dirs` includes `"src"` (or wherever project headers live)
   - `ldflags` includes `/SUBSYSTEM:WINDOWS` and `/ENTRY:mainCRTStartup` for GUI apps
4. Run the following batch:

```batch
@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" > nul 2>&1
cd /d ${input:projectRoot}
call .venv\Scripts\activate.bat
set NGKS_ALLOW_DIRECT_BUILDCORE=1
python -m ngksgraph build --profile ${input:profile|debug} --target ${input:targetName}
python -m ngksbuildcore run --plan build_graph\${input:profile|debug}\ngksbuildcore_plan.json
```

5. Confirm binary exists at `build\${input:profile|debug}\bin\${input:targetName}.exe`.
6. Report any compile errors, filtering out `Note: including file:` lines for readability.

## Critical Notes

- `NGKS_ALLOW_DIRECT_BUILDCORE=1` is **mandatory**. Without it, `ngksbuildcore run` silently exits 0 with no compilation.
- `ngksgraph build` only generates the plan — it does NOT compile.
- moc-generated files must already exist in `build/${input:profile|debug}/qt/`. If they don't, run moc manually first.
- vcvars64.bat activates MSVC; without it, `cl` is not on PATH.
