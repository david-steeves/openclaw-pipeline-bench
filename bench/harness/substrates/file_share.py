"""
File-share substrate — one append-only JSONL per agent under /workspace.

Models OpenClaw's current shape: each claw writes to its own file inside a shared
workspace directory. No pipeline, no seams, no analyst surface.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections import deque
from pathlib import Path


class FileShareSubstrate:
    def __init__(self, in_memory: bool = False, root: str | None = None):
        # in_memory=True means "use a tempdir on the host's default tmp" — not an
        # in-process StringIO. The actual baseline must exercise the OS file path,
        # otherwise we measure StringIO not file-share.
        if in_memory:
            self._tmpdir = tempfile.TemporaryDirectory(prefix="bench-baseline-")
            self.root = Path(self._tmpdir.name)
        else:
            self._tmpdir = None
            self.root = Path(root or os.environ.get("WORKSPACE_ROOT", "/workspace"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._files: dict[int, any] = {}
        self._read_back_cache: dict[int, deque] = {}

    def _file_for(self, agent_id: int):
        if agent_id not in self._files:
            path = self.root / f"agent-{agent_id}.jsonl"
            self._files[agent_id] = open(path, "a", buffering=1)
            self._read_back_cache[agent_id] = deque(maxlen=5)
        return self._files[agent_id]

    async def emit(self, agent_id: int, payload: str) -> dict:
        f = self._file_for(agent_id)
        # File I/O is sync; offload to thread to keep the event loop responsive.
        await asyncio.to_thread(self._write_and_flush, f, payload)
        self._read_back_cache[agent_id].append(payload)
        # Simulate read-back (matches workload spec: each agent reads last N events).
        _ = list(self._read_back_cache[agent_id])
        return {"verdict": "pass"}

    @staticmethod
    def _write_and_flush(f, payload: str):
        f.write(payload + "\n")
        if hasattr(f, "flush"):
            f.flush()
        if hasattr(f, "fileno"):
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # in-memory file-like

    async def close(self):
        for f in self._files.values():
            if hasattr(f, "close"):
                f.close()
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
