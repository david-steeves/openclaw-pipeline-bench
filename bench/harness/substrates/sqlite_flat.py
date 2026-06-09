"""
SQLite-flat substrate — single SQLite database, single `items` table.

No pipeline, no stages, no analysts. This variant exists to separate two effects
that pipeline-noop conflates:

    file-append (baseline)  -->  SQLite single-table (sqlite-flat)  -->  3-stage pipeline (pipeline-noop)

If sqlite-flat is close to baseline and pipeline-noop is much higher, the cost
is the 3-stage shape. If sqlite-flat is already at pipeline-noop's level, the
cost is just SQLite vs raw file I/O. Either answer is useful — but conflating
the two would mislead the RFC reader.

Same pragmas as the pipeline substrate (WAL, synchronous=NORMAL, temp_store=MEMORY,
cache_size=64 MiB) so the comparison is apples-to-apples at the engine level.
Same read-back window as file_share so per-agent work matches.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import threading
import time
from collections import deque
from pathlib import Path


def _open_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            payload TEXT NOT NULL,
            ts REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_agent ON items(agent_id, id DESC)")
    return conn


class SqliteFlatSubstrate:
    def __init__(self, in_memory: bool = False, root: str | None = None,
                 read_back_window: int = 5):
        if in_memory:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="bench-flat-")
            root_dir = Path(self._tmpdir.name)
        else:
            self._tmpdir = None
            root_dir = Path(root or os.environ.get("FLAT_ROOT", "/data"))
            root_dir.mkdir(parents=True, exist_ok=True)

        self._conn = _open_db(root_dir / "items.db")
        self._lock = threading.Lock()
        self._read_back_window = read_back_window

    async def emit(self, agent_id: int, payload: str) -> dict:
        # Single insert + read-back of last N for this agent — mirrors file_share's per-agent
        # read-back so the workload shape is identical at the substrate level.
        await asyncio.to_thread(self._insert_and_read_back, agent_id, payload)
        return {"verdict": "pass"}

    def _insert_and_read_back(self, agent_id: int, payload: str):
        with self._lock:
            self._conn.execute(
                "INSERT INTO items (agent_id, payload, ts) VALUES (?, ?, ?)",
                (agent_id, payload, time.time()),
            )
            cur = self._conn.execute(
                "SELECT payload FROM items WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
                (agent_id, self._read_back_window),
            )
            _ = cur.fetchall()

    async def close(self):
        self._conn.close()
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
