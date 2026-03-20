# Source Matching Root Causes

## NGKsMediaLab
- failure_type: BAD_GLOB_OR_TARGET_CONFIG
- ownership: repo
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksgraph.exe configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsMediaLab
- exit_code: 1
- plan_path: None
- plan_snippet: plan_not_found
- evidence: CONFIG_ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files, but repository contains source files (sample: app/cpp_host/src/main.cpp, app/cpp_host/src/mainwindow.cpp, app/win32_host/src/main.cpp).

## NGKsGraph
- failure_type: BAD_GLOB_OR_TARGET_CONFIG
- ownership: repo
- command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksgraph.exe configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph --profile debug
- exit_code: 1
- plan_path: None
- plan_snippet: plan_not_found
- evidence: CONFIG_ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files, but repository contains source files (sample: examples/hello_msvc/src/main.cpp, examples/multi_target_msvc/src/app/main.cpp, examples/multi_target_msvc/src/core/core.cpp, examples/qt_msvc_real/build/debug/qt/moc_core_message.cpp, examples/qt_msvc_real/build/debug/qt/moc_main_window.cpp, examples/qt_msvc_real/build/debug/qt/qrc_app.cpp, examples/qt_msvc_real/build/release/qt/moc_core_message.cpp, examples/qt_msvc_real/build/release/qt/moc_main_window.cpp, examples/qt_msvc_real/build/release/qt/qrc_app.cpp, examples/qt_msvc_real/src/app/main.cpp).

