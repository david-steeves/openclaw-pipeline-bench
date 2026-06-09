"""
Synthetic analyst skill: blocks a configurable percentage of payloads.

Models the worst-case operator policy: an active analyst that intercepts and rejects
some fraction of traffic. Block decision is deterministic per payload (hash-based) so
runs are reproducible.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import threading
import time


class BlockingAnalyst:
    NAME = "synthetic.blocking"

    def __init__(self, block_rate: float, cost_ms: int,
                 evidence_conn: sqlite3.Connection, evidence_lock: threading.Lock,
                 seam: str):
        if not 0.0 <= block_rate <= 1.0:
            raise ValueError(f"block_rate must be 0..1, got {block_rate!r}")
        self.block_rate = block_rate
        self.cost_s = cost_ms / 1000.0
        self.evidence_conn = evidence_conn
        self.evidence_lock = evidence_lock
        self.seam = seam

    def _write_evidence(self, verdict: str):
        with self.evidence_lock:
            self.evidence_conn.execute(
                "INSERT INTO evidence (seam, analyst, verdict, rule, ts) VALUES (?, ?, ?, ?, ?)",
                (self.seam, self.NAME, verdict, "policy/synthetic.block.v0", time.time()),
            )

    async def evaluate(self, agent_id: int, payload: str) -> str:
        await asyncio.sleep(self.cost_s)
        # Deterministic block decision per payload.
        h = int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)
        block = (h / 0xFFFFFFFF) < self.block_rate
        verdict = "block" if block else "pass"
        await asyncio.to_thread(self._write_evidence, verdict)
        return verdict
