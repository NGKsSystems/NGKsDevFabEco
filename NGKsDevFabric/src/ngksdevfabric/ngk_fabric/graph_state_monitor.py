from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from .devfabeco_orchestrator import ensure_graph_state_current
from .graph_state_manager import mark_graph_state_dirty_if_changed


class GraphStateMonitor:
    def __init__(
        self,
        *,
        project_root: Path,
        pf: Path,
        poll_seconds: float = 2.0,
        on_refresh: Callable[[dict], None] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.pf = pf.resolve()
        self.poll_seconds = max(0.5, float(poll_seconds))
        self.on_refresh = on_refresh
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            state = ensure_graph_state_current(project_root=self.project_root, pf=self.pf)
            mark_graph_state_dirty_if_changed(
                project_root=self.project_root,
                active_profile="debug",
                active_target="watcher",
                graph_artifact_root=self.pf / "20_graph_auto_refresh_watcher",
            )
            if bool(state.get("changed_since_last", False)) and self.on_refresh is not None:
                self.on_refresh(state)
            self._stop.wait(self.poll_seconds)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="graph-state-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_seconds * 2))


def start_background_graph_monitor(
    *,
    project_root: Path,
    pf: Path,
    poll_seconds: float = 2.0,
    max_cycles: int = 0,
) -> int:
    monitor = GraphStateMonitor(project_root=project_root, pf=pf, poll_seconds=poll_seconds)
    monitor.start()
    try:
        if max_cycles <= 0:
            while True:
                time.sleep(poll_seconds)
        else:
            for _ in range(max_cycles):
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
    return 0
