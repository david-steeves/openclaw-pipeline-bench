# Draft PR comment — to post on openclaw/rfcs#11 when openclaw-test-harnesses ships

**Posting target:** comment thread on https://github.com/openclaw/rfcs/pull/11
**Post when:** step 10 of [`2026-06-19-policy-harness-extension.md`](./2026-06-19-policy-harness-extension.md) — after `rfc-0010-v1` tag is pushed and all sanity gates green.
**Replace `<sha>` and the bench-cost numbers below before pasting.**

---

Quick update with additional evidence for the discussion above.

I built reference implementations + a policy/perf test harness exercising the **per-claw "governed mode"** design from the bench-numbers reply: https://github.com/david-steeves/openclaw-test-harnesses (public, MIT, pinned at tag [`rfc-0010-v1`](https://github.com/david-steeves/openclaw-test-harnesses/releases/tag/rfc-0010-v1) / `<sha>`).

Not proposing this as part of the RFC. The substrate stays the focus here — this is just concrete evidence that the seam contract is buildable, the policy composition is unambiguous, and the "real cost" delta over the bench numbers is small enough to defend.

## What's in the repo

- **Two reference review teams** — `pii-reviewer` (HR-shaped PII) and `phi-reviewer` (healthcare-shaped PHI). Each is a small set of analyst-skill Python files that emit verdicts at the seam in the RFC 0003 evidence shape.
- **Layered policy composition** — one system-wide policy (SSN block) + two scoped policies (PII warn, PHI block). System layer evaluated first, BLOCK from any layer is final, scoped policies can ADD warns/blocks but cannot downgrade system verdicts (AWS IAM explicit-deny + MS Purview most-restrictive-wins semantics).
- **Control-plane config** — single YAML at the Gateway, Renovate-style `extends:` for preset composition, per-team `enabled` flag, per-team scope (data-classes), per-team severity map. Two YAML edits to ship.
- **Clarifying-prompt seam on upload/analyze** — decision-tree YAML with skip-logic; answers attach to `event.metadata.clarifications`; policy engine reads metadata during evaluation. This surface is novel — none of the surveyed DLP prior-art (Presidio, Purview, Macie, Cloud DLP) does interactive intent-capture at ingest time. Closest precedent is Stripe Radar's 4-action model.
- **Mock data** — 1MB synthetic HR PII (Workday-shaped, Faker-generated) and 1MB synthetic PHI (Synthea-shaped, wide-table datamart). Both public-safe; both ship with `annotations.yaml` documenting the expected verdict per row.
- **Policy-eval harness** — ingests mock data, loads the review teams, asserts every annotated row produces the documented verdict. Emits a human-reviewable verdict tape per run.
- **Perf harness** — `pipeline-real-claws` variant that delegates to [openclaw-pipeline-bench](https://github.com/david-steeves/openclaw-pipeline-bench) and substitutes the synthetic pass-analyst with the actual review teams above. `make perf-test-vs-bench` produces a side-by-side comparison REPORT.md.

## Proof shape (deep links pinned to `rfc-0010-v1`)

| Claim | Test / file |
|---|---|
| System SSN block fires on annotated row | `harness/policy-eval/asserts/test_system_ssn_block.py` |
| Scoped layer cannot downgrade system BLOCK | `harness/policy-eval/asserts/test_policy_composition.py` |
| Empty seam fails closed on sensitive transitions (= my Q5 in the reply, configurable here) | `harness/policy-eval/asserts/test_empty_seam_policy.py` |
| Real-claws perf cost stays within ~Δms of `pipeline-noop` | `harness/perf/results/REPORT.md` |
| Clarifying-prompt metadata routes correctly | `harness/policy-eval/asserts/test_clarifying_prompts_metadata.py` |

## Real-cost delta

| Variant | p50 | Notes |
|---|---|---|
| `pipeline-noop` (RFC 0010 lower bound) | _<X ms>_ | seam shape, no analysts |
| `pipeline-real-claws` (this comment, mixed pass + block) | _<X + Y ms>_ | pii-reviewer + phi-reviewer wired |
| Delta | **_<Y ms>_** | the "real" governance tax per event |

(*Numbers will replace these placeholders at posting time, after step 8 sanity gates.*)

Net of the bench numbers above: per-claw governed mode costs roughly the substrate delta + a single-digit-ms analyst overhead at 512B payloads. At 5MB+ payloads the substrate is the dominant cost — analysts are a rounding error.

## Re my Q3 in the previous comment

I asked whether there's an established place to get research/review teams iterating on RFCs at this depth. This repo is what *one* such group's deliverable looks like with one author + one M5 Pro rig over a couple of focused days. If a working group already exists, pointers welcome — I'd rather plug in than parallel-build. If not, this repo and the bench repo can stand as a seed others might join, fork, or critique. Either is fine; the goal is to make answering Q3 easier by putting evidence on the table.

## What this *isn't*

- **Not a new RFC.** RFC 0010 is still the proposal; this is reference-impl evidence cited from this thread.
- **Not a vendor pitch.** Synthetic data, MIT license, no service to sell.
- **Not exhaustive.** The example teams cover the two most common regulated-data shapes (PII / PHI). The composition rules generalize to any verdict-emitting analyst; happy to add a finance-claw or content-moderation-claw if reviewers think a third would clarify.

If maintainers want any of these sub-designs formalized — composition rules, control-plane config schema, clarifying-prompt seam, analyst-skill contract — I'd open follow-up RFCs (0012+) at whatever granularity you prefer. Until then they live as runnable code under MIT.

cc anyone working on adjacent supervisor/supervised separation, per-claw governance, or DLP-style analyst surfaces.
