from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import tomllib

from ngksgraph.util import normalize_path, stable_unique_sorted


@dataclass
class QtConfig:
    enabled: bool = False
    qt_root: str = ""
    prefix: str = ""
    version: int = 6
    modules: list[str] = field(default_factory=list)
    moc_path: str = ""
    uic_path: str = ""
    rcc_path: str = ""
    include_dirs: list[str] = field(default_factory=list)
    lib_dirs: list[str] = field(default_factory=list)
    libs: list[str] = field(default_factory=list)


@dataclass
class AIProviderConfig:
    model: str = ""
    endpoint: str = ""
    api_key_env: str = ""


@dataclass
class AIConfig:
    enabled: bool = False
    plugin: str = ""
    mode: str = "advise"
    max_actions: int = 3
    log_tail_lines: int = 200
    redact_paths: bool = True
    redact_env: bool = True
    provider: AIProviderConfig = field(default_factory=AIProviderConfig)


@dataclass
class SnapshotConfig:
    enabled: bool = True
    keep: int = 10
    write_compdb: bool = True
    write_plan: bool = True
    write_config: bool = True


@dataclass
class ProfileConfig:
    cflags: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)

    def normalize(self) -> None:
        self.cflags = sorted(set(v.strip() for v in self.cflags if v.strip()))
        self.defines = sorted(set(v.strip() for v in self.defines if v.strip()))
        self.ldflags = sorted(set(v.strip() for v in self.ldflags if v.strip()))


@dataclass
class TargetConfig:
    name: str
    type: str = "exe"
    src_glob: list[str] = field(default_factory=lambda: ["src/**/*.cpp"])
    include_dirs: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    libs: list[str] = field(default_factory=list)
    lib_dirs: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    cxx_std: int = 20
    links: list[str] = field(default_factory=list)

    def normalize(self) -> None:
        self.src_glob = stable_unique_sorted(self.src_glob)
        self.include_dirs = stable_unique_sorted(self.include_dirs)
        self.defines = sorted(set(v.strip() for v in self.defines if v.strip()))
        self.cflags = sorted(set(v.strip() for v in self.cflags if v.strip()))
        self.libs = sorted(set(_normalize_lib_name(v) for v in self.libs if str(v).strip()))
        self.lib_dirs = stable_unique_sorted(self.lib_dirs)
        self.ldflags = sorted(set(v.strip() for v in self.ldflags if v.strip()))
        self.links = [v.strip() for v in self.links if v.strip()]
        if self.type not in {"exe", "staticlib"}:
            raise ValueError("target.type must be 'exe' or 'staticlib'.")


