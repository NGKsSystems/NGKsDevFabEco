from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from ngksgraph.config import Config, ProfileConfig, QtConfig, TargetConfig, save_config


_SCOPE_WORDS = {"PRIVATE", "PUBLIC", "INTERFACE"}
_LIB_KINDS = {"STATIC", "SHARED", "MODULE", "OBJECT", "INTERFACE", "UNKNOWN"}


@dataclass
class ImportedTarget:
    name: str
    type: str
    src_glob: list[str] = field(default_factory=list)
    include_dirs: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    libs: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)


@dataclass
class CMakeModel:
    project_name: str = "app"
    cxx_std: int = 20
    qt_modules: set[str] = field(default_factory=set)
    targets: dict[str, ImportedTarget] = field(default_factory=dict)


def _strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if "#" in line:
            line = line.split("#", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def _iter_calls(text: str) -> list[tuple[str, str]]:
    clean = _strip_comments(text)
    pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
    calls: list[tuple[str, str]] = []
    pos = 0
    while True:
        match = pattern.search(clean, pos)
        if not match:
            break
        name = match.group(1).strip().lower()
        index = match.end()
        depth = 1
        start = index
        while index < len(clean) and depth > 0:
            char = clean[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            body = clean[start : index - 1]
            calls.append((name, body))
        pos = index
    return calls


def _tokenize(body: str) -> list[str]:
    return shlex.split(body.replace("\n", " "), posix=True)


def _expand_token(token: str, variables: dict[str, list[str]]) -> list[str]:
    var_match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", token)
    if not var_match:
        return [token]
    return list(variables.get(var_match.group(1), []))


def _expand_tokens(tokens: list[str], variables: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        out.extend(_expand_token(token, variables))
    return out


def _normalize_src_list(items: list[str], fallback: str) -> list[str]:
    cleaned = [v.replace("\\", "/") for v in items if v and not v.startswith("$<")]
    if not cleaned:
        return [fallback]
    return sorted(set(cleaned))


def parse_cmake(cmake_path: Path) -> CMakeModel:
    text = cmake_path.read_text(encoding="utf-8")
    calls = _iter_calls(text)
    variables: dict[str, list[str]] = {}
    model = CMakeModel(project_name=cmake_path.parent.name or "app")

    for name, body in calls:
        tokens = _tokenize(body)
        if not tokens:
            continue

        if name == "project":
            model.project_name = tokens[0]
            continue

        if name == "set" and len(tokens) >= 2:
            key = tokens[0]
            values = _expand_tokens(tokens[1:], variables)
            variables[key] = values
            continue

        if name == "set_property" and "CXX_STANDARD" in [t.upper() for t in tokens]:
            for token in tokens:
                if token.isdigit():
                    model.cxx_std = int(token)
            continue

        if name == "add_executable":
            target_name = tokens[0]
            srcs = _expand_tokens(tokens[1:], variables)
            model.targets[target_name] = ImportedTarget(
                name=target_name,
                type="exe",
                src_glob=_normalize_src_list(srcs, "src/**/*.cpp"),
            )
            continue

        if name == "add_library":
            target_name = tokens[0]
            start_idx = 1
            if len(tokens) > 1 and tokens[1].upper() in _LIB_KINDS:
                start_idx = 2
            srcs = _expand_tokens(tokens[start_idx:], variables)
            model.targets[target_name] = ImportedTarget(
                name=target_name,
                type="staticlib",
                src_glob=_normalize_src_list(srcs, "src/**/*.cpp"),
            )
            continue

        if len(tokens) < 2:
            continue

        target_name = tokens[0]
        if target_name not in model.targets:
            continue
        target = model.targets[target_name]

        values = _expand_tokens(tokens[1:], variables)
        values = [v for v in values if v.upper() not in _SCOPE_WORDS and not v.startswith("$<")]

        if name == "target_include_directories":
            target.include_dirs.extend(v.replace("\\", "/") for v in values)
        elif name == "target_compile_definitions":
            target.defines.extend(values)
        elif name == "target_compile_options":
            target.cflags.extend(values)
        elif name == "target_link_options":
            target.ldflags.extend(values)
        elif name == "target_link_libraries":
            for item in values:
                qt_match = re.fullmatch(r"Qt\d+::([A-Za-z0-9_]+)", item)
                if qt_match:
                    model.qt_modules.add(qt_match.group(1))
                    continue
                if item in model.targets:
                    target.links.append(item)
                else:
                    target.libs.append(item)

    std_match = re.search(r"CMAKE_CXX_STANDARD\s+([0-9]+)", _strip_comments(text), flags=re.IGNORECASE)
    if std_match:
        model.cxx_std = int(std_match.group(1))

    return model


def _to_config(model: CMakeModel) -> Config:
    imported_targets: list[TargetConfig] = []
    for name in sorted(model.targets.keys()):
        src = model.targets[name]
        imported_targets.append(
            TargetConfig(
                name=src.name,
                type=src.type,
                src_glob=sorted(set(src.src_glob)) or ["src/**/*.cpp"],
                include_dirs=sorted(set(src.include_dirs)),
                defines=sorted(set(src.defines)),
                cflags=sorted(set(src.cflags)),
                libs=sorted(set(src.libs)),
                lib_dirs=[],
                ldflags=sorted(set(src.ldflags)),
                cxx_std=int(model.cxx_std),
                links=sorted(set(src.links)),
            )
        )

    if not imported_targets:
        imported_targets = [
            TargetConfig(
                name=model.project_name or "app",
                type="exe",
                src_glob=["src/**/*.cpp"],
                include_dirs=["include"],
                defines=["UNICODE", "_UNICODE"],
                cxx_std=int(model.cxx_std),
            )
        ]

    exe_names = [t.name for t in imported_targets if t.type == "exe"]
    default_target = exe_names[0] if exe_names else imported_targets[0].name

    return Config(
        name=default_target,
        out_dir="build",
        cxx_std=int(model.cxx_std),
        include_dirs=["include"],
        defines=["UNICODE", "_UNICODE"],
        targets=imported_targets,
        build_default_target=default_target,
        profiles={
            "debug": ProfileConfig(cflags=["/Od", "/Zi"], defines=["DEBUG"], ldflags=[]),
            "release": ProfileConfig(cflags=["/O2"], defines=["NDEBUG"], ldflags=[]),
        },
        qt=QtConfig(
            enabled=bool(model.qt_modules),
            prefix="",
            version=6,
            modules=sorted(model.qt_modules),
            moc_path="C:/Qt/6.6.0/msvc2019_64/bin/moc.exe" if model.qt_modules else "",
            uic_path="C:/Qt/6.6.0/msvc2019_64/bin/uic.exe" if model.qt_modules else "",
            rcc_path="C:/Qt/6.6.0/msvc2019_64/bin/rcc.exe" if model.qt_modules else "",
        ),
    )


def import_cmake_project(cmake_path: Path, out_path: Path) -> Path:
    model = parse_cmake(cmake_path)
    config = _to_config(model)
    save_config(out_path, config)
    return out_path
