# NGKsGraph App Wrapper (Blended Install Model)

Use one shared NGKsGraph install and keep app repos thin.

- Shared tools Python: `NGKsTools\.venv\Scripts\python.exe`
- App repo wrapper: `tools\ngksgraph.ps1`
- Wrapper forwards all commands to:
  - `python -m ngksgraph <cmd> --project <APP_REPO_ROOT> ...`

## Option C Python discovery

Wrapper selection order:

1. `NGKSTOOLS_PY` (if it points to an existing file)
2. `%USERPROFILE%\NGKsTools\.venv\Scripts\python.exe`
3. Else fail with:
   - `NGKSTOOLS_PY_NOT_FOUND: set NGKSTOOLS_PY or install to %USERPROFILE%\NGKsTools\.venv`

## Root guard

Run wrapper from app repo root (must contain `ngksgraph.toml`).
If not, wrapper prints:

- `hey stupid Fucker, wrong window again`

## Usage examples

```powershell
.\tools\ngksgraph.ps1 doctor --profiles
.\tools\ngksgraph.ps1 plan --target app --profile debug --format json
.\tools\ngksgraph.ps1 build --target app --profile debug
```

## Proof artifacts

Proof is centralized in NGKsGraph CLI core under the NGKsGraph repo root:

- `_proof/run_<yyyyMMdd_HHmmss>/`
- `_proof/run_<yyyyMMdd_HHmmss>.zip`

Each run folder includes command line, stdout/stderr logs, environment metadata,
git metadata, and `RUN_SUMMARY.md`.

Wrapper does not install packages (`pip` is never called).
