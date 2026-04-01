---
applyTo: "**/ngksgraph.toml"
---

# ngksgraph.toml Authoring Rules

## Target Inheritance

`[[targets]]` sections do NOT automatically inherit global-level `cflags`, `include_dirs`, `defines`, or `ldflags` if those keys are explicitly set (even to `[]`). Explicitly set them on the target.

## Required for Qt 6 targets on MSVC

```toml
cflags = ["/Zc:__cplusplus", "/permissive-"]
```

## Always include src/ in include_dirs

```toml
include_dirs = ["src"]
```

Without this, project-relative includes like `#include "core/query/QueryTypes.h"` will fail with C1083.

## Profile cflags are additive

`[profiles.debug]` cflags are appended to the target's cflags. Do not repeat flags already in the target.

## Qt module list drives includes, libs, and windeployqt

Only list modules actually used. Extra modules slow deployment and can introduce spurious DLL dependencies.

## SUBSYSTEM and ENTRY point

Windows GUI apps must set:
```toml
ldflags = ["/SUBSYSTEM:WINDOWS", "/ENTRY:mainCRTStartup"]
```

Console apps: omit `/SUBSYSTEM:WINDOWS`.

## windeployqt_qmldir

Only set this if the app uses QML:
```toml
[qt]
windeployqt_qmldir = "src/qml"
```

Widgets-only apps: omit or leave empty — `--qmldir` with an empty path causes windeployqt to fail.
