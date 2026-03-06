from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLogger:
    def __init__(self, proof_dir: Path, console_verbose: bool = True) -> None:
        self.proof_dir = proof_dir
        self.proof_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.proof_dir / "events.jsonl"
        self.commands_path = self.proof_dir / "commands.jsonl"
        self._events_handle = self.events_path.open("a", encoding="utf-8", newline="\n")
        self._commands_handle = self.commands_path.open("a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()
        self.console_verbose = console_verbose

    def emit(self, event_type: str, **payload: Any) -> None:
        evt = {"ts": utc_now_iso(), "event": event_type, **payload}
        line = json.dumps(evt, ensure_ascii=True)
        with self._lock:
            self._events_handle.write(line + "\n")
            self._events_handle.flush()

    def command(self, **payload: Any) -> None:
        row = {"ts": utc_now_iso(), **payload}
        line = json.dumps(row, ensure_ascii=True)
        with self._lock:
            self._commands_handle.write(line + "\n")
            self._commands_handle.flush()

    def print(self, message: str) -> None:
        if self.console_verbose:
            print(message, flush=True)

    def close(self) -> None:
        with self._lock:
            self._events_handle.close()
            self._commands_handle.close()
