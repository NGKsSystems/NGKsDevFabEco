# Sources Analysis - NGKsGraph

- repo: C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph
- configure_command: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.venv\Scripts\ngksgraph.exe configure --project C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph --profile debug
- configure_exit_code: 1
- classification: BAD_GLOB_OR_TARGET_CONFIG
- ownership: repo

## ngksgraph.toml inspection
- config_path: C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\ngksgraph.toml
- src_glob: []
- targets: <no targets key>

## Manual glob expansion
- <no globs>

## Actual source files sample
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\real_qt_widgets\src\app\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\real_qt_widgets\src\core\widgets_core.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\src\app\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\src\core\core_message.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\src\ui\main_window.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\release\qt\moc_core_message.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\release\qt\moc_main_window.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\release\qt\qrc_app.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\debug\qt\moc_core_message.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\debug\qt\moc_main_window.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\debug\qt\qrc_app.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\multi_target_msvc\src\app\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\multi_target_msvc\src\core\core.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\hello_msvc\src\main.cpp
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\include\core_message.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\include\main_window.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\src\core\core_message.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\src\ui\main_window.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\release\qt\ui_mainwindow.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\qt_msvc_real\build\debug\qt\ui_mainwindow.h
- C:\Users\suppo\Desktop\NGKsSystems\NGKsGraph\examples\multi_target_msvc\src\core\core.h

## Error lines
- CONFIG_ERROR: NO_SOURCES_MATCHED: target='app' src_glob=[src/**/*.cpp] matched 0 files, but repository contains source files (sample: examples/hello_msvc/src/main.cpp, examples/multi_target_msvc/src/app/main.cpp, examples/multi_target_msvc/src/core/core.cpp, examples/qt_msvc_real/build/debug/qt/moc_core_message.cpp, examples/qt_msvc_real/build/debug/qt/moc_main_window.cpp, examples/qt_msvc_real/build/debug/qt/qrc_app.cpp, examples/qt_msvc_real/build/release/qt/moc_core_message.cpp, examples/qt_msvc_real/build/release/qt/moc_main_window.cpp, examples/qt_msvc_real/build/release/qt/qrc_app.cpp, examples/qt_msvc_real/src/app/main.cpp).

## Evidence files
- configure: C:\Users\suppo\Desktop\NGKsSystems\NGKsDevFabEco\.triage_work_20260318_152459\raw\NGKsGraph\10_configure.json
