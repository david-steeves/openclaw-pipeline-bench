"""
SQLite-fullcopy substrate — three-stage pipeline with real read+copy+delete promotion.

Difference from `sqlite_pipeline.py` (which is now the "lower-bound" variant):

    sqlite_pipeline.py  ──>  INSERT into raw  ──>  INSERT into processed  ──>  INSERT into curated
                              (payload passed forward in-process; no SELECT or DELETE)

    sqlite_fullcopy.py  ──>  INSERT into raw, capture rowid
                              for each seam (raw→processed, processed→curated):
                                  SELECT row from source     (under source lock)
                                  INSERT row into dest        (under dest lock)
                                  DELETE row from source      (under source lock)
                              (rows do NOT accumulate in the source stage)

This is the "upper bound" — what a faithful medallion promotion would actually cost
per event: 3 inserts + 2 selects + 2 deletes, plus analyst hooks and evidence stamps.

The cross-DB promotion is not a single distributed transaction (would need ATTACH or
2PC) — we measure the I/O cost shape, not the atomicity guarantees a real impl would
add on top. That's the same approximation `sqlite_pipeline.py` makes; the variable
we're isolating here is read+delete cost, not transactional guarantees.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from harness.analysts.pass_analyst import PassAnalyst
from harness.analysts.blocking_analyst import BlockingAnalyst


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
    return conn


def _open_evidence(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seam TEXT NOT NULL,
            analyst TEXT NOT NULL,
            verdict TEXT NOT NULL,
            rule TEXT,
            ts REAL NOT NULL
        )
    """)
    return conn


class SqliteFullCopySubstrate:
    def __init__(self, stages: list[str], analysts: list[dict],
                 in_memory: bool = False, root: str | None = None):
        self.stages = stages or ["raw", "processed", "curated"]
        if in_memory:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="bench-fullcopy-")
            root_dir = Path(self._tmpdir.name)
        else:
            self._tmpdir = None
            root_dir = Path(root or os.environ.get("PIPELINE_ROOT", "/data"))
            root_dir.mkdir(parents=True, exist_ok=True)

        def db_path(name: str) -> str:
            return str(root_dir / f"{name}.db")

        self._conns = {stage: _open_db(db_path(stage)) for stage in self.stages}
        self._locks = {stage: threading.Lock() for stage in self.stages}
        self._evidence = _open_evidence(db_path("evidence"))
        self._evidence_lock = threading.Lock()

        self._seam_analysts: dict[str, list] = {}
        for spec in analysts:
            seam = spec["seam"]
            if spec.get("verdict") == "conditional_block":
                analyst = BlockingAnalyst(
                    block_rate=spec.get("block_rate", 0.05),
                    cost_ms=spec.get("cost_ms", 1),
                    evidence_conn=self._evidence,
                    evidence_lock=self._evidence_lock,
                    seam=seam,
                )
            else:
                analyst = PassAnalyst(
                    cost_ms=spec.get("cost_ms", 1),
                    evidence_conn=self._evidence,
                    evidence_lock=self._evidence_lock,
                    seam=seam,
                )
            self._seam_analysts.setdefault(seam, []).append(analyst)

    def _stage_pair_seam(self, src: str, dst: str) -> str:
        return f"{src}_to_{dst}"

    async def emit(self, agent_id: int, payload: str) -> dict:
        # Ingress: INSERT into raw, capture rowid so we can promote it.
        current_id = await asyncio.to_thread(self._insert, "raw", agent_id, payload)

        for i in range(len(self.stages) - 1):
            src, dst = self.stages[i], self.stages[i + 1]
            seam = self._stage_pair_seam(src, dst)

            for analyst in self._seam_analysts.get(seam, []):
                verdict = await analyst.evaluate(agent_id, payload)
                if verdict == "block":
                    # Blocked at seam — row stays in src (matches real medallion behavior).
                    return {"verdict": "block", "seam": seam}

            if not self._seam_analysts.get(seam):
                await asyncio.to_thread(self._stamp_empty, seam)

            # Full promotion: SELECT row from src → INSERT into dst → DELETE from src.
            current_id = await asyncio.to_thread(self._promote, src, dst, current_id)

        return {"verdict": "pass"}

    def _insert(self, stage: str, agent_id: int, payload: str) -> int:
        with self._locks[stage]:
            cur = self._conns[stage].execute(
                "INSERT INTO items (agent_id, payload, ts) VALUES (?, ?, ?)",
                (agent_id, payload, time.time()),
            )
            return cur.lastrowid

    def _promote(self, src: str, dst: str, row_id: int) -> int:
        # Read from source.
        with self._locks[src]:
            row = self._conns[src].execute(
                "SELECT agent_id, payload, ts FROM items WHERE id = ?",
                (row_id,),
            ).fetchone()
        if row is None:
            # Shouldn't happen — the row was just inserted. Defensive.
            return row_id
        agent_id, payload, ts = row
        # Write to dest.
        with self._locks[dst]:
            cur = self._conns[dst].execute(
                "INSERT INTO items (agent_id, payload, ts) VALUES (?, ?, ?)",
                (agent_id, payload, ts),
            )
            new_id = cur.lastrowid
        # Delete from source.
        with self._locks[src]:
            self._conns[src].execute("DELETE FROM items WHERE id = ?", (row_id,))
        return new_id

    def _stamp_empty(self, seam: str):
        with self._evidence_lock:
            self._evidence.execute(
                "INSERT INTO evidence (seam, analyst, verdict, rule, ts) VALUES (?, ?, ?, ?, ?)",
                (seam, "<none>", "<empty-stamp>", None, time.time()),
            )

    async def close(self):
        for c in self._conns.values():
            c.close()
        self._evidence.close()
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
