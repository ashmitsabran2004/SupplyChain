"""SQLite persistence for scored telemetry ticks, indexed by timestamp."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class TickStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticks (
                ts TEXT NOT NULL,
                node_id TEXT NOT NULL,
                delay_probability REAL NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (ts, node_id)
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(ts)")
        self._conn.commit()

    def insert_many(self, rows: list[tuple[str, str, float, dict[str, Any]]]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO ticks(ts, node_id, delay_probability, payload) VALUES (?,?,?,?)",
            [(ts, nid, p, json.dumps(payload)) for ts, nid, p, payload in rows],
        )
        self._conn.commit()

    def timestamps(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT ts FROM ticks ORDER BY ts").fetchall()
        return [r[0] for r in rows]

    def at(self, ts: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT node_id, delay_probability, payload FROM ticks WHERE ts = ?",
            (ts,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for node_id, p, payload in rows:
            body = json.loads(payload)
            body["node_id"] = node_id
            body["delay_probability"] = p
            out.append(body)
        return out

    def snapshot_range(self) -> dict[str, Any]:
        ts = self.timestamps()
        return {"timestamps": ts, "count": len(ts)}
