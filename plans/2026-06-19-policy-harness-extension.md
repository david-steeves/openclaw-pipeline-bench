# Plan — Reference implementations + test harness for RFC 0010 (evidence track)

**Authored:** 2026-06-18 (MacBook research + synthesis session)
**Revised:** 2026-06-18 (recast after refreshing on the 2026-06-09 PR reply at
[openclaw/rfcs#11](https://github.com/openclaw/rfcs/pull/11) — bench numbers +
governed-mode reframing already posted; this is not "next RFC", it's "evidence
for the open RFC")
**Sibling of:** [`implementation.md`](./implementation.md) (M5 perf-bench plan —
already executed locally; numbers public at the bench repo URL above)
**Output target:** new `openclaw-test-harnesses` repo (public from day 1) +
one PR comment on openclaw/rfcs#11
**No new RFCs in this plan.** RFCs 0012+ land later only if maintainers ask.

---

## Why this exists (read this first)

RFC 0010 is open, bench numbers are posted (with the per-claw "governed mode"
reframing), and we asked maintainers 5 questions including Q3: *"Is there an
established place to get research/review teams iterating on RFCs at this
depth?"*

We're at the standard awaiting-maintainer-reaction stage of an RFC. In mature
RFC processes (TC39, W3C, Rust, K8s KEPs), this is **not** the moment to open
follow-up RFCs. It's the moment to ship reference implementations and harness
evidence in a sibling repo and link them from the open PR.

So the previous draft of this plan (titled "RFC 0012") was wrong shape. This
revision recasts the work as Stage-1 evidence, not a Stage-2 normative proposal.

## What's normal (the playbook)

| Stage | Action | Output | Where |
|---|---|---|---|
| 1 — *we are here* | Build reference impls + harness as evidence | Public repo + PR comment | `openclaw-test-harnesses` + comment on openclaw/rfcs#11 |
| 2 — maintainer signals interest | Stabilize surface area through implementation experience | Versioned reference impls | Same repo, tagged release `rfc-0010-v1` |
| 3 — maintainers ask for formalization | Open follow-up RFCs at the granularity they request | RFC 0012/0013/0014 | openclaw-rfcs (docs only) |

If we skip Stage 1 and write RFC 0012 directly, we're asking maintainers to
review a normative proposal for sub-designs whose parent (RFC 0010) hasn't been
acked yet. That's pushing rope.

---

## Repo architecture (one new repo — public from day 1)

### `openclaw-test-harnesses` (NEW, public) — `git@github.com:david-steeves/openclaw-test-harnesses.git`

```
README.md                              # what this is, how to run, link back to RFC 0010 PR
HANDOFF.md                             # landing pad for M5 Pro session (like the bench repo)
LICENSE                                # MIT, mirrors openclaw-rfcs

control-plane/
  config-schema.yaml                   # JSON schema for openclaw.config.yaml
  example.config.yaml                  # paste-into-your-repo example
  README.md                            # how the control-plane config works

clarifying-prompts/
  schema.yaml                          # prompt-tree schema
  upload-prompts.example.yaml          # 2 upload prompts (PHI detection, jurisdiction)
  analyze-prompts.example.yaml         # 2 analyze prompts (output-dest, depth)
  README.md                            # decision-tree semantics + skip-logic

policies/
  system/
    block-ssn.yaml                     # system-wide, always evaluated first
    block-api-key.yaml                 # system-wide
  shared-lib/
    ssn-detector.yaml                  # composable rule snippets
    phi-detector.yaml
    pii-cooccurrence.yaml
  teams/
    pii-warn.yaml                      # scoped to pii-reviewer
    phi-block.yaml                     # scoped to phi-reviewer
  README.md                            # composition rule, precedence

teams/                                 # the reference review teams (was rfcs/0012/example-teams in v1)
  pii-reviewer/                        # RENAMED from hr-reviewer per Q2
    team.yaml
    analysts/
      ssn-detector.py                  # imports system-wide rule
      pii-cooccurrence-warn.py         # name + DOB warn
      salary-warn.py
    README.md                          # what this team is for
  phi-reviewer/                        # RENAMED from snowflake-reviewer per Q2
    team.yaml
    analysts/
      phi-marker-block.py              # MRN/diagnosis_code block
      patient-id-warn.py
      free-text-phi-scan.py            # scans diagnosis_notes free-text
    README.md

mock-data/                             # synthetic, public-safe, ~1MB each gzipped
  hr-pii/                              # source format name kept (it's HR-shaped data)
    schema.md
    data.csv.gz
    annotations.yaml                   # row -> expected verdict + which policy fires + which layer wins
  phi-snowflakey/                      # source format name kept (it's wide-table datamart-shaped)
    schema.md
    data.csv.gz
    annotations.yaml
  generators/                          # repro: regenerate the CSVs from seeds
    gen_hr.py                          # Faker-shaped
    gen_phi.py                         # Synthea-shaped

harness/
  policy-eval/                         # functional tests
    runner.py                          # ingest mock-data, load teams, emit verdict tape
    asserts/
      test_system_ssn_block.py
      test_pii_warn.py
      test_phi_block.py
      test_policy_composition.py       # system BLOCK trumps scoped WARN
      test_clarifying_prompts_metadata.py
    verdict-tape/                      # human-reviewable transcripts per run
  perf/                                # perf tests with real claws
    runner.py                          # delegates to openclaw-pipeline-bench harness
    manifest.yaml                      # adds variant: pipeline-real-claws
    workload-from-mock.py              # feeds mock-data as event stream

Makefile                               # make policy-test / make perf-test-vs-bench / make all
docker-compose.yml                     # for perf runs in containers
```

### `openclaw-rfcs` — *unchanged*

Stays a docs-only repo. RFC 0010 is in flight; no new RFC, no executable Python
landing under `rfcs/`. We revisit when/if maintainers ask for formalization.

### `openclaw-pipeline-bench` — *unchanged except a forward pointer*

The perf harness in `openclaw-test-harnesses/harness/perf/` *delegates* to this
repo's variant infrastructure. We don't fork it — we add `pipeline-real-claws`
as a new variant that imports the existing substrate adapters.

---

## Mock data — schemas (full versions in `mock-data/*/schema.md` in the new repo)

### `mock-data/hr-pii/` — Workday-shaped employee master

16 columns, one row per active employee. ~10K rows → ~1MB gzipped CSV
(synthesizable from seed via `generators/gen_hr.py`, Faker-shaped).

Columns: `employee_id, first_name, last_name, date_of_birth, ssn, email, phone, street_address, city, state, zip, department, job_title, salary, hire_date, employment_status`

Annotated trigger rows:
- **BLOCK** — `ssn` present + `full_name` present (system SSN block fires)
- **WARN** — `date_of_birth` + name co-occurrence without SSN (scoped PII warn)
- **WARN** — `salary` present (scoped HR-sensitivity warn)
- **PASS** — `employee_id` + `department` only

### `mock-data/phi-snowflakey/` — Synthea-shaped wide-table datamart

24 columns, one row per patient-encounter, ICD-10 / LOINC / RxNorm vocabularies.
~250K rows → ~1MB gzipped (from `generators/gen_phi.py`).

Columns: `patient_id, last_name, first_name, birth_date, gender, address, city, state, zip_code, phone_number, email, ssn, mrn, encounter_id, encounter_date, diagnosis_code, diagnosis_description, procedure_code, medication_code, medication_name, lab_value, lab_code, lab_code_description, diagnosis_notes`

Annotated trigger rows:
- **BLOCK** — `ssn` present + any of `mrn`/`diagnosis_code` (system SSN block + scoped PHI block; system layer wins)
- **WARN** — `patient_id` + `birth_date` + `city` (re-identification vector, scoped warn)
- **PASS** — billing codes only, no demographics

`diagnosis_notes` is the LLM-analyst seam — free-text PHI detection is the case
where regex-only analysts fail.

---

## Policy composition — the rule

```
final_verdict = max(system_verdicts ∪ scoped_verdicts)
ordering:      PASS < WARN < BLOCK
constraint:    scoped layer can ADD warns/blocks; cannot downgrade system verdicts
audit_trail:   every layer that fired is recorded; the winning layer is named
```

System-wide policies run first; scoped policies still evaluate after a system
BLOCK (for audit completeness) but their verdicts become advisory. Cited
precedent in the README: AWS IAM explicit-deny + Microsoft Purview
most-restrictive-policy-wins.

---

## Control-plane config — `openclaw.config.yaml`

```yaml
version: 1
extends:
  - openclaw-test-harnesses:control-plane/example.config.yaml   # paste-in default

system_policies:
  - openclaw-test-harnesses:policies/system/block-ssn.yaml
  - openclaw-test-harnesses:policies/system/block-api-key.yaml

teams:
  pii-reviewer:
    enabled: true
    seams: [raw_to_processed, processed_to_curated]
    analysts:
      - openclaw-test-harnesses:teams/pii-reviewer/analysts/ssn-detector.py
      - openclaw-test-harnesses:teams/pii-reviewer/analysts/pii-cooccurrence-warn.py
    policies:
      - openclaw-test-harnesses:policies/teams/pii-warn.yaml
    severity_map: { critical: block, high: warn }
    scope:
      data_classes: [hr, payroll]
    clarifying_prompts:
      upload: openclaw-test-harnesses:clarifying-prompts/upload-prompts.example.yaml
      analyze: openclaw-test-harnesses:clarifying-prompts/analyze-prompts.example.yaml

  phi-reviewer:
    enabled: true
    seams: [raw_to_processed, processed_to_curated]
    analysts:
      - openclaw-test-harnesses:teams/phi-reviewer/analysts/phi-marker-block.py
      - openclaw-test-harnesses:teams/phi-reviewer/analysts/patient-id-warn.py
      - openclaw-test-harnesses:teams/phi-reviewer/analysts/free-text-phi-scan.py
    policies:
      - openclaw-test-harnesses:policies/teams/phi-block.yaml
    severity_map: { critical: block, high: warn }
    scope:
      data_classes: [warehouse, snowflake, healthcare]
    clarifying_prompts:
      upload: openclaw-test-harnesses:clarifying-prompts/upload-prompts.example.yaml
```

Renovate-style preset composition. User ergonomics: clone the example, set
`enabled: true` on the teams you want, override 1–2 fields. Two YAML edits, ship.

---

## Clarifying prompts — decision-tree schema

Decision-tree YAML with skip-logic, closed answer sets, and metadata attachment.
Answers attach as `metadata.clarifications`; policy engine reads it during
evaluation.

```
Upload event arrives
  → ask "Does this file contain PHI?"
      yes  → ask "Is it destined for a HIPAA-regulated jurisdiction?"
      no   → skip jurisdiction prompt
      uncertain → triage analyst runs, asks follow-up
  → answers stored on event.metadata.clarifications
  → review-team seams fire; policies read metadata when deciding verdict

Analyze event arrives
  → ask "Where will results be shared?" (internal | external | public)
      external → ask "Is there a signed DPA?"
        no  → analyze blocked, escalate to legal
  → answers stored on event.metadata.clarifications
```

This surface is **novel** — none of the surveyed prior-art (Presidio, Purview,
Macie, Cloud DLP) does interactive intent-capture at upload/analyze. Closest
analog is Stripe Radar's 4-action model (block / allow / review / challenge).
Worth surfacing as an OpenClaw differentiator in the PR comment.

---

## Test harness — what `make` runs (in the new repo)

```
make install            # python 3.13 + uv + (optional) orbstack for perf runs
make gen-data           # regenerate mock-data/*/data.csv.gz from seeds (deterministic)
make policy-test        # ingest mock data → load review teams → assert verdicts vs annotations.yaml
                        # → emit verdict-tape/<ts>/REPORT.md (human-readable)
make perf-test          # delegates to openclaw-pipeline-bench harness; replays mock-data as event stream
                        # adds variant: pipeline-real-claws (uses pii-reviewer + phi-reviewer teams)
make perf-test-vs-bench # runs synthetic pass-analyst variants (from pipeline-bench) AND
                        # pipeline-real-claws side-by-side; emits comparison REPORT.md.
                        # This is the "real cost" number for the follow-up PR comment.
make all                # policy-test + perf-test-vs-bench
make clean
```

`make perf-test-vs-bench` is the headline number for the PR comment:
*"the substrate cost from RFC 0010 is X; with real review teams loaded, it's X + Y.
The 'governed mode' opt-in design pays for X + Y only on claws that need it."*

---

## Implementation ordering

Each step is independently verifiable. Sized for a fresh M5 Pro Claude session
to execute in order, after the bench-numbers work in `implementation.md` is no
longer needed (already shipped).

| Step | Output | Verifiable when |
|---|---|---|
| 0 | Create public repo `david-steeves/openclaw-test-harnesses` on GitHub + clone | `git ls-remote` succeeds |
| 1 | LICENSE + README + HANDOFF skeletons; link RFC 0010 PR | repo page on github.com renders |
| 2 | Control-plane config schema + example.config + clarifying-prompts schemas | `yamllint` clean across the repo |
| 3 | System + shared-lib + team-scoped policy YAML | spot-check `block-ssn.yaml` matches the annotated SSN rows in mock data |
| 4 | Reference review teams `pii-reviewer` + `phi-reviewer` (4–6 small Python files each) | `python -m pii_reviewer.ssn_detector --in fixtures/ssn-row.json` returns BLOCK |
| 5 | Mock data + generators + annotations | `make gen-data && diff <(zcat data.csv.gz) <(./gen.py --seed N)` is empty |
| 6 | Policy-eval harness (ingest, load teams, assert) | `make policy-test` is green; verdict tape spot-checks |
| 7 | Perf harness (`pipeline-real-claws` variant; delegates to pipeline-bench) | `make perf-test` produces metrics.json |
| 8 | Comparison report generator | `make perf-test-vs-bench` produces side-by-side REPORT.md |
| 9 | Tag release `rfc-0010-v1` at the SHA we'll cite | `git tag --list` shows it; GitHub release rendered |
| 10 | Post follow-up comment on openclaw/rfcs#11 with pinned SHA + Proof Shape table | comment visible in PR thread (draft in [`pr-comment-when-impl-ships.md`](./pr-comment-when-impl-ships.md)) |

## Wall-clock budget

| Step | Estimate |
|---|---|
| 0 — repo create + clone | 10 min |
| 1 — skeletons | 15 min |
| 2 — config schemas | 45 min |
| 3 — policy YAML | 30 min |
| 4 — reference review teams (4–6 small Python files per team) | 60 min |
| 5 — mock data + generators | 60 min |
| 6 — policy-eval harness | 90 min |
| 7 — perf harness (most reuse from pipeline-bench) | 45 min |
| 8 — comparison reporter | 30 min |
| 9 — tag release | 5 min |
| 10 — PR comment | 15 min (review + paste; draft already exists) |
| **Total** | **~6.5 h** (one focused day on M5 Pro) |

---

## Sanity gates (required before posting the PR comment)

1. **All annotated mock rows produce the documented verdict.** Verdict tape
   matches every `annotations.yaml`.
2. **Policy composition tests are green.** Specifically: a row hitting both
   `system/block-ssn` and `policies/teams/pii-warn` returns BLOCK with both
   verdicts in the audit trail (system layer wins; scoped recorded as advisory).
3. **Clarifying-prompt metadata routes correctly.** A row uploaded with
   `clarifications.phi-detection = no` should NOT trigger the PHI block analyst
   even if the row contains MRN-shaped data (operator-asserted exemption path;
   logged but not enforced).
4. **Perf monotonicity:** `pipeline-noop ≤ pipeline-real-claws-pass-only ≤ pipeline-real-claws-mixed`.
   If real claws beat synthetic pass-analysts, instrumentation is wrong.
5. **Cost delta is citable:** the difference between `pipeline-noop` and
   `pipeline-real-claws` is the number that goes in the follow-up comment.

---

## Design decisions (locked, per 2026-06-18 conversation)

1. **New repo name = `openclaw-test-harnesses`** (plural; room for sibling
   harness sets in future RFCs).
2. **No new RFC.** This is Stage 1 evidence for RFC 0010, not a Stage 2
   proposal. RFCs 0012+ land only after maintainer signal.
3. **Public from day 1.** Accelerates an answer to Q3 (research/review WG
   question) from the original PR reply by giving maintainers a concrete repo
   to point to or copy from.
4. **All impl lives in the new repo, not `openclaw-rfcs`.** The RFC repo stays
   docs-only. Sticking executable Python under `openclaw-rfcs/rfcs/0012/` was
   the wrong call.
5. **Team names = `pii-reviewer` / `phi-reviewer`** (was `hr-reviewer` /
   `snowflake-reviewer`). Describes what's reviewed, not source format. Mock
   data dirs keep source-shape names (`hr-pii`, `phi-snowflakey`).
6. **Cite a pinned SHA / tagged release in the PR comment**, not just the repo
   URL. WPT / test262 precedent. Tag = `rfc-0010-v1` at step 9.
7. **PR comment includes a "Proof Shape" table** with deep-links to specific
   test files at the pinned SHA — casual readers don't have to clone the repo.

---

## What lands in front of the maintainer

A single PR comment on openclaw/rfcs#11 — see
[`pr-comment-when-impl-ships.md`](./pr-comment-when-impl-ships.md) for the draft.
It cites the test-harnesses repo at the `rfc-0010-v1` tag, includes the Proof
Shape table, and connects back to the open Q3 about research/review WGs.

No revision to RFC 0010 doc itself. No new RFC PR. Just evidence.

---

## Stage 2 / Stage 3 — when maintainers do reply

Only relevant *if* maintainers signal they want the sub-design surfaces
formalized. If they do, factor by surface area:

| Possible follow-up RFC | Scope |
|---|---|
| RFC 0012 — Layered policy composition for analyst skills | System + scoped policy composition rule; precedence semantics; audit trail format |
| RFC 0013 — Control-plane config schema for review teams | `openclaw.config.yaml` shape; preset-extends; per-team enable/disable; scope/severity |
| RFC 0014 — Clarifying-prompt seam on upload/analyze | Decision-tree schema; metadata attachment; policy integration |
| RFC 0015 — Reference review team contract | What an analyst skill ABI must implement; verdict shape; redaction guarantees |

These are placeholders. We don't draft them now. If maintainers say *"yes, take
clarifying prompts further"* in their reply, we cherry-pick that one and write
it. If they say *"none of this, the substrate is too costly,"* we drop the
whole tree and the test-harnesses repo stands as a standalone parental-controls
demo.

---

## Open questions still in the air (not for the plan; for the conversation)

1. Maintainer answers to the 5 questions from the 2026-06-09 PR reply. Until
   those land, this plan is the most-likely-correct shape. If their feedback
   reshapes the substrate or kills the governed-mode framing, this plan needs
   substantive revision.
2. Whether the test-harnesses repo should also host a *minimum* governed-mode
   reference runtime (a small wrapper that demonstrates the per-claw opt-in
   without a full OpenClaw fork). Currently NOT in scope; the harness assumes
   review teams run standalone against mock data. If maintainers want to see
   the substitution mechanism end-to-end, that's a Stage-2 addition.

---

## Sources referenced (research synthesis, unchanged from v1)

- AWS IAM / MS Purview / K8s admission / OPA Rego — layered policy composition
- Renovate / CodeRabbit / Snyk / CODEOWNERS — review-team config patterns
- Synthea / MIMIC-IV / HIPAA 18 / AWS Macie / Cloud DLP — PHI mock schema
- Workday / BambooHR / Faker / AWS Macie / MS Purview / Cloud DLP — HR PII mock
- Stripe Radar / Qualtrics skip-logic / OneTrust intake — clarifying-prompt UX
- TC39 test262 / W3C WPT / Rust RFC process / K8s KEPs — RFC + reference-impl
  separation pattern (informs the "no new RFC yet" call)
