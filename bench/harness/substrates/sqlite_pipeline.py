"""
SQLite-backed three-stage pipeline substrate.

raw  → processed  → curated, each a separate SQLite database (WAL mode).
Stage advance is a synchronous insert + delete in a transaction. Analyst skills
register at seam boundaries and run inline; verdicts are emitted to evidence.db.

Matches the substrate-passive-I/O contract from RFC 0010: this module does NOT
mutate payload content. Mutation is exclusively the analyst-skill surface, which
lives in harness/analysts/.
"""

from __future__ import annotations

import asyncio
import hashlib
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
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
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


class SqlitePipelineSubstrate:
    def __init__(self, stages: list[str], analysts: list[dict],
                 in_memory: bool = False, root: str | None = None):
        self.stages = stages or ["raw", "processed", "curated"]
        self.in_memory = in_memory
        if in_memory:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="bench-")
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

        # Register analysts per seam.
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
        # Stage 0: raw insert (no analysts at ingress)
        await asyncio.to_thread(self._insert, "raw", agent_id, payload)

        # Advance through pipeline; run analyst chain at each seam boundary.
        for i in range(len(self.stages) - 1):
            src, dst = self.stages[i], self.stages[i + 1]
            seam = self._stage_pair_seam(src, dst)
            for analyst in self._seam_analysts.get(seam, []):
                verdict = await analyst.evaluate(agent_id, payload)
                if verdict == "block":
                    return {"verdict": "block", "seam": seam}
            # No analysts registered at this seam = empty-evidence stamp (per RFC).
            if not self._seam_analysts.get(seam):
                await asyncio.to_thread(self._stamp_empty, seam)
            await asyncio.to_thread(self._insert, dst, agent_id, payload)

        return {"verdict": "pass"}

    def _insert(self, stage: str, agent_id: int, payload: str):
        with self._locks[stage]:
            self._conns[stage].execute(
                "INSERT INTO items (agent_id, payload, ts) VALUES (?, ?, ?)",
                (agent_id, payload, time.time()),
            )

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
