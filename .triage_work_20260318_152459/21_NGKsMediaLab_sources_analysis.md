# Sources Analysis - NGKsMediaLab

- repo: C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab
- configure_command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksgraph.exe configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab
- configure_exit_code: 1
- classification: BAD_GLOB_OR_TARGET_CONFIG
- ownership: repo

## ngksgraph.toml inspection
- config_path: C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\ngksgraph.toml
- src_glob: []
- targets: <no targets key>

## Manual glob expansion
- <no globs>

## Actual source files sample
- C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\app\win32_host\src\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\app\cpp_host\src\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\app\cpp_host\src\mainwindow.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab\app\cpp_host\src\mainwindow.h

## Error lines
- CONFIG_ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files, but repository contains source files (sample: app/cpp_host/src/main.cpp, app/cpp_host/src/mainwindow.cpp, app/win32_host/src/main.cpp).

## Evidence files
- configure: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsMediaLab\10_configure.json
