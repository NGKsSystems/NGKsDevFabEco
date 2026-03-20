# PlayerNative Root-Handoff Fix

## File Modified
`NGKsDevFabric/src/ngksdevfabric/ngk_fabric/main.py`
Function: `_resolve_detected_build_root` (line 1190)

## Root Cause
`cmd_run` calls `_resolve_detected_build_root(project_root, build_detect_reason)` where
`build_detect_reason` is a relative path emitted by the build-input detector — e.g.
`third_party/JUCE/modules/juce_gui_extra/native/javascript` (a JS file found inside JUCE).
The old code resolved that path to an existing directory and returned it directly, so the graph
stage received `--project <deeply-nested-third-party-dir>` instead of the repo root.

## Before (defective)
```python
def _resolve_detected_build_root(project_root: Path, build_detect_reason: str) -> Path:
    reason = str(build_detect_reason or "").strip()
    if not reason or reason == "no_build_inputs":
        return project_root
    candidate = (project_root / reason).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except Exception:
        return project_root
    if candidate.is_dir():
        return candidate          # BUG: returned nested third_party path
    return candidate.parent
```

## After (patched)
```python
def _resolve_detected_build_root(project_root: Path, build_detect_reason: str) -> Path:
    reason = str(build_detect_reason or "").strip()
    if not reason or reason == "no_build_inputs":
        return project_root
    candidate = (project_root / reason).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except Exception:
        return project_root
    detected_root = candidate if candidate.is_dir() else candidate.parent
    if detected_root == project_root:
        return project_root

    # Prevent graph/build handoff from drifting into nested third_party or tool folders
    # unless that directory is explicitly graph-capable.
    if (detected_root / "ngksgraph.toml").is_file():
        return detected_root

    return project_root
```

## Guard Logic
Only re-root the build handoff to a subdirectory if that subdirectory contains `ngksgraph.toml`.
Otherwise the function returns `project_root` unchanged. This prevents JS/header/asset file
detections from hijacking the graph `--project` argument.

## Affected Code Path
`cmd_run` → `_resolve_detected_build_root` → `build_root` → graph subprocess `--project str(build_root)`
