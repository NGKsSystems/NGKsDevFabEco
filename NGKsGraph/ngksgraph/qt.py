from __future__ import annotations

from dataclasses import dataclass
import json
import re
import subprocess
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from ngksgraph.config import Config
from ngksgraph.hashutil import sha256_json
from ngksgraph.util import normalize_path, rel_path, sha256_file


@dataclass
class QtGeneratorNode:
    kind: str
    target: str
    input: str
    output: str
    status: str
    reason: str
    tool_path: str
    tool_hash: str
    tool_version: str
    fingerprint: str

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "reason": self.reason,
            "tool_path": self.tool_path,
            "tool_hash": self.tool_hash,
            "tool_version": self.tool_version,
            "fingerprint": self.fingerprint,
        }


@dataclass
class QtIntegrationResult:
    generator_nodes: list[QtGeneratorNode]
    generated_files: list[str]
    include_injected: list[str]
    lib_dirs_injected: list[str]
    libs_injected: list[str]
    tool_info: dict[str, dict[str, str]]

    def trace_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "qt.enabled": bool(self.generator_nodes or self.include_injected or self.libs_injected),
            "qt.moc.generated": [],
            "qt.moc.skipped": [],
            "qt.uic.generated": [],
            "qt.uic.skipped": [],
            "qt.rcc.generated": [],
            "qt.rcc.skipped": [],
            "qt.generator.reason": [],
            "qt.generator.tool_hash": {},
            "qt.include.injected": list(self.include_injected),
            "qt.lib.injected": {
                "lib_dirs": list(self.lib_dirs_injected),
                "libs": list(self.libs_injected),
            },
        }
        for node in self.generator_nodes:
            key = f"qt.{node.kind}.{node.status}"
            out.setdefault(key, []).append(node.output)
            out["qt.generator.reason"].append({"output": node.output, "reason": node.reason})
            out["qt.generator.tool_hash"][node.output] = node.tool_hash
        return out


def _qt_modules_from_libs(libs: list[str]) -> list[str]:
    modules: set[str] = set()
    for lib in libs:
        item = str(lib).strip()
        if not item:
            continue
        item = item[:-4] if item.lower().endswith(".lib") else item
        if item.startswith("Qt6") or item.startswith("Qt5"):
            mod = item[3:]
            if mod.endswith("d"):
                mod = mod[:-1]
            if mod:
                modules.add(mod)
    return sorted(modules)


def resolve_qt_toolchain(config: Config, check_exists: bool = True) -> dict[str, Any]:
    config.normalize()
    qt = config.qt
    if not qt.enabled:
        return {"qt_enabled": False}

    notes: list[str] = []
    resolved_root = Path(qt.qt_root) if str(qt.qt_root).strip() else None
    if resolved_root is not None:
        resolved_root = resolved_root.resolve()
        if check_exists and not resolved_root.exists():
            raise FileNotFoundError(f"Qt root not found: {resolved_root}")

        qt.qt_root = normalize_path(resolved_root)
        bin_dir = resolved_root / "bin"
        include_dir = resolved_root / "include"
        lib_dir = resolved_root / "lib"

        if not str(qt.moc_path).strip():
            qt.moc_path = normalize_path((bin_dir / "moc.exe").resolve())
            notes.append("resolved.moc_path.from_qt_root")
        if not str(qt.uic_path).strip():
            qt.uic_path = normalize_path((bin_dir / "uic.exe").resolve())
            notes.append("resolved.uic_path.from_qt_root")
        if not str(qt.rcc_path).strip():
            qt.rcc_path = normalize_path((bin_dir / "rcc.exe").resolve())
            notes.append("resolved.rcc_path.from_qt_root")

        if not qt.lib_dirs:
            qt.lib_dirs = [normalize_path(lib_dir.resolve())]
            notes.append("resolved.lib_dirs.from_qt_root")

        modules = sorted(set(qt.modules) | set(_qt_modules_from_libs(qt.libs)))
        if not qt.modules and modules:
            qt.modules = modules

        if not qt.include_dirs:
            includes = [normalize_path(include_dir.resolve())]
            for mod in modules:
                candidate = include_dir / f"Qt{mod}"
                includes.append(normalize_path(candidate.resolve()))
            qt.include_dirs = sorted(set(includes))
            notes.append("resolved.include_dirs.from_qt_root")

    for p in ["moc_path", "uic_path", "rcc_path"]:
        val = str(getattr(qt, p, "")).strip()
        if not val:
            continue
        setattr(qt, p, normalize_path(Path(val).resolve()))

    qt.include_dirs = sorted(set(normalize_path(Path(v).resolve()) for v in qt.include_dirs))
    qt.lib_dirs = sorted(set(normalize_path(Path(v).resolve()) for v in qt.lib_dirs))

    tool_paths = {
        "moc": Path(qt.moc_path) if str(qt.moc_path).strip() else None,
        "uic": Path(qt.uic_path) if str(qt.uic_path).strip() else None,
        "rcc": Path(qt.rcc_path) if str(qt.rcc_path).strip() else None,
    }
    if check_exists:
        missing = [name for name, p in tool_paths.items() if p is None or not p.exists()]
        if missing:
            raise FileNotFoundError(f"Qt tools missing: {', '.join(missing)}")

    return {
        "qt_enabled": True,
        "qt_root": qt.qt_root,
        "resolved": {
            "moc_path": qt.moc_path,
            "uic_path": qt.uic_path,
            "rcc_path": qt.rcc_path,
            "include_dirs": list(qt.include_dirs),
            "lib_dirs": list(qt.lib_dirs),
            "libs": list(qt.libs),
        },
        "notes": notes,
    }


