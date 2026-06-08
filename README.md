# openclaw-pipeline-bench

Performance benchmark lab for [openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11)
(RFC 0010 — Analyst-skill seams on a pipeline-shaped session substrate).

Measures the cost of moving from a **file-share substrate** to a **three-stage data
pipeline substrate**, with and without analyst-skill loadings, on a Mac mini M5 Pro.

## Why this exists

If a maintainer in the RFC PR thread says *"the latency cost of an evaluating
substrate is too high to consider"* — these numbers are the answer.

## What it measures

Four variants on identical hardware, harness, and workload:

| Variant              | Substrate            | Analyst surface                          |
|----------------------|----------------------|------------------------------------------|
| `baseline`           | tmpfs file-share     | None (today's shape)                     |
| `pipeline-noop`      | 3× SQLite stages     | None (substrate cost only)               |
| `pipeline-1-analyst` | 3× SQLite stages     | 1 synthetic pass-analyst per seam        |
| `pipeline-blocking`  | 3× SQLite stages     | 1 pass-analyst + 1 5%-block analyst      |

Metrics: latency p50/p95/p99, throughput, peak RSS, cold start, disk write amplification.

## How to run

On the Mac mini M5 Pro (after `plans/implementation.md` step 0 is complete):

```sh
make install      # confirm runtime + python present
make build        # build 4 container images
make bench-all    # ~25 min: 3 runs per variant, generate REPORT.md
```

Results land in `bench/results/<timestamp>/REPORT.md`.

## Repo layout

```
specs/    — design doc (approved 2026-06-08)
plans/    — step-by-step implementation plan for the M5 Pro session
manifest/ — single source of truth for workload parameters
bench/
  variants/      — Dockerfile + compose per variant
  harness/       — Python workload runner (asyncio)
  workload/      — synthetic event generator
  results/       — per-run metrics + reports (gitignored except .gitkeep)
scripts/  — orchestration, reporting, setup
```

## Status

- **2026-06-08 evening:** Design + manifest + implementation plan committed on MacBook. Ready for M5 Pro handoff.
- **2026-06-09 morning (planned):** M5 Pro executes `plans/implementation.md`. Numbers + REPORT.md by EOD.
