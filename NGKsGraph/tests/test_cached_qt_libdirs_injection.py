from ngksgraph.build import _apply_cached_target_overrides, _inject_qt_target_overrides
from ngksgraph.config import Config, QtConfig, TargetConfig


def test_cached_overrides_rehydrate_qt_libdirs_when_qt_libs_present() -> None:
    config = Config(
        targets=[
            TargetConfig(
                name="app",
                type="exe",
                src_glob=["src/**/*.cpp"],
                include_dirs=["src"],
                libs=["Qt6Core", "Qt6Gui", "Qt6Widgets"],
                lib_dirs=[],
            )
        ],
        qt=QtConfig(
            enabled=True,
            qt_root="C:/Qt/6.10.2/msvc2022_64",
            lib_dirs=["C:/Qt/6.10.2/msvc2022_64/lib"],
            libs=["Qt6Core", "Qt6Gui", "Qt6Widgets"],
        ),
    )
    config.normalize()

    cached_plan = {
        "target_overrides": {
            "app": {
                "include_dirs": [
                    "C:/Qt/6.10.2/msvc2022_64/include",
                    "C:/Qt/6.10.2/msvc2022_64/include/QtCore",
                    "C:/Qt/6.10.2/msvc2022_64/include/QtGui",
                    "C:/Qt/6.10.2/msvc2022_64/include/QtWidgets",
                    "src",
                ],
                "libs": ["Qt6Core", "Qt6Gui", "Qt6Widgets"],
            }
        }
    }

    _apply_cached_target_overrides(config, cached_plan)

    assert "C:/Qt/6.10.2/msvc2022_64/lib" in config.targets[0].lib_dirs


def test_qt_target_injection_adds_qt_libdirs_for_plan_context() -> None:
    config = Config(
        targets=[
            TargetConfig(
                name="app",
                type="exe",
                src_glob=["src/**/*.cpp"],
                include_dirs=["src"],
                libs=["Qt6Core", "Qt6Gui", "Qt6Widgets"],
                lib_dirs=[],
            )
        ],
        qt=QtConfig(
            enabled=True,
            qt_root="C:/Qt/6.10.2/msvc2022_64",
            include_dirs=["C:/Qt/6.10.2/msvc2022_64/include", "C:/Qt/6.10.2/msvc2022_64/include/QtCore"],
            lib_dirs=["C:/Qt/6.10.2/msvc2022_64/lib"],
            libs=["Qt6Core", "Qt6Gui", "Qt6Widgets"],
        ),
    )
    config.normalize()

    _inject_qt_target_overrides(config)

    target = config.targets[0]
    assert "C:/Qt/6.10.2/msvc2022_64/lib" in target.lib_dirs
    assert "Qt6Core" in target.libs
    assert "C:/Qt/6.10.2/msvc2022_64/include" in target.include_dirs