@dataclass
class Config:
    # global / legacy fields
    name: str = "app"
    out_dir: str = "build"
    target_type: str = "exe"
    cxx_std: int = 20
    src_glob: list[str] = field(default_factory=lambda: ["src/**/*.cpp"])
    include_dirs: list[str] = field(default_factory=lambda: ["include"])
    defines: list[str] = field(default_factory=lambda: ["UNICODE", "_UNICODE"])
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    libs: list[str] = field(default_factory=list)
    lib_dirs: list[str] = field(default_factory=list)
    warnings: str = "default"

    targets: list[TargetConfig] = field(default_factory=list)
    build_default_target: str = ""
    snapshots: SnapshotConfig = field(default_factory=SnapshotConfig)
    profiles: dict[str, ProfileConfig] = field(default_factory=dict)

    qt: QtConfig = field(default_factory=QtConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    def normalize(self) -> None:
        self.src_glob = stable_unique_sorted(self.src_glob)
        self.include_dirs = stable_unique_sorted(self.include_dirs)
        self.defines = sorted(set(v.strip() for v in self.defines if v.strip()))
        self.cflags = sorted(set(v.strip() for v in self.cflags if v.strip()))
        self.ldflags = sorted(set(v.strip() for v in self.ldflags if v.strip()))
        self.libs = sorted(set(_normalize_lib_name(v) for v in self.libs if str(v).strip()))
        self.lib_dirs = stable_unique_sorted(self.lib_dirs)
        self.qt.modules = sorted(set(v.strip() for v in self.qt.modules if v.strip()))
        self.qt.qt_root = normalize_path(self.qt.qt_root)
        self.qt.include_dirs = stable_unique_sorted(self.qt.include_dirs)
        self.qt.lib_dirs = stable_unique_sorted(self.qt.lib_dirs)
        self.qt.libs = sorted(set(_normalize_lib_name(v) for v in self.qt.libs if str(v).strip()))

        clean_profiles: dict[str, ProfileConfig] = {}
        for name, profile in self.profiles.items():
            key = str(name).strip()
            if not key:
                continue
            profile.normalize()
            clean_profiles[key] = profile
        self.profiles = dict(sorted(clean_profiles.items(), key=lambda kv: kv[0]))

        if not self.targets:
            self.targets = [
                TargetConfig(
                    name=self.name,
                    type=self.target_type,
                    src_glob=list(self.src_glob),
                    include_dirs=list(self.include_dirs),
                    defines=list(self.defines),
                    cflags=list(self.cflags),
                    libs=list(self.libs),
                    lib_dirs=list(self.lib_dirs),
                    ldflags=list(self.ldflags),
                    cxx_std=int(self.cxx_std),
                    links=[],
                )
            ]

        seen: set[str] = set()
        for target in self.targets:
            target.normalize()
            if target.name in seen:
                raise ValueError(f"Duplicate target name: {target.name}")
            seen.add(target.name)

        primary = self.targets[0]
        self.name = primary.name
        self.target_type = primary.type
        self.src_glob = list(primary.src_glob)
        self.include_dirs = list(primary.include_dirs)
        self.defines = list(primary.defines)
        self.cflags = list(primary.cflags)
        self.ldflags = list(primary.ldflags)
        self.libs = list(primary.libs)
        self.lib_dirs = list(primary.lib_dirs)
        self.cxx_std = int(primary.cxx_std)

        if self.ai.mode not in {"advise", "apply"}:
            raise ValueError("ai.mode must be 'advise' or 'apply'.")
        if self.ai.max_actions < 0:
            raise ValueError("ai.max_actions must be >= 0.")

        if self.build_default_target:
            if self.build_default_target not in {t.name for t in self.targets}:
                raise ValueError(f"build.default_target references unknown target: {self.build_default_target}")
        if self.snapshots.keep < 1:
            raise ValueError("snapshots.keep must be >= 1")

        if self.qt.enabled:
            has_qt_root = bool(str(self.qt.qt_root).strip())
            if not has_qt_root:
                missing = [
                    name
                    for name, value in [
                        ("qt.moc_path", self.qt.moc_path),
                        ("qt.uic_path", self.qt.uic_path),
                        ("qt.rcc_path", self.qt.rcc_path),
                    ]
                    if not str(value).strip()
                ]
                if missing:
                    raise ValueError(f"Qt enabled but required paths missing: {', '.join(missing)}")

    def get_target(self, name: str) -> TargetConfig:
        for target in self.targets:
            if target.name == name:
                return target
        raise KeyError(name)

    def exe_targets(self) -> list[TargetConfig]:
        return [t for t in self.targets if t.type == "exe"]

    def default_target_name(self) -> str:
        if not self.targets:
            self.normalize()
        if self.build_default_target:
            return self.build_default_target
        exe_targets = self.exe_targets()
        if len(exe_targets) == 1:
            return exe_targets[0].name
        if len(self.targets) == 1:
            return self.targets[0].name
        raise ValueError("No default target. Set [build].default_target or specify --target.")

    def as_sanitized_dict(self) -> dict[str, Any]:
        data = asdict(self)
        provider = data.get("ai", {}).get("provider", {})
        provider["api_key_env"] = ""
        return data

    def has_profiles(self) -> bool:
        return bool(self.profiles)

    def profile_names(self) -> list[str]:
        return sorted(self.profiles.keys())

    def get_default_profile(self) -> str:
        names = self.profile_names()
        if not names:
            return "default"
        if "debug" in names:
            return "debug"
        if "release" in names:
            return "release"
        return names[0]

    def apply_profile(self, profile: str | None) -> str:
        self.normalize()
        if not self.profiles:
            if profile and profile != "default":
                raise ValueError(f"Unknown profile '{profile}'. No profiles are defined in config.")
            return "default"

        if not profile:
            raise ValueError("Profiles are defined in config; --profile is required.")
        if profile not in self.profiles:
            known = ", ".join(self.profile_names())
            raise ValueError(f"Unknown profile '{profile}'. Known profiles: {known}")

        selected = self.profiles[profile]
        for target in self.targets:
            target.cflags = list(target.cflags) + list(selected.cflags)
            target.defines = list(target.defines) + list(selected.defines)
            target.ldflags = list(target.ldflags) + list(selected.ldflags)
            target.normalize()

        self.out_dir = normalize_path(Path(self.out_dir) / profile)

        primary = self.targets[0]
        self.cflags = list(primary.cflags)
        self.defines = list(primary.defines)
        self.ldflags = list(primary.ldflags)
        return profile


def _normalize_lib_name(value: str) -> str:
    clean = value.strip()
    if not clean:
        return clean
    if clean.lower().endswith(".lib"):
        clean = clean[:-4]
    return clean


def _as_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Expected list value in config.")
    return [str(v) for v in raw]


def _target_from_raw(raw: dict[str, Any], defaults: dict[str, Any]) -> TargetConfig:
    return TargetConfig(
        name=str(raw.get("name", "")).strip(),
        type=str(raw.get("type", defaults.get("type", "exe"))),
        src_glob=_as_list(raw.get("src_glob", defaults.get("src_glob", ["src/**/*.cpp"]))),
        include_dirs=_as_list(raw.get("include_dirs", defaults.get("include_dirs", []))),
        defines=_as_list(raw.get("defines", defaults.get("defines", []))),
        cflags=_as_list(raw.get("cflags", defaults.get("cflags", []))),
        libs=_as_list(raw.get("libs", defaults.get("libs", []))),
        lib_dirs=_as_list(raw.get("lib_dirs", defaults.get("lib_dirs", []))),
        ldflags=_as_list(raw.get("ldflags", defaults.get("ldflags", []))),
        cxx_std=int(raw.get("cxx_std", defaults.get("cxx_std", 20))),
        links=_as_list(raw.get("links", [])),
    )


def load_config(path: Path) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    qt_raw = raw.get("qt", {}) or {}
    ai_raw = raw.get("ai", {}) or {}
    provider_raw = ai_raw.get("provider", {}) or {}
    build_raw = raw.get("build", {}) or {}
    snapshots_raw = raw.get("snapshots", {}) or {}
    profiles_raw = raw.get("profiles", {}) or {}

    parsed_profiles: dict[str, ProfileConfig] = {}
    if isinstance(profiles_raw, dict):
        for name, body in profiles_raw.items():
            if not isinstance(body, dict):
                continue
            parsed_profiles[str(name)] = ProfileConfig(
                cflags=_as_list(body.get("cflags", [])),
                defines=_as_list(body.get("defines", [])),
                ldflags=_as_list(body.get("ldflags", [])),
            )

    cfg = Config(
        name=str(raw.get("name", "app")),
        out_dir=str(raw.get("out_dir", "build")),
        target_type=str(raw.get("target_type", "exe")),
        cxx_std=int(raw.get("cxx_std", 20)),
        src_glob=_as_list(raw.get("src_glob", ["src/**/*.cpp"])),
        include_dirs=_as_list(raw.get("include_dirs", ["include"])),
        defines=_as_list(raw.get("defines", ["UNICODE", "_UNICODE"])),
        cflags=_as_list(raw.get("cflags", [])),
        ldflags=_as_list(raw.get("ldflags", [])),
        libs=_as_list(raw.get("libs", [])),
        lib_dirs=_as_list(raw.get("lib_dirs", [])),
        warnings=str(raw.get("warnings", "default")),
        build_default_target=str(build_raw.get("default_target", "")),
        snapshots=SnapshotConfig(
            enabled=bool(snapshots_raw.get("enabled", True)),
            keep=int(snapshots_raw.get("keep", 10)),
            write_compdb=bool(snapshots_raw.get("write_compdb", True)),
            write_plan=bool(snapshots_raw.get("write_plan", True)),
            write_config=bool(snapshots_raw.get("write_config", True)),
        ),
        profiles=parsed_profiles,
        qt=QtConfig(
            enabled=bool(qt_raw.get("enabled", False)),
            qt_root=str(qt_raw.get("qt_root", "")),
            prefix=str(qt_raw.get("prefix", "")),
            version=int(qt_raw.get("version", 6)),
            modules=_as_list(qt_raw.get("modules", [])),
            moc_path=str(qt_raw.get("moc_path", "")),
            uic_path=str(qt_raw.get("uic_path", "")),
            rcc_path=str(qt_raw.get("rcc_path", "")),
            include_dirs=_as_list(qt_raw.get("include_dirs", [])),
            lib_dirs=_as_list(qt_raw.get("lib_dirs", [])),
            libs=_as_list(qt_raw.get("libs", [])),
        ),
        ai=AIConfig(
            enabled=bool(ai_raw.get("enabled", False)),
            plugin=str(ai_raw.get("plugin", "")),
            mode=str(ai_raw.get("mode", "advise")),
            max_actions=int(ai_raw.get("max_actions", 3)),
            log_tail_lines=int(ai_raw.get("log_tail_lines", 200)),
            redact_paths=bool(ai_raw.get("redact_paths", True)),
            redact_env=bool(ai_raw.get("redact_env", True)),
            provider=AIProviderConfig(
                model=str(provider_raw.get("model", "")),
                endpoint=str(provider_raw.get("endpoint", "")),
                api_key_env=str(provider_raw.get("api_key_env", "")),
            ),
        ),
    )

    defaults = {
        "type": cfg.target_type,
        "src_glob": list(cfg.src_glob),
        "include_dirs": list(cfg.include_dirs),
        "defines": list(cfg.defines),
        "cflags": list(cfg.cflags),
        "libs": list(cfg.libs),
        "lib_dirs": list(cfg.lib_dirs),
        "ldflags": list(cfg.ldflags),
        "cxx_std": int(cfg.cxx_std),
    }

    targets_raw = raw.get("targets", []) or []
    if targets_raw:
        cfg.targets = []
        for item in targets_raw:
            target = _target_from_raw(item or {}, defaults)
            if not target.name:
                raise ValueError("Each [[targets]] entry must define a non-empty name.")
            cfg.targets.append(target)
    else:
        cfg.targets = []

    cfg.normalize()
    return cfg


def save_config(path: Path, config: Config) -> None:
    config.normalize()

    def list_str(items: list[str]) -> str:
        return "[" + ", ".join(f'\"{item}\"' for item in items) + "]"

    lines = [
        f'out_dir = "{config.out_dir}"',
        f'warnings = "{config.warnings}"',
        "",
        f'cxx_std = {config.cxx_std}',
        f"include_dirs = {list_str(config.include_dirs)}",
        f"defines = {list_str(config.defines)}",
        f"cflags = {list_str(config.cflags)}",
        f"ldflags = {list_str(config.ldflags)}",
        f"libs = {list_str(config.libs)}",
        f"lib_dirs = {list_str(config.lib_dirs)}",
        "",
    ]

    if config.build_default_target:
        lines.extend(
            [
                "[build]",
                f'default_target = "{config.build_default_target}"',
                "",
            ]
        )

    lines.extend(
        [
            "[snapshots]",
            f"enabled = {str(config.snapshots.enabled).lower()}",
            f"keep = {config.snapshots.keep}",
            f"write_compdb = {str(config.snapshots.write_compdb).lower()}",
            f"write_plan = {str(config.snapshots.write_plan).lower()}",
            f"write_config = {str(config.snapshots.write_config).lower()}",
            "",
        ]
    )

    for profile_name in sorted(config.profiles.keys()):
        profile = config.profiles[profile_name]
        lines.extend(
            [
                f"[profiles.{profile_name}]",
                f"cflags = {list_str(profile.cflags)}",
                f"defines = {list_str(profile.defines)}",
                f"ldflags = {list_str(profile.ldflags)}",
                "",
            ]
        )

    for target in config.targets:
        lines.extend(
            [
                "[[targets]]",
                f'name = "{target.name}"',
                f'type = "{target.type}"',
                f"src_glob = {list_str(target.src_glob)}",
                f"include_dirs = {list_str(target.include_dirs)}",
                f"defines = {list_str(target.defines)}",
                f"cflags = {list_str(target.cflags)}",
                f"libs = {list_str(target.libs)}",
                f"lib_dirs = {list_str(target.lib_dirs)}",
                f"ldflags = {list_str(target.ldflags)}",
                f"cxx_std = {target.cxx_std}",
                f"links = {list_str(target.links)}",
                "",
            ]
        )

    lines.extend(
        [
            "[qt]",
            f"enabled = {str(config.qt.enabled).lower()}",
            f'qt_root = "{normalize_path(config.qt.qt_root)}"',
            f'prefix = "{normalize_path(config.qt.prefix)}"',
            f"version = {config.qt.version}",
            f"modules = {list_str(config.qt.modules)}",
            f'moc_path = "{normalize_path(config.qt.moc_path)}"',
            f'uic_path = "{normalize_path(config.qt.uic_path)}"',
            f'rcc_path = "{normalize_path(config.qt.rcc_path)}"',
            f"include_dirs = {list_str(config.qt.include_dirs)}",
            f"lib_dirs = {list_str(config.qt.lib_dirs)}",
            f"libs = {list_str(config.qt.libs)}",
            "",
            "[ai]",
            f"enabled = {str(config.ai.enabled).lower()}",
            f'plugin = "{config.ai.plugin}"',
            f'mode = "{config.ai.mode}"',
            f"max_actions = {config.ai.max_actions}",
            f"log_tail_lines = {config.ai.log_tail_lines}",
            f"redact_paths = {str(config.ai.redact_paths).lower()}",
            f"redact_env = {str(config.ai.redact_env).lower()}",
            "",
            "[ai.provider]",
            f'model = "{config.ai.provider.model}"',
            f'endpoint = "{config.ai.provider.endpoint}"',
            f'api_key_env = "{config.ai.provider.api_key_env}"',
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
