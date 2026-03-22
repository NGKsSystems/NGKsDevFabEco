from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re


_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx"}
_HEADER_SUFFIXES = {".h", ".hh", ".hpp", ".hxx"}
_SCAN_SUFFIXES = _SOURCE_SUFFIXES | _HEADER_SUFFIXES
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "third_party",
    "_proof",
    "_artifacts",
    "artifacts",
}

_QT_MODULE_CANONICAL = {
    "core": "Core",
    "gui": "Gui",
    "widgets": "Widgets",
    "network": "Network",
    "sql": "Sql",
    "concurrent": "Concurrent",
    "svg": "Svg",
    "printsupport": "PrintSupport",
    "qml": "Qml",
    "quick": "Quick",
    "quickcontrols2": "QuickControls2",
    "test": "Test",
    "testlib": "Test",
    "xml": "Xml",
    "xmlpatterns": "XmlPatterns",
    "opengl": "OpenGL",
    "openglwidgets": "OpenGLWidgets",
    "multimedia": "Multimedia",
    "multimediawidgets": "MultimediaWidgets",
    "websockets": "WebSockets",
    "webchannel": "WebChannel",
    "webengine": "WebEngine",
    "webenginecore": "WebEngineCore",
    "webenginewidgets": "WebEngineWidgets",
    "webenginequick": "WebEngineQuick",
}

_QT_MODULE_ORDER = [
    "Core",
    "Gui",
    "Widgets",
    "Network",
    "Sql",
    "Concurrent",
    "Svg",
    "PrintSupport",
]

_QT_CLASS_PREFIX_MODULES = [
    ("QNetwork", "Network"),
    ("QSql", "Sql"),
    ("QSvg", "Svg"),
    ("QPrinter", "PrintSupport"),
    ("QPrint", "PrintSupport"),
    ("QtConcurrent", "Concurrent"),
    ("QFuture", "Concurrent"),
    ("QThread", "Concurrent"),
    ("QWidget", "Widgets"),
    ("QMainWindow", "Widgets"),
    ("QApplication", "Gui"),
    ("QGuiApplication", "Gui"),
]


def _canonical_qt_module_name(name: str) -> str:
    token = str(name or "").strip()
    if not token:
        return ""
    if token.lower().startswith("qt6") or token.lower().startswith("qt5"):
        token = token[3:]
    if token.lower().startswith("qt") and token.lower() not in _QT_MODULE_CANONICAL:
        token = token[2:]
    if token.lower().endswith(".lib"):
        token = token[:-4]
    key = token.strip().lower()
    if not key:
        return ""
    if key not in _QT_MODULE_CANONICAL and token.endswith("d"):
        token = token[:-1]
        key = token.strip().lower()
        if not key:
            return ""
    if key in _QT_MODULE_CANONICAL:
        return _QT_MODULE_CANONICAL[key]
    return token[0].upper() + token[1:]


def _infer_module_from_q_include(include_token: str) -> str:
    token = str(include_token or "").strip()
    if not token:
        return ""
    if token.startswith("Qt") and "/" in token:
        return _canonical_qt_module_name(token.split("/", 1)[0])
    if not token.startswith("Q"):
        return ""
    for prefix, module in _QT_CLASS_PREFIX_MODULES:
        if token.startswith(prefix):
            return module
    return ""


def _sort_qt_modules(modules: set[str]) -> list[str]:
    ordered: list[str] = [module for module in _QT_MODULE_ORDER if module in modules]
    extras = sorted(module for module in modules if module not in _QT_MODULE_ORDER)
    return ordered + extras


@dataclass(frozen=True)
class RepoClassification:
    family: str
    reasoning: tuple[str, ...]
    app_names: tuple[str, ...]
    default_target: str
    source_globs: tuple[str, ...]
    include_dirs: tuple[str, ...]
    libs: tuple[str, ...]
    cflags: tuple[str, ...]
    qt_enabled: bool
    qt_modules: tuple[str, ...]
    qt_root: str
    target_type: str
    qt_signal_count: int
    entrypoint_count: int
    windows_signal: bool


