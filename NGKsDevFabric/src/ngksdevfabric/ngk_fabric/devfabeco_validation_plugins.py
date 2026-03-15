from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


class ValidationPlugin(ABC):
    plugin_name = "validation_plugin"
    plugin_version = "0.0.0"
    plugin_category = "GENERIC"

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}
        self.inputs: dict[str, Any] = {}
        self.analysis: dict[str, Any] = {}

    @abstractmethod
    def load_inputs(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def run_analysis(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def generate_artifacts(self, output_dir: Path) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def generate_summary(self) -> str:
        raise NotImplementedError
