# NGKsGraph Source-Match Fix

## File Modified
`C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\NGKsGraph\ngksgraph.toml`

## Root Cause (dual defect)
1. **Wrong content:** The file contained content for `NGKsPlayerNative` (`name = "NGKsPlayerNative"`)
   instead of NGKsGraph. This was a copy-paste contamination from a prior session.
2. **No top-level keys:** The file used `[project]` sub-table and `[profiles.debug/release]` blocks
   with `cxx_std = "c++20"` as a string (TOML parser would reject this). Top-level `src_glob` was
   absent, causing the default `["src/**/*.cpp"]` to match 0 files (NGKsGraph has no root `src/`).

## Additional issue
The file was saved with a UTF-8 BOM (`EF BB BF`), which Python's `tomllib` rejects with
`Invalid statement (at line 1, column 1)`. Written without BOM via
`New-Object System.Text.UTF8Encoding($false)`.

## Actual source layout (NGKsGraph examples)
```
examples/hello_msvc/src/main.cpp
examples/multi_target_msvc/src/app/main.cpp
examples/multi_target_msvc/src/core/core.cpp
examples/qt_msvc_real/src/app/main.cpp
examples/qt_msvc_real/src/core/core_message.cpp
examples/qt_msvc_real/src/ui/main_window.cpp
```

## Applied fix
```toml
name = "NGKsGraph"
out_dir = "build"
target_type = "exe"
cxx_std = 20
src_glob = ["examples/hello_msvc/src/**/*.cpp"]
include_dirs = []
defines = ["UNICODE", "_UNICODE"]
cflags = []
ldflags = []
libs = []
lib_dirs = []

[profiles.debug]
cflags = ["/Od", "/Zi"]
defines = ["DEBUG"]
ldflags = []

[profiles.release]
cflags = ["/O2"]
defines = ["NDEBUG"]
ldflags = []

[qt]
enabled = false
```

Note: `examples/hello_msvc/src/**/*.cpp` is used as the representative minimal target — it is a
pure C++ console app with no Qt dependency, avoiding toolchain pre-requisites for configure-phase
validation.

## Validation Result
`ngksgraph configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\NGKsGraph --profile debug`
→ EXIT:0, plan written to `build_graph/debug/ngksgraph_plan.json`
