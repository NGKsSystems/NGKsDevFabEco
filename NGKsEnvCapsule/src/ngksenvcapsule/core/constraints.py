from __future__ import annotations

from .types import Constraint


def _norm(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _strategy(section: dict, default: str) -> str:
    value = str(section.get("strategy", default)).strip().lower()
    if value not in {"prefer", "require", "off"}:
        raise ValueError(f"Invalid strategy: {value}")
    return value


def parse_constraints_from_config(config_dict: dict) -> dict[str, Constraint]:
    python_section = dict(config_dict.get("python", {}))
    node_section = dict(config_dict.get("node", {}))
    msvc_section = dict(config_dict.get("msvc", {}))
    windows_sdk_section = dict(config_dict.get("windows_sdk", {}))

    constraints = {
        "python": Constraint(
            strategy=_strategy(python_section, "prefer"),
            version=_norm(python_section.get("required")),
            min_version=_norm(python_section.get("min_version")),
            identity=_norm(python_section.get("identity")),
            arch=_norm(python_section.get("arch")),
            channel=_norm(python_section.get("channel")),
        ),
        "node": Constraint(
            strategy=_strategy(node_section, "off"),
            version=_norm(node_section.get("required")),
            min_version=_norm(node_section.get("min_version")),
            identity=_norm(node_section.get("identity")),
            arch=_norm(node_section.get("arch")),
            channel=_norm(node_section.get("channel")),
        ),
        "msvc": Constraint(
            strategy=_strategy(msvc_section, "prefer"),
            version=_norm(msvc_section.get("required")),
            min_version=_norm(msvc_section.get("min_version")),
            identity=_norm(msvc_section.get("identity")),
            arch=_norm(msvc_section.get("arch", "x64")),
            channel=_norm(msvc_section.get("channel")),
        ),
        "windows_sdk": Constraint(
            strategy=_strategy(windows_sdk_section, "prefer"),
            version=_norm(windows_sdk_section.get("required")),
            min_version=_norm(windows_sdk_section.get("min_version")),
            identity=_norm(windows_sdk_section.get("identity")),
            arch=_norm(windows_sdk_section.get("arch")),
            channel=_norm(windows_sdk_section.get("channel")),
        ),
    }
    return constraints
