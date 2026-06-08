"""
Synthetic analyst skill: always emits `pass`.

Models the cost of a registered analyst that does its work (classification, redaction,
schema check) and concludes the payload is safe to advance. Cost is configurable in ms.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time


class PassAnalyst:
    NAME = "synthetic.pass"

    def __init__(self, cost_ms: int, evidence_conn: sqlite3.Connection, seam: str):
        self.cost_s = cost_ms / 1000.0
        self.evidence_conn = evidence_conn
        self.seam = seam

    async def evaluate(self, agent_id: int, payload: str) -> str:
        # Simulate analysis cost.
        await asyncio.sleep(self.cost_s)
        # Emit redacted evidence (RFC 0003 shape: seam, analyst, verdict, rule — no payload).
        await asyncio.to_thread(
            self.evidence_conn.execute,
            "INSERT INTO evidence (seam, analyst, verdict, rule, ts) VALUES (?, ?, ?, ?, ?)",
            (self.seam, self.NAME, "pass", "policy/synthetic.pass.v0", time.time()),
        )
        return "pass"