def _tool_version(path: Path) -> str:
    proc = subprocess.run([str(path), "-v"], capture_output=True, text=True, shell=False)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise RuntimeError(f"Qt tool failed version query: {path} ({proc.returncode})")
    return out.splitlines()[0].strip() if out else ""


def _ensure_qt_tools(config: Config) -> dict[str, dict[str, str]]:
    tools = {
        "moc": Path(config.qt.moc_path),
        "uic": Path(config.qt.uic_path),
        "rcc": Path(config.qt.rcc_path),
    }
    info: dict[str, dict[str, str]] = {}
    for name, path in tools.items():
        if not path.exists():
            raise FileNotFoundError(f"Qt enabled but tool missing: {name} at {path}")
        info[name] = {
            "path": normalize_path(path.resolve()),
            "sha256": sha256_file(path),
            "version": _tool_version(path),
        }
    return info


def _pattern_root(pattern: str) -> str:
    wildcard_pos = len(pattern)
    for token in ["*", "?", "["]:
        idx = pattern.find(token)
        if idx != -1:
            wildcard_pos = min(wildcard_pos, idx)
    root = pattern[:wildcard_pos].rstrip("/\\")
    return root or "."


def _target_scope_roots(repo_root: Path, src_glob: list[str]) -> list[Path]:
    roots = []
    seen = set()
    for pattern in src_glob:
        root = (repo_root / _pattern_root(pattern)).resolve()
        n = normalize_path(root)
        if n in seen:
            continue
        seen.add(n)
        roots.append(root)
    return sorted(roots, key=lambda p: normalize_path(p))


