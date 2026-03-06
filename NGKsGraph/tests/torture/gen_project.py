from __future__ import annotations

from dataclasses import dataclass
import random
import sys
from pathlib import Path

from ngksgraph.config import Config, TargetConfig, save_config
from ngksgraph.util import normalize_path, rel_path


@dataclass
class GeneratedProject:
    repo_root: Path
    config_path: Path
    qt_paths: dict[str, str]
    qobject_headers: list[str]
    ui_files: list[str]
    qrc_files: list[str]
    qrc_referenced_files: list[str]
    unrelated_files: list[str]


def _write_fake_qt_tools(repo_root: Path, with_spaces: bool = False) -> dict[str, str]:
    tools_dir = repo_root / ("build tools" if with_spaces else "build_tools")
    tools_dir.mkdir(parents=True, exist_ok=True)

    impl = tools_dir / "qt_tool_impl.py"
    impl.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import hashlib",
                "import sys",
                "from pathlib import Path",
                "",
                "def _usage():",
                "    raise SystemExit(2)",
                "",
                "def main():",
                "    if len(sys.argv) < 3:",
                "        _usage()",
                "    mode = sys.argv[1]",
                "    if sys.argv[2] == '-v':",
                "        print(f'{mode} torture-fake 1.0.0')",
                "        return 0",
                "    if len(sys.argv) < 5 or sys.argv[3] != '-o':",
                "        _usage()",
                "    input_path = Path(sys.argv[2])",
                "    output_path = Path(sys.argv[4])",
                "    output_path.parent.mkdir(parents=True, exist_ok=True)",
                "    inp = input_path.read_bytes() if input_path.exists() else b''",
                "    h = hashlib.sha256(inp).hexdigest()",
                "    output_path.write_text(f'// {mode} generated\\n// input={input_path.name}\\n// hash={h}\\n', encoding='utf-8')",
                "    return 0",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        ),
        encoding="utf-8",
    )

    paths: dict[str, str] = {}
    for mode in ["moc", "uic", "rcc"]:
        cmd = tools_dir / f"{mode}.cmd"
        cmd.write_text(
            "\n".join(
                [
                    "@echo off",
                    f'"{sys.executable}" "{impl}" {mode} %*',
                ]
            ),
            encoding="utf-8",
        )
        paths[f"{mode}_path"] = normalize_path(cmd.resolve())

    return paths


def _mixed_slash(value: str, token: int) -> str:
    text = normalize_path(value)
    if token % 2 == 0:
        return text
    return text.replace("/", "\\")


