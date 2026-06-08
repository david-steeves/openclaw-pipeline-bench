"""
openclaw-pipeline-bench — workload runner

Single async harness shared across all 4 variants. The substrate is the variable;
the workload is invariant. This is intentional — see specs/2026-06-08-pipeline-bench-design.md.

USAGE (inside container):
    python -m harness.runner --variant <id> --duration <seconds> --output <path>

USAGE (smoke test, no docker):
    python -m harness.runner --variant pipeline-noop --duration 10 --in-memory

The container ENTRYPOINT passes --variant via $BENCH_VARIANT_ID.
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil  # rss sampling
import yaml    # manifest


@dataclass
class WorkloadConfig:
    agents: int
    events_per_agent_per_sec: int
    event_payload_bytes: int
    read_back_window: int
    warmup_seconds: int
    steady_state_seconds: int


@dataclass
class VariantConfig:
    id: str
    substrate: str            # "file_share" | "sqlite"
    pipeline_stages: list[str]
    analysts: list[dict[str, Any]] = field(default_factory=list)


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    with open(manifest_path) as f:
        return yaml.safe_load(f)


def get_variant(manifest: dict[str, Any], variant_id: str) -> VariantConfig:
    for v in manifest["variants"]:
        if v["id"] == variant_id:
            return VariantConfig(
                id=v["id"],
                substrate=v["substrate"],
                pipeline_stages=v.get("pipeline_stages", []),
                analysts=v.get("analysts", []),
            )
    raise KeyError(f"variant {variant_id!r} not in manifest")


def get_workload(manifest: dict[str, Any]) -> WorkloadConfig:
    w = manifest["workload"]
    return WorkloadConfig(
        agents=w["agents"],
        events_per_agent_per_sec=w["events_per_agent_per_sec"],
        event_payload_bytes=w["event_payload_bytes"],
        read_back_window=w["read_back_window"],
        warmup_seconds=w["warmup_seconds"],
        steady_state_seconds=w["steady_state_seconds"],
    )


# -----------------------------------------------------------------------------
# Substrate dispatch — actual adapters live in harness/substrates/
# -----------------------------------------------------------------------------

async def build_substrate(variant: VariantConfig, in_memory: bool):
    """Returns a substrate object exposing async emit(agent_id, payload) -> emit_ts, durable_ts."""
    if variant.substrate == "file_share":
        from harness.substrates.file_share import FileShareSubstrate
        return FileShareSubstrate(in_memory=in_memory)
    if variant.substrate == "sqlite":
        from harness.substrates.sqlite_pipeline import SqlitePipelineSubstrate
        return SqlitePipelineSubstrate(
            stages=variant.pipeline_stages,
            analysts=variant.analysts,
            in_memory=in_memory,
        )
    raise ValueError(f"unknown substrate {variant.substrate!r}")


# -----------------------------------------------------------------------------
# Agent task
# -----------------------------------------------------------------------------

async def agent_loop(agent_id: int, substrate, payload_bytes: int, cadence_s: float,
                    stop_at: float, latencies: list[float], blocks: list[int]):
    """One agent: emits events at fixed cadence; records per-event durability latency."""
    payload_filler = "x" * (payload_bytes - 128)  # 128 bytes reserved for metadata
    seq = 0
    next_tick = time.monotonic()
    while time.monotonic() < stop_at:
        seq += 1
        payload = json.dumps({
            "agent": agent_id,
            "seq": seq,
            "ts": time.time(),
            "data": payload_filler,
        })
        emit_ts = time.monotonic()
        result = await substrate.emit(agent_id, payload)
        durable_ts = time.monotonic()
        if result.get("verdict") == "block":
            blocks.append(seq)
        else:
            latencies.append((durable_ts - emit_ts) * 1000)  # ms
        next_tick += cadence_s
        sleep_for = next_tick - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
        else:
            next_tick = time.monotonic()  # fell behind; resync


# -----------------------------------------------------------------------------
# RSS sampler
# -----------------------------------------------------------------------------

async def rss_sampler(stop_event: asyncio.Event, samples: list[float]):
    proc = psutil.Process()
    while not stop_event.is_set():
        samples.append(proc.memory_info().rss / (1024 * 1024))  # MB
        await asyncio.sleep(1.0)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

async def run(variant_id: str, duration_override: int | None, output: Path | None,
              in_memory: bool, manifest_path: Path):
    manifest = load_manifest(manifest_path)
    workload = get_workload(manifest)
    variant = get_variant(manifest, variant_id)

    duration = duration_override or (workload.warmup_seconds + workload.steady_state_seconds)
    cadence_s = 1.0 / workload.events_per_agent_per_sec

    print(f"variant={variant.id} substrate={variant.substrate} "
          f"stages={variant.pipeline_stages} analysts={len(variant.analysts)} "
          f"duration={duration}s in_memory={in_memory}")

    cold_start_begin = time.monotonic()
    substrate = await build_substrate(variant, in_memory=in_memory)
    cold_start_ms = (time.monotonic() - cold_start_begin) * 1000

    latencies: list[float] = []
    blocks: list[int] = []
    rss_samples: list[float] = []
    stop_event = asyncio.Event()

    sampler_task = asyncio.create_task(rss_sampler(stop_event, rss_samples))

    stop_at = time.monotonic() + duration
    agent_tasks = [
        asyncio.create_task(
            agent_loop(i, substrate, workload.event_payload_bytes, cadence_s,
                       stop_at, latencies, blocks)
        )
        for i in range(workload.agents)
    ]

    await asyncio.gather(*agent_tasks)
    stop_event.set()
    await sampler_task
    await substrate.close()

    # Discard warmup window from latencies (approximate: drop first N events
    # where N = warmup_seconds * total_events_per_sec)
    if duration_override is None:
        discard = workload.warmup_seconds * workload.events_per_agent_per_sec * workload.agents
        latencies = latencies[discard:]

    metrics = {
        "variant": variant.id,
        "substrate": variant.substrate,
        "analysts": len(variant.analysts),
        "duration_s": duration,
        "events_completed": len(latencies),
        "events_blocked": len(blocks),
        "throughput_eps": len(latencies) / duration if duration > 0 else 0,
        "latency_ms": {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else None,
            "p99": statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else None,
            "max": max(latencies) if latencies else None,
            "min": min(latencies) if latencies else None,
        },
        "rss_mb": {
            "peak": max(rss_samples) if rss_samples else None,
            "mean": statistics.mean(rss_samples) if rss_samples else None,
        },
        "cold_start_ms": cold_start_ms,
    }

    print(f"RESULT variant={variant.id} "
          f"p50={metrics['latency_ms']['p50']} "
          f"p95={metrics['latency_ms']['p95']} "
          f"p99={metrics['latency_ms']['p99']} "
          f"rss_peak_mb={metrics['rss_mb']['peak']} "
          f"throughput={metrics['throughput_eps']:.1f}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"wrote {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default=os.environ.get("BENCH_VARIANT_ID"),
                        help="variant id from manifest (or $BENCH_VARIANT_ID)")
    parser.add_argument("--duration", type=int, default=None,
                        help="override total duration (s); skips manifest warmup math")
    parser.add_argument("--output", type=Path, default=None,
                        help="write metrics.json to this path")
    parser.add_argument("--in-memory", action="store_true",
                        help="use ':memory:' SQLite + tmpfs not required for file_share")
    parser.add_argument("--manifest", type=Path, default=Path("/app/manifest/manifest.yaml"),
                        help="path to manifest.yaml")
    args = parser.parse_args()

    if not args.variant:
        parser.error("--variant required (or set BENCH_VARIANT_ID)")

    asyncio.run(run(args.variant, args.duration, args.output, args.in_memory, args.manifest))


if __name__ == "__main__":
    main()