def _collect_headers_ui_qrc(repo_root: Path, roots: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    headers: set[Path] = set()
    uis: set[Path] = set()
    qrcs: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in {".h", ".hpp", ".hh", ".hxx"}:
                headers.add(path)
            elif suffix == ".ui":
                uis.add(path)
            elif suffix == ".qrc":
                qrcs.add(path)
    return (
        sorted(headers, key=lambda p: normalize_path(p)),
        sorted(uis, key=lambda p: normalize_path(p)),
        sorted(qrcs, key=lambda p: normalize_path(p)),
    )


def _contains_q_object(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "Q_OBJECT" in text


def _qrc_referenced_files(qrc_file: Path) -> list[Path]:
    try:
        tree = ET.fromstring(qrc_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    out: set[Path] = set()
    base = qrc_file.parent
    for elem in tree.iter("file"):
        if elem.text:
            p = (base / elem.text.strip()).resolve()
            if p.exists() and p.is_file():
                out.add(p)
    return sorted(out, key=lambda p: normalize_path(p))


def _unique_output_path(
    qt_out_dir: Path,
    prefix: str,
    input_path: Path,
    ext: str,
    seen: set[str],
    repo_root: Path,
) -> Path:
    base = f"{prefix}{input_path.stem}{ext}"
    out = qt_out_dir / base
    n = normalize_path(out)
    if n in seen:
        rel = rel_path(input_path, repo_root)
        suffix = sha256_json({"input": normalize_path(rel)})[:10]
        base = f"{prefix}{input_path.stem}__{suffix}{ext}"
        out = qt_out_dir / base
        n = normalize_path(out)
        if n in seen:
            raise ValueError(f"Qt generated output collision: {base}")
    seen.add(n)
    return out


def _run_generator(cmd: list[str], output: Path) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if proc.returncode != 0:
        body = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        raise RuntimeError(f"Qt generator failed ({proc.returncode}): {' '.join(cmd)}\n{body}")
    if not output.exists():
        raise RuntimeError(f"Qt generator did not produce output: {output}")


def _node_fingerprint(
    kind: str,
    input_file: Path,
    referenced_files: list[Path],
    tool_hash: str,
    tool_version: str,
    args: list[str],
) -> str:
    payload = {
        "kind": kind,
        "input": sha256_file(input_file),
        "referenced": [{"path": normalize_path(p), "hash": sha256_file(p)} for p in referenced_files],
        "tool_hash": tool_hash,
        "tool_version": tool_version,
        "args": args,
    }
    return sha256_json(payload)


def _fingerprint_file(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".fingerprint.json")


def _maybe_generate(
    kind: str,
    target_name: str,
    tool_path: Path,
    tool_hash: str,
    tool_version: str,
    input_file: Path,
    output_file: Path,
    args: list[str],
    referenced_files: list[Path] | None = None,
) -> QtGeneratorNode:
    refs = referenced_files or []
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fp = _node_fingerprint(kind, input_file, refs, tool_hash, tool_version, args)
    fp_file = _fingerprint_file(output_file)

    reason = "qt.generator.reason.unchanged"
    status = "skipped"

    should_generate = True
    if output_file.exists() and fp_file.exists():
        try:
            prev = json.loads(fp_file.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
        if prev.get("fingerprint") == fp:
            should_generate = False

    if should_generate:
        _run_generator(args, output_file)
        fp_file.write_text(json.dumps({"fingerprint": fp}, indent=2, sort_keys=True), encoding="utf-8")
        reason = "qt.generator.reason.fingerprint_changed"
        status = "generated"

    return QtGeneratorNode(
        kind=kind,
        target=target_name,
        input=normalize_path(input_file),
        output=normalize_path(output_file),
        status=status,
        reason=reason,
        tool_path=normalize_path(tool_path),
        tool_hash=tool_hash,
        tool_version=tool_version,
        fingerprint=fp,
    )


def integrate_qt(repo_root: Path, config: Config, source_map: dict[str, list[str]], out_dir: Path, profile: str = "") -> QtIntegrationResult:
    config.normalize()
    if not config.qt.enabled:
        return QtIntegrationResult([], [], [], [], [], {})

    resolve_qt_toolchain(config, check_exists=True)

    tool_info = _ensure_qt_tools(config)
    qt_out_dir = out_dir / "qt"

    include_injected = sorted(set(config.qt.include_dirs + [normalize_path(qt_out_dir)]))
    lib_dirs_injected = sorted(set(config.qt.lib_dirs))

    is_debug = profile.lower() == "debug"
    raw_libs = [v[:-4] if v.lower().endswith(".lib") else v for v in config.qt.libs]
    if is_debug:
        # Qt debug DLLs have a 'd' suffix (Qt6Xxxd.dll). Append it so the linker
        # selects Qt6Xxxd.lib and the runtime resolves Qt6Xxxd.dll, not the release DLL.
        processed_libs = [
            name + "d" if (name.startswith("Qt") and not name.endswith("d")) else name
            for name in raw_libs
        ]
    else:
        processed_libs = raw_libs
    libs_injected = sorted(set(processed_libs))

    for target in config.targets:
        target.include_dirs = sorted(set(target.include_dirs + include_injected))
        target.lib_dirs = sorted(set(target.lib_dirs + lib_dirs_injected))
        target.libs = sorted(set(target.libs + libs_injected))

    nodes: list[QtGeneratorNode] = []
    generated_files: set[str] = set()
    seen_outputs: set[str] = set()

    for target in config.targets:
        roots = _target_scope_roots(repo_root, target.src_glob)
        headers, uis, qrcs = _collect_headers_ui_qrc(repo_root, roots)

        for header in headers:
            if not _contains_q_object(header):
                continue
            out_cpp = _unique_output_path(qt_out_dir, "moc_", header, ".cpp", seen_outputs, repo_root)
            node = _maybe_generate(
                kind="moc",
                target_name=target.name,
                tool_path=Path(config.qt.moc_path),
                tool_hash=tool_info["moc"]["sha256"],
                tool_version=tool_info["moc"]["version"],
                input_file=header,
                output_file=out_cpp,
                args=[str(config.qt.moc_path), str(header), "-o", str(out_cpp)],
            )
            nodes.append(node)
            source_map[target.name].append(rel_path(out_cpp, repo_root))
            generated_files.add(rel_path(out_cpp, repo_root))

        for ui in uis:
            out_h = _unique_output_path(qt_out_dir, "ui_", ui, ".h", seen_outputs, repo_root)
            node = _maybe_generate(
                kind="uic",
                target_name=target.name,
                tool_path=Path(config.qt.uic_path),
                tool_hash=tool_info["uic"]["sha256"],
                tool_version=tool_info["uic"]["version"],
                input_file=ui,
                output_file=out_h,
                args=[str(config.qt.uic_path), str(ui), "-o", str(out_h)],
            )
            nodes.append(node)
            generated_files.add(rel_path(out_h, repo_root))

        for qrc in qrcs:
            out_cpp = _unique_output_path(qt_out_dir, "qrc_", qrc, ".cpp", seen_outputs, repo_root)
            refs = _qrc_referenced_files(qrc)
            node = _maybe_generate(
                kind="rcc",
                target_name=target.name,
                tool_path=Path(config.qt.rcc_path),
                tool_hash=tool_info["rcc"]["sha256"],
                tool_version=tool_info["rcc"]["version"],
                input_file=qrc,
                output_file=out_cpp,
                args=[str(config.qt.rcc_path), str(qrc), "-o", str(out_cpp)],
                referenced_files=refs,
            )
            nodes.append(node)
            source_map[target.name].append(rel_path(out_cpp, repo_root))
            generated_files.add(rel_path(out_cpp, repo_root))

    for target_name in list(source_map.keys()):
        source_map[target_name] = sorted(set(source_map[target_name]))

    return QtIntegrationResult(
        generator_nodes=nodes,
        generated_files=sorted(generated_files),
        include_injected=include_injected,
        lib_dirs_injected=lib_dirs_injected,
        libs_injected=libs_injected,
        tool_info=tool_info,
    )
