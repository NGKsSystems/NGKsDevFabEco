from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ProviderPolicy:
    strategy: str
    required: str = ""
    min_version: str = ""
    arch: str = ""


@dataclass(frozen=True)
class CapsuleConfig:
    path: str
    exists: bool
    version: int
    python: ProviderPolicy
    node: ProviderPolicy
    msvc: ProviderPolicy
    windows_sdk: ProviderPolicy

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "python": {
                "strategy": self.python.strategy,
                "required": self.python.required,
                "min_version": self.python.min_version,
                "arch": self.python.arch,
            },
            "node": {
                "strategy": self.node.strategy,
                "required": self.node.required,
                "min_version": self.node.min_version,
                "arch": self.node.arch,
            },
            "msvc": {
                "strategy": self.msvc.strategy,
                "required": self.msvc.required,
                "min_version": self.msvc.min_version,
                "arch": self.msvc.arch,
            },
            "windows_sdk": {
                "strategy": self.windows_sdk.strategy,
                "required": self.windows_sdk.required,
                "min_version": self.windows_sdk.min_version,
                "arch": self.windows_sdk.arch,
            },
        }


def _policy(section: dict, default_strategy: str) -> ProviderPolicy:
    strategy = str(section.get("strategy", default_strategy)).strip().lower()
    if strategy not in {"prefer", "require", "off"}:
        raise ValueError(f"Invalid strategy: {strategy}")
    return ProviderPolicy(
        strategy=strategy,
        required=str(section.get("required", "")).strip(),
        min_version=str(section.get("min_version", "")).strip(),
        arch=str(section.get("arch", "")).strip(),
    )


def load_config(config_path: str | None = None) -> CapsuleConfig:
    path = Path(config_path or "ngksenvcapsule.toml")
    if not path.exists():
        return CapsuleConfig(
            path=str(path),
            exists=False,
            version=1,
            python=ProviderPolicy("prefer"),
            node=ProviderPolicy("off"),
            msvc=ProviderPolicy("prefer", arch="x64"),
            windows_sdk=ProviderPolicy("prefer"),
        )

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    version = int(data.get("version", 1))
    if version != 1:
        raise ValueError("Config version must be 1")
    return CapsuleConfig(
        path=str(path),
        exists=True,
        version=version,
        python=_policy(data.get("python", {}), "prefer"),
        node=_policy(data.get("node", {}), "off"),
        msvc=_policy(data.get("msvc", {}), "prefer"),
        windows_sdk=_policy(data.get("windows_sdk", {}), "prefer"),
    )
