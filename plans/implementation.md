# Implementation Plan — openclaw-pipeline-bench

**Target executor:** Mac mini M5 Pro (handoff from David's MacBook, 2026-06-09 morning)
**Design:** `specs/2026-06-08-pipeline-bench-design.md`
**Manifest:** `manifest/manifest.yaml`

This plan is written so a fresh Claude session on the M5 Pro can pick up and execute
without re-deriving any decisions. Each step is independently verifiable.

---

## Step 0 — One-time M5 Pro setup

**Owner:** M5 Pro Claude session
**Verifiable when:** `orb version` returns a version string and `docker ps` succeeds.

1. Install OrbStack:
   ```
   brew install --cask orbstack
   open -a OrbStack
   ```
   Wait for the OrbStack menu-bar icon to go green.

2. Confirm Docker compatibility:
   ```
   docker version
   docker compose version
   ```

3. Install Python 3.13 + uv:
   ```
   brew install python@3.13 uv
   ```

4. Clone the bench repo onto the M5 Pro:
   - **From this laptop:** push `~/projects/openclaw-pipeline-bench` to a private GitHub repo `david-steeves/openclaw-pipeline-bench` (per the device-sync memory rule).
   - **On the M5:** `git clone git@github.com:david-steeves/openclaw-pipeline-bench.git ~/projects/openclaw-pipeline-bench`

---

## Step 1 — Harness implementation

**Owner:** M5 Pro Claude session
**Verifiable when:** `make harness-smoke` produces 100 events in ≤2 s against an in-memory SQLite.

The harness is a single Python module (`bench/harness/runner.py`) that:

- Reads `manifest/manifest.yaml` for workload parameters and the target variant ID.
- Spawns N async tasks (one per agent), each emitting events at the configured cadence.
- Records per-event timestamps to an in-memory ring buffer; flushes to `latency.csv` at end of run.
- Samples RSS of the substrate process via `psutil` at 1 Hz; writes `rss.csv`.
- Computes p50/p95/p99 from `latency.csv` and writes `metrics.json`.
- Emits a single line on stdout at completion: `RESULT variant=<id> p50=<ms> p95=<ms> p99=<ms> rss_peak_mb=<n> throughput=<eps>`.

A skeleton (`runner.py.skeleton`) is in this repo. The M5 session fleshes it out.

---

## Step 2 — Substrate adapters

**Owner:** M5 Pro Claude session
**Verifiable when:** each adapter's `pytest tests/test_<adapter>.py` is green.

Two substrate adapters in `bench/harness/substrates/`:

- **`file_share.py`** — opens `/workspace/agent-{n}.jsonl`, appends JSON-line, reads back last N lines for the read-back window.
- **`sqlite_pipeline.py`** — opens `raw.db / processed.db / curated.db`; inserts a row to `raw`, kicks off (or awaits) the registered analyst chain, advances to `processed` then `curated`. Analysts are registered via the manifest's `variants[*].analysts` list and run synchronously inline.

The pipeline substrate must enforce passive-I/O on the substrate adapter itself (per RFC):
the adapter only inserts and selects. All payload mutation / verdicts live in
`bench/harness/analysts/`.

---

## Step 3 — Analyst skill shims

**Owner:** M5 Pro Claude session
**Verifiable when:** `pytest tests/test_analysts.py` is green.

Synthetic analyst skills in `bench/harness/analysts/`:

- `pass_analyst.py` — sleeps `cost_ms`, emits `{verdict: "pass"}`.
- `blocking_analyst.py` — sleeps `cost_ms`, returns `block` if `hash(payload) % 100 < block_rate * 100` else `pass`.

Both emit an evidence row to `evidence.db` in the redacted shape RFC 0003 defines
(seam id, analyst id, rule ref, verdict — no payload content).

---

## Step 4 — Variant container builds

**Owner:** M5 Pro Claude session
**Verifiable when:** `make build` produces 4 images, each ≤200 MB.

One `Dockerfile` per variant in `bench/variants/<id>/`:

- Base: `python:3.13-slim-bookworm`
- COPY: harness module, manifest, variant-specific env var (`BENCH_VARIANT_ID=<id>`)
- ENTRYPOINT: `python -m harness.runner`
- Healthcheck: small TCP socket exposed on :8080 for the orchestrator to detect "ready".

`docker-compose.yml` at repo root composes all four for `make bench-all`.

---

## Step 5 — Orchestration & reporting

**Owner:** M5 Pro Claude session
**Verifiable when:** `make bench-all` runs end-to-end, takes ~25 min wall-clock, produces `bench/results/<timestamp>/REPORT.md`.

The Makefile orchestrates:

```
make install      # confirm orbstack + python + uv present
make build        # docker compose build
make bench-baseline           # 3 runs, write results
make bench-pipeline-noop      # 3 runs, write results
make bench-pipeline-1-analyst # 3 runs, write results
make bench-pipeline-blocking  # 3 runs, write results
make bench-all                # all four in sequence + generate REPORT.md
make clean                    # docker compose down + rm results dir
```

`scripts/generate_report.py` reads all `metrics.json` under `bench/results/<timestamp>/`
and produces `REPORT.md` with the table from the design doc filled in.

The **headline paragraph** at the top of `REPORT.md` is written by hand after looking
at the numbers — not auto-generated. Plan reserves a placeholder.

---

## Step 6 — Sanity gates before sharing numbers

**Owner:** Human (David) — review before posting in RFC thread
**Verifiable when:** all three checks pass.

1. **Sanity check 1: baseline ≈ pipeline-noop within an order of magnitude.** If the pipeline is 100× slower than file-share on noop, something is broken.
2. **Sanity check 2: pipeline-1-analyst ≈ pipeline-noop + (2 * cost_ms).** The analyst cost should account for the difference; if it doesn't, instrumentation is wrong.
3. **Sanity check 3: pipeline-blocking p99 spikes for blocked payloads.** Confirms the block path is exercised.

If all three pass: numbers are citable. If any fail: re-investigate before sharing.

---

## Estimated wall-clock budget on M5 Pro

| Phase                                    | Estimate |
|------------------------------------------|----------|
| OrbStack install + Python + uv           | 15 min   |
| Repo clone + push from this laptop       | 5 min    |
| Harness implementation                   | 45 min   |
| Substrate adapters                       | 30 min   |
| Analyst shims                            | 15 min   |
| Variant Dockerfiles + compose            | 20 min   |
| Makefile + reporter                      | 30 min   |
| `make bench-all` execution               | 25 min   |
| REPORT review + headline paragraph       | 15 min   |
| **Total**                                | **~3.5 h** |

Numbers ready to cite in PR thread by EOD 2026-06-09 if started in the morning.

---

## Handoff message for the M5 Pro session

> Pick up `~/projects/openclaw-pipeline-bench/plans/implementation.md` and execute steps 0–6.
> The design is `specs/2026-06-08-pipeline-bench-design.md`. The manifest is the single
> source of truth — do not hardcode workload params. Numbers are for citing in
> openclaw/rfcs#11; sanity gates in step 6 are required before sharing.
