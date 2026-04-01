---
applyTo: "**/*.cpp,**/*.h,**/*.hpp"
---

# NGKs C++ Project Context

## Build System

These files are built via the **NGKsDevFabEco pipeline** — not CMake, MSBuild, or Ninja directly.

Build command (from project root with `.venv` activated):
```batch
set NGKS_ALLOW_DIRECT_BUILDCORE=1
python -m ngksgraph build --profile debug --target <TARGET>
python -m ngksbuildcore run --plan build_graph\debug\ngksbuildcore_plan.json
```

## Compiler: MSVC (Visual Studio 18 / 2026)

- Standard: C++20 (`/std:c++20`)
- Required Qt flags: `/Zc:__cplusplus /permissive-`
- Windows subsystem: `/SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup`

## Qt Version: 6.10.2

- Root: `C:/Qt/6.10.2/msvc2022_64`
- Use `Q_OBJECT` macro in classes that need signals/slots — moc is run pre-compilation
- moc-generated files go to `build/<profile>/qt/moc_<Classname>.cpp`
- Include styles: `#include <QtWidgets/QMainWindow>` or `#include <QMainWindow>` both work

## Platform

Windows-only. No POSIX APIs. Use `QString`, `QFile`, `QDir` for file ops — not `std::filesystem` unless carefully wrapped.