def _apply_mixed_slashes_to_config(cfg_path: Path, seed: int) -> None:
    lines = cfg_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    token = seed
    for line in lines:
        if "= [" in line and "\"" in line:
            prefix, values = line.split("=", 1)
            parts = values.strip()
            if parts.startswith("[") and parts.endswith("]"):
                raw_items = [v.strip() for v in parts[1:-1].split(",") if v.strip()]
                cooked: list[str] = []
                for item in raw_items:
                    if item.startswith('"') and item.endswith('"'):
                        payload = item[1:-1].replace('\\\\', '\\')
                        if any(x in payload for x in ["/", "\\"]):
                            payload = _mixed_slash(payload, token)
                            token += 1
                        payload = payload.replace('\\', '\\\\')
                        cooked.append(f'"{payload}"')
                    else:
                        cooked.append(item)
                out.append(f"{prefix.strip()} = [{', '.join(cooked)}]")
                continue
        if 'path = "' in line:
            left, right = line.split('"', 1)
            payload, tail = right.rsplit('"', 1)
            payload = _mixed_slash(payload, token)
            token += 1
            payload = payload.replace('\\', '\\\\')
            out.append(f'{left}"{payload}"{tail}')
            continue
        out.append(line)
    cfg_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def gen_project(
    base_dir: Path,
    *,
    seed: int,
    path_with_spaces: bool = False,
    mixed_slashes: bool = False,
    large_scale: bool = False,
    qobject_headers: int = 16,
    ui_files: int = 2,
    qrc_files: int = 1,
    include_tree_depth: int = 3,
    duplicate_basenames: bool = False,
    ambiguous_ownership: bool = False,
) -> GeneratedProject:
    rnd = random.Random(seed)

    project_name = "Qt Torture Repo" if path_with_spaces else "qt_torture_repo"
    repo_root = (base_dir / project_name).resolve()
    repo_root.mkdir(parents=True, exist_ok=True)

    qt_paths = _write_fake_qt_tools(repo_root, with_spaces=path_with_spaces)

    src_root = repo_root / "src"
    (src_root / "core").mkdir(parents=True, exist_ok=True)
    (src_root / "util").mkdir(parents=True, exist_ok=True)
    (src_root / "app").mkdir(parents=True, exist_ok=True)

    (src_root / "core" / "core.cpp").write_text("int core_fn(){return 7;}\n", encoding="utf-8")
    (src_root / "util" / "util.cpp").write_text("int util_fn(){return 11;}\n", encoding="utf-8")

    app_cpp_dir = src_root / "app" / ("space dir" if path_with_spaces else "main")
    app_cpp_dir.mkdir(parents=True, exist_ok=True)
    (app_cpp_dir / "app_main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")

    header_count = 200 if large_scale else qobject_headers
    header_count = max(header_count, 0)

    qobject_paths: list[Path] = []
    include_root = src_root / "app" / "include"
    for idx in range(header_count):
        branch = [f"lvl{(idx + j) % max(include_tree_depth, 1)}" for j in range(max(include_tree_depth, 1))]
        folder = include_root
        for token in branch:
            folder = folder / token
        folder.mkdir(parents=True, exist_ok=True)
        hdr = folder / f"Widget{idx:04d}.hpp"
        hdr.write_text(f"class Widget{idx:04d} {{ Q_OBJECT }};\n", encoding="utf-8")
        qobject_paths.append(hdr)

    if duplicate_basenames:
        left = include_root / "dupA"
        right = include_root / "dupB"
        left.mkdir(parents=True, exist_ok=True)
        right.mkdir(parents=True, exist_ok=True)
        lhs = left / "EngineBridge.hpp"
        rhs = right / "EngineBridge.hpp"
        lhs.write_text("class EngineBridgeA { Q_OBJECT };\n", encoding="utf-8")
        rhs.write_text("class EngineBridgeB { Q_OBJECT };\n", encoding="utf-8")
        qobject_paths.extend([lhs, rhs])

    ui_paths: list[Path] = []
    ui_root = src_root / "app" / "ui"
    ui_root.mkdir(parents=True, exist_ok=True)
    for idx in range(max(ui_files, 0)):
        ui = ui_root / f"screen_{idx:03d}.ui"
        ui.write_text("<ui version=\"4.0\"><class>Form</class></ui>\n", encoding="utf-8")
        ui_paths.append(ui)

    qrc_paths: list[Path] = []
    qrc_refs: list[Path] = []
    res_root = src_root / "app" / "resources"
    res_root.mkdir(parents=True, exist_ok=True)
    for idx in range(max(qrc_files, 0)):
        nested = res_root / f"bundle_{idx}" / "deep" / "leaf"
        nested.mkdir(parents=True, exist_ok=True)
        assets: list[Path] = []
        for j in range(3):
            asset = nested / f"asset_{idx}_{j}.txt"
            asset.write_text(f"seed={seed},idx={idx},j={j},rnd={rnd.randint(0, 10_000)}\n", encoding="utf-8")
            assets.append(asset)
        qrc = src_root / "app" / f"resources_{idx:03d}.qrc"
        files_xml = "\n".join(
            f"    <file>{rel_path(p, qrc.parent)}</file>" for p in sorted(assets, key=lambda p: normalize_path(p))
        )
        qrc.write_text(f"<RCC>\n  <qresource>\n{files_xml}\n  </qresource>\n</RCC>\n", encoding="utf-8")
        qrc_paths.append(qrc)
        qrc_refs.extend(assets)

    unrelated = src_root / "docs" / "unrelated.txt"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    unrelated.write_text("unrelated\n", encoding="utf-8")

    shared_glob = ["src/shared/**/*.cpp"] if ambiguous_ownership else []
    if ambiguous_ownership:
        shared = src_root / "shared"
        shared.mkdir(parents=True, exist_ok=True)
        (shared / "shared_conflict.cpp").write_text("int shared_conflict(){return 1;}\n", encoding="utf-8")

    cfg = Config(
        out_dir="build",
        targets=[
            TargetConfig(name="core", type="staticlib", src_glob=["src/core/**/*.cpp"] + shared_glob),
            TargetConfig(name="util", type="staticlib", src_glob=["src/util/**/*.cpp"] + shared_glob, links=["core"]),
            TargetConfig(name="app", type="exe", src_glob=["src/app/**/*.cpp"], links=["util"]),
        ],
        build_default_target="app",
    )
    cfg.qt.enabled = True
    cfg.qt.moc_path = qt_paths["moc_path"]
    cfg.qt.uic_path = qt_paths["uic_path"]
    cfg.qt.rcc_path = qt_paths["rcc_path"]
    cfg.qt.include_dirs = ["C:/Qt/include", "C:/Qt/include/QtCore"]
    cfg.qt.lib_dirs = ["C:/Qt/lib"]
    cfg.qt.libs = ["Qt6Core.lib", "Qt6Widgets.lib"]

    cfg_path = repo_root / "ngksgraph.toml"
    save_config(cfg_path, cfg)

    if mixed_slashes:
        _apply_mixed_slashes_to_config(cfg_path, seed)

    return GeneratedProject(
        repo_root=repo_root,
        config_path=cfg_path,
        qt_paths=qt_paths,
        qobject_headers=sorted(rel_path(p, repo_root) for p in qobject_paths),
        ui_files=sorted(rel_path(p, repo_root) for p in ui_paths),
        qrc_files=sorted(rel_path(p, repo_root) for p in qrc_paths),
        qrc_referenced_files=sorted(rel_path(p, repo_root) for p in qrc_refs),
        unrelated_files=[rel_path(unrelated, repo_root)],
    )
