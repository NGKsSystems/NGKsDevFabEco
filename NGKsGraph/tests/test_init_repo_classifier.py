from __future__ import annotations

from pathlib import Path

from ngksgraph.cli import main


def test_init_autodetects_native_single_target_exe(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    assert main(["init"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: native-single-target' in cfg_text
    assert 'target_type = "exe"' in cfg_text
    assert '[qt]' in cfg_text
    assert 'enabled = false' in cfg_text


def test_init_autodetects_native_single_target_staticlib_when_no_entrypoint(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "core.cpp").write_text("int core(){return 1;}\n", encoding="utf-8")

    assert main(["init"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: native-single-target' in cfg_text
    assert 'target_type = "staticlib"' in cfg_text


def test_init_autodetects_engine_multi_target_and_prefers_widget_sandbox(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "engine" / "core" / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "engine" / "core" / "src" / "core.cpp").write_text("int core(){return 0;}\n", encoding="utf-8")
    for app_name in ["alpha", "widget_sandbox", "zeta"]:
        (tmp_path / "apps" / app_name).mkdir(parents=True, exist_ok=True)
        (tmp_path / "apps" / app_name / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    assert main(["init"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: engine-multi-target' in cfg_text
    assert 'name = "engine"' in cfg_text
    assert 'name = "alpha"' in cfg_text
    assert 'name = "widget_sandbox"' in cfg_text
    assert 'default_target = "widget_sandbox"' in cfg_text


def test_init_autodetects_qt_when_ui_and_qobject_signals_present(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text(
        "#include <QApplication>\n#include <QMainWindow>\nint main(int argc, char** argv){QApplication app(argc, argv); return 0;}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "mainwindow.hpp").write_text(
        "#pragma once\n#include <QObject>\nclass MainWindow : public QObject { Q_OBJECT };\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "mainwindow.ui").write_text("<ui version=\"4.0\"></ui>\n", encoding="utf-8")

    assert main(["init"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: qt-app' in cfg_text
    assert '[qt]' in cfg_text
    assert 'enabled = true' in cfg_text
    assert 'modules = ["Core", "Gui", "Widgets"]' in cfg_text
    assert 'moc_path = "' in cfg_text
    assert 'uic_path = "' in cfg_text
    assert 'rcc_path = "' in cfg_text


def test_init_filevisionary_style_qlineedit_signal_not_misclassified(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "main.cpp").write_text(
        "#include <QLineEdit>\n#include <QApplication>\nint main(int argc, char** argv){QApplication app(argc, argv); return 0;}\n",
        encoding="utf-8",
    )

    assert main(["init", "--force"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: qt-app' in cfg_text
    assert 'enabled = true' in cfg_text
    assert 'target_type = "exe"' in cfg_text
    assert 'cflags = ["/Zc:__cplusplus", "/permissive-"]' in cfg_text
    assert 'cxx_std = 17' in cfg_text


def test_init_autodetects_flutter_repo_layout(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "windows" / "runner").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pubspec.yaml").write_text(
        "name: sample_app\n"
        "description: sample\n"
        "environment:\n"
        "  sdk: '>=3.0.0 <4.0.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
        encoding="utf-8",
    )
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
    (tmp_path / "windows" / "runner" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    assert main(["init", "--force"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: flutter-app' in cfg_text
    assert 'name = "flutter_runner"' in cfg_text
    assert 'target_type = "exe"' in cfg_text
    assert 'enabled = false' in cfg_text


def test_init_autodetects_juce_repo_signals(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Source").mkdir(parents=True, exist_ok=True)
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.22)\n"
        "project(JuceApp)\n"
        "juce_add_gui_app(JuceApp)\n",
        encoding="utf-8",
    )
    (tmp_path / "Source" / "Main.cpp").write_text(
        "#include <JuceHeader.h>\n"
        "int main(){return 0;}\n",
        encoding="utf-8",
    )

    assert main(["init", "--force"]) == 0
    cfg_text = (tmp_path / "ngksgraph.toml").read_text(encoding="utf-8")

    assert '# Auto-detected repo family: juce-app' in cfg_text
    assert 'name = "juce_app"' in cfg_text
    assert 'target_type = "exe"' in cfg_text
    assert 'cflags = ["/Zc:__cplusplus", "/permissive-"]' in cfg_text
