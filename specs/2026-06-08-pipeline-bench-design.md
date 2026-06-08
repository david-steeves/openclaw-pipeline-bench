# Design: openclaw-pipeline-bench

**Created:** 2026-06-08
**Author:** David Steeves
**Status:** approved-for-implementation
**Companion RFC:** openclaw/rfcs#11 (RFC 0010 — Analyst-skill seams on a pipeline-shaped session substrate)

## Purpose

Produce defensible latency, throughput, memory, and cold-start numbers comparing the
**file-share substrate** OpenClaw uses today to the **three-stage pipeline substrate**
proposed in RFC 0010, across three analyst-skill loadings:

1. **baseline** — file-share, no pipeline, no analysts (today's shape)
2. **pipeline-noop** — three-stage pipeline (raw → processed → curated) with no analyst skills registered (substrate cost only)
3. **pipeline-1-analyst** — same pipeline, with one synthetic analyst skill registered per stage boundary, each emitting a `pass` verdict + evidence
4. **pipeline-blocking** — same as #3, but the processed → curated analyst returns `block` on 5 % of payloads (worst-case operator policy)

Numbers must be **citable in the RFC PR thread** if a maintainer says *"the latency cost is too high to consider"*.

## Hardware target

Mac mini M5 Pro (David's personal-AI rig). All four variants run on the same hardware,
back-to-back, with the same container runtime, same harness, same workload — so the
delta is the substrate, not the environment.

## Workload shape

Synthesises 10 concurrent agents ("top-10 claws") for 5 minutes of steady-state plus 60 s warmup.

- Each agent emits one **transcript event** every 100 ms (10 events/sec/agent, 100 events/sec total).
- Each event is a ~512-byte JSON payload (representative of a real claw transcript line).
- Each agent reads back the most recent **N=5** events from its own transcript to simulate "read what I just wrote" patterns.
- Workload runs in a single harness container; substrate is the variable across variants.

Workload synthesis (not loading real OpenClaw skills) is deliberate: it lets the
harness be identical across variants, eliminating skill-loading variance from the
measurement.

## Substrate implementations

| Variant              | Substrate                                              | Analyst surface                                                   |
|----------------------|--------------------------------------------------------|--------------------------------------------------------------------|
| baseline             | tmpfs bind mount, one file per agent (append-only JSONL) | None — substrate is the workspace                                  |
| pipeline-noop        | Three SQLite databases (raw.db / processed.db / curated.db); stage transitions are SQL inserts; stage 1 = ingest, stage 2 = parse-and-normalize, stage 3 = publish | None — measures pipeline substrate overhead alone                  |
| pipeline-1-analyst   | Same as pipeline-noop                                  | One Python coroutine per stage boundary, ~1 ms classification, emits redacted evidence row to `evidence.db` |
| pipeline-blocking    | Same as pipeline-noop                                  | Same as -1-analyst, but the processed → curated analyst returns `block` on 5 % of payloads (chosen randomly per payload hash) |

SQLite is the chosen backend per the RFC: *"A local SQLite file, an embedded log, an
object store, or a remote managed queue can each back any stage."* SQLite is the
smallest-footprint backend a personal-AI operator might actually run. WAL mode,
`PRAGMA synchronous = NORMAL`, `PRAGMA temp_store = MEMORY` (typical production-tuned settings,
documented in the harness).

## Metrics

For each variant the harness records:

- **Latency** — per-event end-to-end (emit → durable at curated stage / visible at file destination). Reports p50, p95, p99 over the 5-minute steady-state window.
- **Throughput** — sustained events/sec across all 10 agents.
- **Memory** — peak RSS of the substrate processes (not the harness) sampled at 1 Hz.
- **Cold start** — time from `docker compose up` to first event processed end-to-end.
- **Disk write amplification** — bytes written to disk per logical event, for each variant.

All measurements written to `bench/results/<variant>/<timestamp>/{metrics.json, latency.csv, rss.csv}` and summarised in `bench/results/<timestamp>/REPORT.md`.

## Success criteria

The lab succeeds if it produces:

1. A reproducible `make bench-all` that runs all four variants back-to-back on the M5 Pro and writes results to `bench/results/`.
2. A `REPORT.md` per run, machine-generated, summarising the four variants with the metric table above.
3. A one-paragraph **headline** answer to the question *"what does the pipeline substrate cost?"* — written by hand, citable in the RFC thread.

The lab does **not** need to:

- Implement real OpenClaw skills (synthetic workload by design).
- Survive packaging as a community benchmark suite (it's a one-off measurement for one RFC).
- Match production conditions in any cloud — M5 Pro on local SQLite is the deliberate target, matching the RFC's "personal-AI on personal devices" framing.

## Non-goals

- Choosing the best backend. The lab measures SQLite vs file-share; it does not claim either is universally optimal.
- Measuring multi-tenant or networked deployments.
- Optimising the substrate. Each variant uses straightforward, idiomatic implementations. Tuning is out of scope.
- Forensic measurement of analyst-skill verdicts (declarative evidence only, matching the RFC).

## Reviewer-facing risks (note for self)

- **Apples-to-apples fairness.** Same Python harness in all variants; only the substrate code path differs. Document the harness invariants in the report.
- **SQLite tuning posture.** Use documented production-typical pragmas; do not silently change them between variants.
- **Cold-start measurement.** Docker first-launch caches differ from second-launch. Run each variant **twice** in `make bench-all`; report the **second** number as "cold start" and label the first as "first-touch".
- **Variance.** Run each variant **3 times** and report median + min/max. Single-run numbers will get pushed back on.
