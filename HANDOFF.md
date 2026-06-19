# HANDOFF — M5 Pro execution

**Authored:** 2026-06-18 (MacBook pre-flight session)
**Target executor:** Mac mini M5 Pro
**Origin:** `github.com/david-steeves/openclaw-pipeline-bench`
**HEAD on master:** see `git log -1` after clone — this file is committed alongside.

This is the "you just landed on the Mac mini, what do I do" doc. Read this, then
glance at `README.md` and `plans/implementation.md`. Everything below was verified
working on a MacBook Pro on 2026-06-18 before push.

---

## TL;DR

```sh
git clone git@github.com:david-steeves/openclaw-pipeline-bench.git ~/projects/openclaw-pipeline-bench
cd ~/projects/openclaw-pipeline-bench
make install      # verifies OrbStack + python3.13 + uv
make smoke        # 10s in-memory sanity check (~10s wall-clock)
make bench-all    # full benchmark — ~40 min wall-clock on M5 Pro
```

Then write the headline paragraph at the top of `bench/results/<ts>/REPORT.md`
by hand. Sanity-check the numbers per step 6 of `plans/implementation.md`. Post
the numbers in [openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11).

---

## Pre-flight state (verified on MacBook, 2026-06-18)

| Check                                  | State |
|----------------------------------------|-------|
| `make install` passes                  | ✓ |
| `make smoke` runs harness in-memory    | ✓ — p50 ≈ 3ms on MacBook |
| `docker compose build` (all 6 images)  | ✓ |
| `docker compose run baseline` 10s      | ✓ — p50 ≈ 0.76ms |
| `docker compose run sqlite-flat` 10s   | ✓ — p50 ≈ 1.09ms |
| `docker compose run pipeline-noop` 10s | ✓ — already smoke-tested |
| `docker compose run pipeline-fullcopy` 10s | ✓ — p50 ≈ 6.78ms |
| Monotonicity baseline → fullcopy       | ✓ — shape expected by design |

The bench is **mechanically ready**. M5 Pro execution is about getting citable
numbers on the right hardware, not about debugging the bench itself.

## Variant set (6, not 4 — plan is older than code)

The plan in `plans/implementation.md` was written 2026-06-08 against the
original 4 variants. The bench has since grown to **6 variants** to better
isolate cost layers for the RFC reviewers:

| Variant                | Substrate         | What it isolates                                  |
|------------------------|-------------------|---------------------------------------------------|
| `baseline`             | tmpfs file-share  | today's shape — control                           |
| `sqlite-flat`          | single SQLite tbl | **SQLite-engine cost**, no pipeline               |
| `pipeline-noop`        | 3× SQLite stages  | pipeline-shape cost, INSERT-only promotion (lower bound) |
| `pipeline-fullcopy`    | 3× SQLite stages  | pipeline cost with SELECT+INSERT+DELETE (upper bound) |
| `pipeline-1-analyst`   | 3× SQLite stages  | + 1 pass-analyst per seam                         |
| `pipeline-blocking`    | 3× SQLite stages  | + 1 conditional-block analyst (5% block rate)     |

The Makefile, `docker-compose.yml`, and `scripts/generate_report.py` are all
in sync with the manifest (`manifest/manifest.yaml`). `make bench-all` runs
all six, `scripts/generate_report.py` produces a 6-row table.

## Wall-clock budget (M5 Pro estimate)

| Phase                                    | Estimate |
|------------------------------------------|----------|
| OrbStack install + Python + uv           | 15 min (skip if dukeFast7 setup already done) |
| Clone + `make install`                   | 2 min |
| `make build` (6 images, first build)     | 6 min |
| `make bench-all` (6 × 3 × 6 min)         | ~40 min |
| `REPORT.md` review + headline paragraph  | 15 min |
| **Total**                                | **~1h 20m** (or 1h if OrbStack already installed) |

## Sanity gates (required before posting numbers to PR)

From `plans/implementation.md` step 6:

1. **Baseline ≈ pipeline-noop within an order of magnitude.** If pipeline is
   100× slower than file-share on noop, something is broken.
2. **pipeline-1-analyst ≈ pipeline-noop + (2 × cost_ms).** The analyst cost
   should account for the difference. If not, instrumentation is wrong.
3. **pipeline-blocking p99 spikes for blocked payloads.** Confirms the block
   path is exercised.

**Additional gate from the 6-variant set:**

4. **Monotonicity holds:** `baseline ≤ sqlite-flat ≤ pipeline-noop ≤ pipeline-fullcopy`
   on p50, p95, p99. If a row jumps out of order, re-investigate before sharing.
   (Verified holds on MacBook smoke runs.)

## What can go wrong (and what to look at)

- **OrbStack docker socket missing** → `open -a OrbStack` then wait for green
  menu-bar icon, then retry `docker version`. Step 0.1 in plan.
- **`make smoke` says "No such file or directory: '/app/manifest/manifest.yaml'"**
  → already fixed; smoke now passes `--manifest ../manifest/manifest.yaml`
  explicitly. If you see this error, you're on a stale Makefile. Re-pull.
- **A bench run hangs partway** → check `docker ps`; the harness has a hard
  duration arg and should always exit. If it hangs, `docker kill <id>` and
  inspect `bench/harness/runner.py` for an unbounded await.
- **REPORT.md missing rows** → `scripts/generate_report.py` skips variants
  whose results dir is empty. Confirm `bench/results/<ts>/<variant>/run-*.json`
  files exist before re-running the reporter.

## Where to post numbers

The bench exists to answer one specific question in the
[openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11) PR thread: *what
is the latency cost of moving from a file-share substrate to a pipeline
substrate, with and without analyst loadings?*

When the bench finishes:

1. Open `bench/results/<ts>/REPORT.md`.
2. Write the headline paragraph at the top (one sentence per major finding —
   substrate cost, analyst cost, blocking cost).
3. Sanity-check against the 4 gates above.
4. If all gates pass, **commit the results dir** (it's gitignored except
   `.gitkeep`, so add `-f` if needed).
5. Post a link to the committed REPORT.md as a comment on the PR. Cite specific
   p50/p95/p99 numbers in the comment so reviewers don't have to click through.

## Don't

- **Don't run the bench on the MacBook for the PR.** MacBook smoke results are
  for sanity, not citation. The whole point is M5 hardware.
- **Don't change `manifest/manifest.yaml`** unless you also update the design
  doc — the manifest is the single source of truth for workload params and
  the design doc cites it.
- **Don't auto-generate the headline paragraph.** Humans look at the numbers
  and write it. The reporter explicitly leaves a placeholder.

---

If anything in this doc is wrong, fix it in place and commit. This file is the
contract between MacBook-session-Claude and M5-session-Claude.

## Follow-up work after the bench numbers ship

After `make bench-all` finishes and the numbers are posted to
[openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11), the next plan
is in [`plans/2026-06-19-policy-harness-extension.md`](./plans/2026-06-19-policy-harness-extension.md).

That plan covers RFC 0012 (reference analyst review teams, layered policy
composition, clarifying prompts) and a new `openclaw-test-harnesses` repo
that re-runs the perf bench against *real* claws instead of synthetic
pass-analysts. The cost delta between `pipeline-noop` (this plan) and
`pipeline-real-claws` (the next plan) is the headline number for the
follow-up RFC.

Do **not** start that work without the bench numbers in hand — the policy
work builds on the RFC 0010 baseline being citable.