def _iter_repo_files(repo_root: Path):
    for dirpath, dirnames, filenames in repo_root.walk(top_down=True):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS and not name.startswith(".")]
        for filename in filenames:
            yield dirpath / filename


def _discover_repo_app_mains(repo_root: Path) -> list[str]:
    app_names: set[str] = set()
    for main_path in sorted((repo_root / "apps").glob("*/main.cpp")):
        if main_path.is_file() and len(main_path.parts) >= 2:
            app_names.add(main_path.parent.name)
    return sorted(app_names)


def _has_engine_sources(repo_root: Path) -> bool:
    engine_root = repo_root / "engine"
    if not engine_root.exists():
        return False
    for pattern in ("**/*.cpp", "**/*.c"):
        if any(path.is_file() for path in engine_root.glob(pattern)):
            return True
    return False


def _detect_source_globs(repo_root: Path) -> list[str]:
    roots = ["src", "app", "apps", "engine"]
    selected: list[str] = []
    for root in roots:
        root_path = repo_root / root
        if not root_path.exists():
            continue
        has_sources = any(path.is_file() for path in root_path.glob("**/*.cpp")) or any(
            path.is_file() for path in root_path.glob("**/*.c")
        )
        if has_sources:
            selected.extend([f"{root}/**/*.cpp", f"{root}/**/*.c"])

    if not selected:
        selected = ["src/**/*.cpp", "src/**/*.c"]
    return selected


def _detect_flutter_source_globs(repo_root: Path) -> list[str]:
    globs: list[str] = []
    candidates = [
        "windows/runner/**/*.cpp",
        "windows/flutter/**/*.cpp",
        "linux/**/*.cc",
        "linux/**/*.cpp",
        "macos/**/*.mm",
        "macos/**/*.cpp",
    ]
    for pattern in candidates:
        if any(path.is_file() for path in repo_root.glob(pattern)):
            globs.append(pattern)
    if not globs:
        globs = ["windows/runner/**/*.cpp", "linux/**/*.cc", "linux/**/*.cpp"]
    return globs


def _detect_juce_source_globs(repo_root: Path) -> list[str]:
    globs: list[str] = []
    candidates = [
        "Source/**/*.cpp",
        "source/**/*.cpp",
        "JuceLibraryCode/**/*.cpp",
        "src/**/*.cpp",
    ]
    for pattern in candidates:
        if any(path.is_file() for path in repo_root.glob(pattern)):
            globs.append(pattern)
    if not globs:
        globs = ["Source/**/*.cpp", "source/**/*.cpp", "src/**/*.cpp"]
    return globs


def _detect_include_dirs(repo_root: Path) -> list[str]:
    candidates = [
        "include",
        "src",
        "app/include",
        "engine/core/include",
        "engine/gfx/include",
        "engine/gfx/win32/include",
        "engine/platform/win32/include",
        "engine/ui",
        "engine/ui/include",
        "engine/include",
    ]
    include_dirs = [path for path in candidates if (repo_root / path).exists()]
    if not include_dirs:
        include_dirs = ["include"]
    return include_dirs


def _detect_flutter_include_dirs(repo_root: Path) -> list[str]:
    candidates = [
        "windows",
        "windows/runner",
        "windows/flutter",
        "linux",
        "linux/flutter",
        "include",
    ]
    include_dirs = [path for path in candidates if (repo_root / path).exists()]
    if not include_dirs:
        include_dirs = ["windows", "windows/runner"]
    return include_dirs


