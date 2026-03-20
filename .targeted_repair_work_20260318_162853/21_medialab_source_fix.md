# NGKsMediaLab Source-Match Fix

## File Modified
`C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\ngksgraph.toml`

## Root Cause
The original file used a `[project]` sub-table and a `[paths]` sub-table — neither of which the
NGKsGraph config parser reads. The parser reads **top-level keys** only. Because no top-level
`src_glob` was present, it defaulted to `["src/**/*.cpp"]`, which matched 0 files (NGKsMediaLab
has no `src/` directory at root).

## Original (broken) content
```toml
[project]
name = "NGKsMediaLab"
target = "app"
profile = "invalid-profile-name"

[qt]
version = "6.9.9"
root = "C:/Qt/NonExistentVersion"

[paths]
source_root = "app/cpp_host"
include_dirs = ["nonexistent/include"]
```

## Actual source layout
```
app/cpp_host/src/main.cpp
app/cpp_host/src/mainwindow.cpp
app/win32_host/src/main.cpp
```

## Applied fix
```toml
name = "NGKsMediaLab"
out_dir = "build"
target_type = "exe"
cxx_std = 20
src_glob = ["app/cpp_host/src/**/*.cpp", "app/win32_host/src/**/*.cpp"]
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

## Validation Result
`ngksgraph configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab --profile debug`
→ EXIT:0, plan written to `build_graph/debug/ngksgraph_plan.json`
