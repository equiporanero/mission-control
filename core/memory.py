"""Shared memory layer — SQLite-backed state store with JSON envelope.

Every agent reads/writes through this module. The DB is WAL-mode so
concurrent readers never block, and writers serialize automatically.
"""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_local = threading.local()


class Memory:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(_local, "conn") or _local.conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            _local.conn = conn
        return _local.conn

    @contextmanager
    def _tx(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self):
        with self._tx() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kv (
                    ns    TEXT NOT NULL,
                    key   TEXT NOT NULL,
                    value TEXT NOT NULL,
                    ts    REAL NOT NULL,
                    PRIMARY KEY (ns, key)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id         TEXT PRIMARY KEY,
                    agent_id   TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    payload    TEXT NOT NULL,
                    status     TEXT NOT NULL DEFAULT 'pending',
                    result     TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts   REAL NOT NULL,
                    src  TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    data TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_agent  ON tasks(agent_id);
                CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
            """)

    # ── Key-Value store (namespaced) ──

    def put(self, ns: str, key: str, value: Any) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv (ns, key, value, ts) VALUES (?, ?, ?, ?)",
                (ns, key, json.dumps(value), time.time()),
            )

    def get(self, ns: str, key: str, default: Any = None) -> Any:
        row = self._get_conn().execute(
            "SELECT value FROM kv WHERE ns = ? AND key = ?", (ns, key)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    def list_ns(self, ns: str) -> dict[str, Any]:
        rows = self._get_conn().execute(
            "SELECT key, value FROM kv WHERE ns = ?", (ns,)
        ).fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def delete(self, ns: str, key: str) -> bool:
        with self._tx() as conn:
            cur = conn.execute("DELETE FROM kv WHERE ns = ? AND key = ?", (ns, key))
            return cur.rowcount > 0

    # ── Task queue ──

    def push_task(self, task_id: str, agent_id: str, kind: str, payload: Any) -> None:
        now = time.time()
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO tasks (id, agent_id, kind, payload, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (task_id, agent_id, kind, json.dumps(payload), now, now),
            )

    def claim_task(self, agent_id: str) -> dict | None:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE agent_id = ? AND status = 'pending' "
                "ORDER BY created_at LIMIT 1",
                (agent_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (time.time(), row["id"]),
            )
            return dict(row) | {"payload": json.loads(row["payload"])}

    def complete_task(self, task_id: str, result: Any, status: str = "done") -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                (status, json.dumps(result), time.time(), task_id),
            )

    def list_tasks(self, status: str | None = None, agent_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY created_at DESC"
        rows = self._get_conn().execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ── Event log (append-only) ──

    def emit(self, src: str, kind: str, data: Any = None) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO events (ts, src, kind, data) VALUES (?, ?, ?, ?)",
                (time.time(), src, kind, json.dumps(data or {})),
            )

    def events_since(self, since_ts: float, limit: int = 200) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT * FROM events WHERE ts > ? ORDER BY ts DESC LIMIT ?",
            (since_ts, limit),
        ).fetchall()
        return [dict(r) | {"data": json.loads(r["data"])} for r in rows]