def _detect_juce_include_dirs(repo_root: Path) -> list[str]:
    candidates = ["Source", "source", "JuceLibraryCode", "modules", "include", "src"]
    include_dirs = [path for path in candidates if (repo_root / path).exists()]
    if not include_dirs:
        include_dirs = ["Source", "modules"]
    return include_dirs


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _is_flutter_repo(repo_root: Path) -> bool:
    pubspec = _read_text_if_exists(repo_root / "pubspec.yaml")
    if not pubspec:
        return False
    has_flutter_sdk = "sdk: flutter" in pubspec or "flutter:" in pubspec
    has_dart_entry = (repo_root / "lib" / "main.dart").exists()
    has_platform_dir = any((repo_root / name).exists() for name in ["android", "ios", "windows", "linux", "macos", "web"])
    return has_flutter_sdk and (has_dart_entry or has_platform_dir)


def _count_juce_signals(repo_root: Path) -> int:
    count = 0
    count += sum(1 for _ in repo_root.glob("**/*.jucer"))

    cmake_text = _read_text_if_exists(repo_root / "CMakeLists.txt")
    for token in ["juce_add_plugin", "juce_add_gui_app", "juce_add_console_app", "juce_add_binary_data"]:
        count += cmake_text.count(token)

    juce_include_re = re.compile(r"#\s*include\s*<\s*(?:JuceHeader\.h|juce_[^>]+)\s*>")
    for path in _iter_repo_files(repo_root):
        if path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        text = _read_text_if_exists(path)
        if not text:
            continue
        count += len(juce_include_re.findall(text))
        count += text.count("namespace juce")
        count += text.count("JUCEApplication")

    return count


def _collect_text_signals(repo_root: Path) -> dict[str, object]:
    source_files: list[Path] = []
    config_files: list[Path] = []
    ui_files = 0
    qrc_files = 0
    pro_files = 0
    pri_files = 0

    for path in _iter_repo_files(repo_root):
        suffix = path.suffix.lower()
        if suffix in _SCAN_SUFFIXES:
            source_files.append(path)
        elif path.name in {"CMakeLists.txt", "meson.build"} or suffix in {".cmake", ".pro", ".pri"}:
            config_files.append(path)
        elif suffix == ".ui":
            ui_files += 1
        elif suffix == ".qrc":
            qrc_files += 1
        elif suffix == ".pro":
            pro_files += 1
        elif suffix == ".pri":
            pri_files += 1

    include_qt = 0
    q_object = 0
    q_application = 0
    q_mainwindow = 0
    winmain = 0
    windows_header = 0
    entrypoints = 0
    widgets_headers = 0
    gui_headers = 0
    core_headers = 0
    qt_modules_detected: set[str] = set()

    entrypoint_re = re.compile(r"\b(?:main|wmain|WinMain|wWinMain)\s*\(")
    qt_include_re = re.compile(r"#\s*include\s*<\s*Q[A-Za-z0-9_/:.]+\s*>")
    include_token_re = re.compile(r"#\s*include\s*<\s*([A-Za-z0-9_/:.]+)\s*>")
    qt_ns_module_re = re.compile(r"\bQt(?:5|6)::([A-Za-z0-9_]+)\b")
    qt_lib_module_re = re.compile(r"\bQt(?:5|6)([A-Za-z0-9_]+)\.lib\b", flags=re.IGNORECASE)
    cmake_components_re = re.compile(r"find_package\s*\(\s*Qt(?:5|6)\s+COMPONENTS\s+([^)]+)\)", flags=re.IGNORECASE)

    for source_path in source_files:
        try:
            text = source_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        include_qt += len(qt_include_re.findall(text))
        for include_token in include_token_re.findall(text):
            module = _infer_module_from_q_include(include_token)
            if module:
                qt_modules_detected.add(module)
        for module_token in qt_ns_module_re.findall(text):
            module = _canonical_qt_module_name(module_token)
            if module:
                qt_modules_detected.add(module)
        for module_token in qt_lib_module_re.findall(text):
            module = _canonical_qt_module_name(module_token)
            if module:
                qt_modules_detected.add(module)
        q_object += text.count("Q_OBJECT")
        q_application += text.count("QApplication") + text.count("QGuiApplication")
        q_mainwindow += text.count("QMainWindow")
        winmain += text.count("WinMain") + text.count("wWinMain")
        windows_header += text.count("#include <windows.h>") + text.count("#include <Windows.h>")
        entrypoints += len(entrypoint_re.findall(text))

        low = text.lower()
        widgets_headers += low.count("qlineedit") + low.count("qwidget") + low.count("qpushbutton")
        gui_headers += low.count("qwindow") + low.count("qguiapplication")
        core_headers += low.count("qobject") + low.count("qstring") + low.count("qbytearray")

    for config_path in config_files:
        text = _read_text_if_exists(config_path)
        if not text:
            continue
        for match in cmake_components_re.findall(text):
            for token in re.split(r"[\s;]+", match):
                module = _canonical_qt_module_name(token)
                if module:
                    qt_modules_detected.add(module)
        for module_token in qt_ns_module_re.findall(text):
            module = _canonical_qt_module_name(module_token)
            if module:
                qt_modules_detected.add(module)
        for module_token in qt_lib_module_re.findall(text):
            module = _canonical_qt_module_name(module_token)
            if module:
                qt_modules_detected.add(module)

    return {
        "ui_files": ui_files,
        "qrc_files": qrc_files,
        "pro_files": pro_files,
        "pri_files": pri_files,
        "include_qt": include_qt,
        "q_object": q_object,
        "q_application": q_application,
        "q_mainwindow": q_mainwindow,
        "winmain": winmain,
        "windows_header": windows_header,
        "entrypoints": entrypoints,
        "widgets_headers": widgets_headers,
        "gui_headers": gui_headers,
        "core_headers": core_headers,
        "qt_modules_detected": _sort_qt_modules(qt_modules_detected),
    }


