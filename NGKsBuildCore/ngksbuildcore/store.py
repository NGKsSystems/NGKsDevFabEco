from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class StateStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._db_path = self._root / "state.sqlite"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS node_state (
                plan_path TEXT NOT NULL,
                node_id TEXT NOT NULL,
                input_signature TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(plan_path, node_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_state (
                node_id TEXT PRIMARY KEY,
                action_key TEXT NOT NULL,
                last_ok_utc TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def get_signature(self, plan_path: Path, node_id: str) -> str | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT input_signature FROM node_state WHERE plan_path=? AND node_id=?",
                (str(plan_path), node_id),
            )
            row = cur.fetchone()
        return None if row is None else str(row[0])

    def set_signature(self, plan_path: Path, node_id: str, signature: str, updated_at: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO node_state(plan_path, node_id, input_signature, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(plan_path, node_id) DO UPDATE SET
                    input_signature=excluded.input_signature,
                    updated_at=excluded.updated_at
                """,
                (str(plan_path), node_id, signature, updated_at),
            )
            self._conn.commit()

    def get_action_key(self, node_id: str) -> str | None:
        with self._lock:
            cur = self._conn.execute("SELECT action_key FROM action_state WHERE node_id=?", (node_id,))
            row = cur.fetchone()
        return None if row is None else str(row[0])

    def set_action_key(self, node_id: str, action_key: str, last_ok_utc: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO action_state(node_id, action_key, last_ok_utc)
                VALUES(?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    action_key=excluded.action_key,
                    last_ok_utc=excluded.last_ok_utc
                """,
                (node_id, action_key, last_ok_utc),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