def _infer_qt_modules(signals: dict[str, object]) -> list[str]:
    modules = [
        _canonical_qt_module_name(str(module))
        for module in list(signals.get("qt_modules_detected", []))
        if _canonical_qt_module_name(str(module))
    ]
    if int(signals["core_headers"]) > 0 or int(signals["include_qt"]) > 0 or int(signals["q_object"]) > 0:
        if "Core" not in modules:
            modules.append("Core")
    if int(signals["gui_headers"]) > 0 or int(signals["q_application"]) > 0:
        if "Core" not in modules:
            modules.append("Core")
        if "Gui" not in modules:
            modules.append("Gui")
    if int(signals["widgets_headers"]) > 0 or int(signals["q_mainwindow"]) > 0:
        if "Core" not in modules:
            modules.append("Core")
        if "Gui" not in modules:
            modules.append("Gui")
        if "Widgets" not in modules:
            modules.append("Widgets")
    if modules and "Core" not in modules:
        modules.insert(0, "Core")
    if "Widgets" in modules and "Gui" not in modules:
        modules.insert(1 if "Core" in modules else 0, "Gui")
    if not modules:
        modules = ["Core", "Gui", "Widgets"]
    return _sort_qt_modules(set(modules))


def _detect_qt_root() -> str:
    env_candidates = [os.environ.get("QTDIR", ""), os.environ.get("QT_ROOT", ""), os.environ.get("Qt6_DIR", "")]
    for raw in env_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        p = Path(text)
        if p.name.lower() == "lib" and p.parent.exists():
            p = p.parent
        if p.exists() and (p / "bin" / "moc.exe").exists():
            return p.resolve().as_posix()

    qt_root = Path("C:/Qt")
    if qt_root.exists():
        version_dirs = sorted((d for d in qt_root.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
        for version_dir in version_dirs:
            kits = sorted(version_dir.glob("msvc*_64"), key=lambda d: d.name, reverse=True)
            for kit in kits:
                if (kit / "bin" / "moc.exe").exists():
                    return kit.resolve().as_posix()
            if (version_dir / "bin" / "moc.exe").exists():
                return version_dir.resolve().as_posix()
    return ""


def classify_repo(repo_root: Path) -> RepoClassification:
    app_names = _discover_repo_app_mains(repo_root)
    engine_sources = _has_engine_sources(repo_root)
    source_globs = _detect_source_globs(repo_root)
    include_dirs = _detect_include_dirs(repo_root)
    signals = _collect_text_signals(repo_root)
    flutter_detected = _is_flutter_repo(repo_root)
    juce_signal_count = _count_juce_signals(repo_root)

    qt_signal_count = int(signals["ui_files"]) + int(signals["qrc_files"]) + int(signals["pro_files"]) + int(
        signals["pri_files"]
    ) + int(signals["include_qt"]) + int(signals["q_object"]) + int(signals["q_application"]) + int(
        signals["q_mainwindow"]
    )
    qt_enabled = qt_signal_count > 0

    windows_signal = bool(int(signals["winmain"]) > 0 or int(signals["windows_header"]) > 0)
    entrypoint_count = int(signals["entrypoints"])

    default_target = "widget_sandbox" if "widget_sandbox" in app_names else (app_names[0] if app_names else "app")

    libs: list[str] = []
    cflags: list[str] = []
    if windows_signal:
        libs.extend(["user32", "gdi32"])
    if (repo_root / "engine" / "gfx" / "win32").exists():
        libs.extend(["d3d11", "dxgi"])
    libs = sorted(set(libs))

    reasoning: list[str] = []
    family = "native-single-target"
    target_type = "exe"

    if engine_sources and len(app_names) >= 2:
        family = "engine-multi-target"
        reasoning.append("Detected engine sources with multiple apps/*/main.cpp entrypoints.")
    elif flutter_detected:
        family = "flutter-app"
        reasoning.append("Detected Flutter layout (pubspec + flutter SDK markers + platform/app structure).")
        source_globs = _detect_flutter_source_globs(repo_root)
        include_dirs = _detect_flutter_include_dirs(repo_root)
        libs = sorted(set([*libs, "user32", "gdi32", "shell32", "ole32", "advapi32"]))
        target_type = "exe"
        default_target = "flutter_runner"
    elif juce_signal_count > 0:
        family = "juce-app"
        reasoning.append("Detected JUCE markers (.jucer / juce_add_* / JuceHeader includes).")
        source_globs = _detect_juce_source_globs(repo_root)
        include_dirs = _detect_juce_include_dirs(repo_root)
        libs = sorted(set([*libs, "user32", "gdi32", "ole32", "comdlg32", "shell32", "winmm"]))
        cflags.append("/Zc:__cplusplus")
        cflags.append("/permissive-")
        target_type = "exe" if entrypoint_count > 0 else "staticlib"
        default_target = "juce_app"
    elif qt_enabled:
        family = "qt-app"
        reasoning.append("Detected Qt-specific repo signals (.ui/.qrc/.pro/.pri/Q* includes/Q_OBJECT/QApplication).")
        cflags.append("/Zc:__cplusplus")
        cflags.append("/permissive-")
    elif len(app_names) >= 2:
        family = "native-multi-target"
        reasoning.append("Detected multiple app entrypoint folders under apps/*/main.cpp.")
    elif entrypoint_count == 0:
        family = "native-single-target"
        target_type = "staticlib"
        reasoning.append("No entrypoint symbols detected; defaulting to static library single target.")
    else:
        family = "native-single-target"
        reasoning.append("Detected single native entrypoint; defaulting to executable single target.")

    if family == "engine-multi-target":
        libs = sorted(set([*libs, "user32", "gdi32", "d3d11", "dxgi"]))

    return RepoClassification(
        family=family,
        reasoning=tuple(reasoning),
        app_names=tuple(app_names),
        default_target=default_target,
        source_globs=tuple(source_globs),
        include_dirs=tuple(include_dirs),
        libs=tuple(libs),
        cflags=tuple(sorted(set(cflags))),
        qt_enabled=qt_enabled,
        qt_modules=tuple(_infer_qt_modules(signals) if qt_enabled else ()),
        qt_root=_detect_qt_root() if qt_enabled else "",
        target_type=target_type,
        qt_signal_count=qt_signal_count,
        entrypoint_count=entrypoint_count,
        windows_signal=windows_signal,
    )


def _render_common_header(include_dirs: tuple[str, ...], cflags: tuple[str, ...]) -> list[str]:
    return [
        'out_dir = "build"',
        'warnings = "default"',
        "",
        "cxx_std = 20",
        f"include_dirs = {json.dumps(list(include_dirs))}",
        'defines = ["UNICODE", "_UNICODE"]',
        f"cflags = {json.dumps(list(cflags))}",
        "ldflags = []",
        "libs = []",
        "lib_dirs = []",
        "",
        "[profiles.debug]",
        'cflags = ["/Od", "/Zi"]',
        'defines = ["DEBUG"]',
        "ldflags = []",
        "",
        "[profiles.release]",
        'cflags = ["/O2"]',
        'defines = ["NDEBUG"]',
        "ldflags = []",
        "",
    ]


def _render_qt_block(classification: RepoClassification) -> list[str]:
    qt_tools_placeholder = bool(classification.qt_signal_count)
    qt_root = str(classification.qt_root or "").strip()
    if qt_root:
        moc = f"{qt_root}/bin/moc.exe"
        uic = f"{qt_root}/bin/uic.exe"
        rcc = f"{qt_root}/bin/rcc.exe"
    else:
        moc = "C:/Qt/6.6.0/msvc2019_64/bin/moc.exe" if qt_tools_placeholder else ""
        uic = "C:/Qt/6.6.0/msvc2019_64/bin/uic.exe" if qt_tools_placeholder else ""
        rcc = "C:/Qt/6.6.0/msvc2019_64/bin/rcc.exe" if qt_tools_placeholder else ""
    modules = list(classification.qt_modules) if classification.qt_enabled else []
    qt_include_dirs: list[str] = []
    qt_lib_dirs: list[str] = []
    qt_libs: list[str] = []
    if qt_root and classification.qt_enabled:
        qt_include_dirs.append(f"{qt_root}/include")
        for module in modules:
            qt_include_dirs.append(f"{qt_root}/include/Qt{module}")
            qt_libs.append(f"Qt6{module}")
        qt_lib_dirs.append(f"{qt_root}/lib")
    return [
        "[qt]",
        f"enabled = {'true' if classification.qt_enabled else 'false'}",
        f'qt_root = "{qt_root}"',
        f'prefix = "{qt_root}"',
        "version = 6",
        f"modules = {json.dumps(modules)}",
        f'moc_path = "{moc}"',
        f'uic_path = "{uic}"',
        f'rcc_path = "{rcc}"',
        f"include_dirs = {json.dumps(sorted(set(qt_include_dirs)))}",
        f"lib_dirs = {json.dumps(sorted(set(qt_lib_dirs)))}",
        f"libs = {json.dumps(sorted(set(qt_libs)))}",
        "",
    ]


def _render_ai_block() -> list[str]:
    return [
        "[ai]",
        "enabled = false",
        'plugin = ""',
        'mode = "advise"',
        "max_actions = 3",
        "log_tail_lines = 200",
        "redact_paths = true",
        "redact_env = true",
        "",
        "[ai.provider]",
        'model = ""',
        'endpoint = ""',
        'api_key_env = ""',
        "",
    ]


def _render_single_target(classification: RepoClassification) -> str:
    name = classification.default_target or "app"
    include_dirs = list(classification.include_dirs)
    libs = list(classification.libs)
    if classification.qt_enabled and classification.qt_root:
        qt_root = classification.qt_root
        include_dirs.extend([f"{qt_root}/include"] + [f"{qt_root}/include/Qt{m}" for m in classification.qt_modules])
        libs.extend([f"Qt6{m}" for m in classification.qt_modules])
    include_dirs = sorted(set(include_dirs))
    libs = sorted(set(libs))
    cflags = sorted(set(classification.cflags))
    lines = [
        f'# Auto-detected repo family: {classification.family}',
        f'name = "{name}"',
        'out_dir = "build"',
        f'target_type = "{classification.target_type}"',
        f"cxx_std = {17 if classification.qt_enabled else 20}",
        "",
        f"src_glob = {json.dumps(list(classification.source_globs))}",
        f"include_dirs = {json.dumps(include_dirs)}",
        'defines = ["UNICODE", "_UNICODE"]',
        f"cflags = {json.dumps(cflags)}",
        "ldflags = []",
        f"libs = {json.dumps(libs)}",
        "lib_dirs = []",
        'warnings = "default"',
        "",
        "[profiles.debug]",
        'cflags = ["/Od", "/Zi"]',
        'defines = ["DEBUG"]',
        "ldflags = []",
        "",
        "[profiles.release]",
        'cflags = ["/O2"]',
        'defines = ["NDEBUG"]',
        "ldflags = []",
        "",
    ]
    lines.extend(_render_qt_block(classification))
    lines.extend(_render_ai_block())
    return "\n".join(lines)


def _render_engine_multi_target(classification: RepoClassification) -> str:
    lines: list[str] = [f'# Auto-detected repo family: {classification.family}']
    lines.extend(_render_common_header(classification.include_dirs, classification.cflags))
    lines.extend([
        "[build]",
        f'default_target = "{classification.default_target}"',
        "",
        "[[targets]]",
        'name = "engine"',
        'type = "staticlib"',
        'src_glob = ["engine/**/*.cpp", "engine/**/*.c"]',
        f"include_dirs = {json.dumps(list(classification.include_dirs))}",
        'defines = ["UNICODE", "_UNICODE"]',
        "cflags = []",
        "libs = []",
        "lib_dirs = []",
        "ldflags = []",
        "cxx_std = 20",
        "links = []",
        "",
    ])
    for app_name in classification.app_names:
        lines.extend(
            [
                "[[targets]]",
                f'name = "{app_name}"',
                'type = "exe"',
                f'src_glob = ["apps/{app_name}/**/*.cpp", "apps/{app_name}/**/*.c"]',
                f"include_dirs = {json.dumps(list(classification.include_dirs))}",
                'defines = ["UNICODE", "_UNICODE"]',
                f"cflags = {json.dumps(list(classification.cflags))}",
                f"libs = {json.dumps(list(classification.libs))}",
                "lib_dirs = []",
                "ldflags = []",
                "cxx_std = 20",
                'links = ["engine"]',
                "",
            ]
        )
    lines.extend(_render_qt_block(classification))
    lines.extend(_render_ai_block())
    return "\n".join(lines)


def _render_native_multi_target(classification: RepoClassification) -> str:
    lines: list[str] = [f'# Auto-detected repo family: {classification.family}']
    lines.extend(_render_common_header(classification.include_dirs, classification.cflags))
    lines.extend([
        "[build]",
        f'default_target = "{classification.default_target}"',
        "",
    ])
    for app_name in classification.app_names:
        lines.extend(
            [
                "[[targets]]",
                f'name = "{app_name}"',
                'type = "exe"',
                f'src_glob = ["apps/{app_name}/**/*.cpp", "apps/{app_name}/**/*.c"]',
                f"include_dirs = {json.dumps(list(classification.include_dirs))}",
                'defines = ["UNICODE", "_UNICODE"]',
                f"cflags = {json.dumps(list(classification.cflags))}",
                f"libs = {json.dumps(list(classification.libs))}",
                "lib_dirs = []",
                "ldflags = []",
                "cxx_std = 20",
                "links = []",
                "",
            ]
        )
    lines.extend(_render_qt_block(classification))
    lines.extend(_render_ai_block())
    return "\n".join(lines)


def synthesize_init_toml(classification: RepoClassification) -> str:
    if classification.family == "engine-multi-target":
        return _render_engine_multi_target(classification)
    if classification.family == "native-multi-target":
        return _render_native_multi_target(classification)
    if classification.family in {"flutter-app", "juce-app", "qt-app", "native-single-target"}:
        return _render_single_target(classification)
    return _render_single_target(classification)
