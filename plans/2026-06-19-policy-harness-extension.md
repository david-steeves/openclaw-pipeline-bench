# Plan — Policy Harness Extension (RFC 0012)

**Authored:** 2026-06-18 (MacBook research session, synthesis of 5 parallel researchers)
**Sibling of:** [`implementation.md`](./implementation.md) (the M5 Pro perf-bench plan)
**Spans:** `openclaw-rfcs` (RFC + example teams) + new `openclaw-test-harnesses` repo
**Target executor:** Mac mini M5 Pro, after perf-bench numbers ship to openclaw/rfcs#11
**Next RFC update:** new RFC 0012 (NOT an addendum to 0010 — keeps 0010 focused on substrate)

---

## Why this exists

RFC 0010 establishes the *seams* (raw → processed → curated stage boundaries) where
analyst skills can run. It does not ship example analyst-skill review teams, does
not specify how users compose system-wide and scoped policies, and does not name
the upload/analyze clarifying-prompt surface.

Reviewers landing on the openclaw/rfcs#11 thread will ask:
*"What does this actually look like when someone uses it?"*

This plan answers that with three deliverables:

1. **RFC 0012** — `Reference analyst review teams, layered policy composition, and clarifying prompts`. Documents the patterns. Lives in `openclaw-rfcs/rfcs/0012-…md`.
2. **Reference implementations** in `openclaw-rfcs/rfcs/0012/` — example review teams, policies, control-plane config schema, clarifying-prompt tree. *Shippable code, not pseudo-code.*
3. **Test harness** in new `openclaw-test-harnesses` repo — exercises the reference implementations against mock PHI/PII data, asserts the right BLOCKs and WARNs fire, optionally re-runs the pipeline-bench perf tests against *real claws* instead of synthetic pass-analysts.

---

## Repo architecture

### `openclaw-rfcs` (existing) — additions on a feature branch

```
rfcs/
  0012-analyst-review-teams-and-policy-control-plane.md   # NEW — the RFC doc
  0012/                                                    # NEW — reference impls
    README.md                                              # how to fork these
    control-plane-config-schema.yaml                       # JSON schema for the config
    example-config.yaml                                    # paste-into-your-repo example
    clarifying-prompts/
      schema.yaml                                          # prompt-tree schema
      upload-prompts.example.yaml                          # 2 upload prompts (PHI + jurisdiction)
      analyze-prompts.example.yaml                         # 2 analyze prompts (output-dest + depth)
    policies/
      system/
        block-ssn.yaml                                     # system-wide, always evaluated first
        block-api-key.yaml                                 # system-wide
      shared-lib/
        ssn-detector.yaml                                  # composable rule snippets
        phi-detector.yaml
        pii-co-occurrence.yaml
      teams/                                               # team-scoped policy refs
        hr-pii-warn.yaml                                   # claw-specific
        snowflake-phi-block.yaml                           # claw-specific
    example-teams/
      hr-reviewer/
        team.yaml                                          # team definition
        analysts/
          ssn-detector.py                                  # imports system-wide rule
          pii-cooccurrence-warn.py                         # name + DOB warn
          salary-warn.py
      snowflake-reviewer/
        team.yaml
        analysts/
          phi-marker-block.py                              # MRN/diagnosis_code block
          patient-id-warn.py
          free-text-phi-scan.py                            # scans diagnosis_notes free-text
```

**Rationale:** the RFC repo currently holds docs only. Adding `rfcs/0012/` with
executable Python is a meaningful shift in repo character but it's the right call:
reviewers can *clone and run* the reference rather than infer behaviour from prose.
Renovate-style presets (an `extends:` chain) keep the YAML composable.

### `openclaw-test-harnesses` (NEW repo) — `git@github.com:david-steeves/openclaw-test-harnesses.git`

```
README.md
HANDOFF.md                              # like the bench repo — landing pad for M5 session
mock-data/
  phi-snowflakey/                       # ~1MB CSV, wide-table datamart
    schema.md
    data.csv.gz                         # checked in (gzipped, small)
    annotations.yaml                    # which rows should BLOCK/WARN, why
  hr-pii/                               # ~1MB CSV, employee master
    schema.md
    data.csv.gz
    annotations.yaml
  generators/                           # repro: regenerate the CSVs from seeds
    gen_phi.py                          # Synthea-shaped synthetic
    gen_hr.py                           # Faker-shaped synthetic
harness/
  policy-eval/                          # functional tests: did the policies fire correctly?
    runner.py                           # ingests mock-data, runs review teams, emits verdict tape
    asserts/
      test_system_ssn_block.py
      test_hr_pii_warn.py
      test_snowflake_phi_block.py
      test_policy_composition.py        # system BLOCK trumps scoped WARN
      test_clarifying_prompts_metadata.py  # prompt answers route correctly
    verdict-tape/                       # human-reviewable transcripts of each run
  perf/                                 # perf tests with real claws (not synthetic pass-analysts)
    runner.py                           # delegates to pipeline-bench harness, swap workload
    manifest.yaml                       # variant: pipeline-real-claws
    workload-from-mock.py               # feeds mock-data rows as the synthetic event stream
Makefile
docker-compose.yml                      # for perf runs in containers
```

**Why a separate repo:** mock data and harness code are not part of the RFC
artifact. Keeping them out of `openclaw-rfcs` keeps that repo skimable. The harness
repo can also house future test fixtures for unrelated RFCs.

---

## RFC 0012 — outline

| § | Title | Notes |
|---|---|---|
| 1 | Summary | One paragraph: review teams + layered policies + clarifying prompts, with the reference impl as the spec. |
| 2 | Motivation | RFC 0010 named the seams; RFC 0012 names what runs at them. |
| 3 | Goals | (a) reference review teams, (b) system + scoped policy composition, (c) clarifying-prompt schema, (d) test-harness contract |
| 4 | Non-goals | New substrate, RBAC for who can edit policies, runtime UI for clarifying prompts (schema only). |
| 5 | Architecture | Control plane registers teams + policies + prompts. Substrate (RFC 0010) calls into teams at each seam. Teams emit verdicts in RFC 0003 evidence shape. |
| 6 | Policy composition | **System layer always evaluated first; BLOCK from any layer is final; scoped layer can ADD warns/blocks but cannot downgrade a system verdict.** Precedence: BLOCK > WARN > PASS. |
| 7 | Control-plane config | YAML schema with `extends:` for preset composition; per-team `enabled`, `seams`, `analysts`, `policies`, `severity`, `scope`, `clarifying-prompts`. |
| 8 | Clarifying prompts | Decision-tree schema with skip-logic; answers attach to payload metadata; policy engine reads `metadata.clarifications`. |
| 9 | Reference review teams | `hr-reviewer` + `snowflake-reviewer` — full team configs included as appendix and as runnable code in `rfcs/0012/example-teams/`. |
| 10 | Test harness contract | What `openclaw-test-harnesses` proves: (a) named verdicts fire on annotated mock rows; (b) policy composition correctness; (c) perf cost of real claws vs pipeline-bench synthetic pass-analysts. |
| 11 | Open questions | Cryptographic attestation of redaction (deferred to follow-up RFC, same as 0010). Versioning of preset config. UI for upload/analyze clarifying prompts. |

---

## Mock data — schemas (full versions in `openclaw-test-harnesses/mock-data/*/schema.md`)

### `mock-data/phi-snowflakey/` — wide-table datamart

24 columns, one row per patient-encounter, ICD-10 / LOINC / RxNorm vocabularies.
10 example rows expand to ~250K rows for a ~1MB gzipped CSV (synthesizable from
seed via `generators/gen_phi.py`, Synthea-shaped). Annotated rows include:

- **BLOCK** trigger: any row with non-empty `ssn` AND any of `mrn / diagnosis_code` (system SSN block + scoped PHI block both fire; system wins).
- **WARN** trigger: any row with `patient_id` + `birth_date` + `city` (re-identification vector, scoped warn).
- **PASS** trigger: rows with only billing codes, no demographics.

Columns: `patient_id, last_name, first_name, birth_date, gender, address, city, state, zip_code, phone_number, email, ssn, mrn, encounter_id, encounter_date, diagnosis_code, diagnosis_description, procedure_code, medication_code, medication_name, lab_value, lab_code, lab_code_description, diagnosis_notes`.

The `diagnosis_notes` free-text column is the LLM-analyst seam — free-text PHI
detection is the case where regex-only analysts fail and an LLM analyst should fire.

### `mock-data/hr-pii/` — employee master

16 columns, one row per active employee. ~10K rows for ~1MB gzipped CSV.

- **BLOCK** trigger: `ssn` present + `full_name` present (system SSN block).
- **WARN** trigger: `date_of_birth` + `first_name` + `last_name` co-occurrence with no SSN (claw-specific PII warn).
- **WARN** trigger: `salary` present (claw-specific HR-sensitivity warn).
- **PASS** trigger: rows with `employee_id` + `department` only.

Columns: `employee_id, first_name, last_name, date_of_birth, ssn, email, phone, street_address, city, state, zip, department, job_title, salary, hire_date, employment_status`.

### Annotations file

Each `mock-data/<class>/annotations.yaml` documents the expected verdict per row,
which policy should fire, and which layer should produce the final verdict. The
test harness asserts against this file.

---

## Policy composition — the rule

```
final_verdict = max(system_verdicts ∪ scoped_verdicts)
ordering:      PASS < WARN < BLOCK
constraint:    scoped_verdict ≤ scoped_verdict (scoped cannot downgrade system)
audit_trail:   every layer that fired is recorded; the layer that *won* is named.
```

System-wide policies run first. If they BLOCK, scoped policies still run (for
audit completeness) but their verdicts are advisory — the system BLOCK is final.
If system PASSes, the scoped layer composes via the same max-rule.

This matches AWS IAM's explicit-deny-wins + Microsoft Purview's
most-restrictive-policy-wins semantics. K8s admission controller and OPA precedent
agree.

---

## Control-plane config — `openclaw.config.yaml`

```yaml
version: 1
extends:
  - openclaw-rfcs:rfcs/0012/example-config.yaml   # paste-in default

system_policies:
  - rfcs/0012/policies/system/block-ssn.yaml
  - rfcs/0012/policies/system/block-api-key.yaml

teams:
  hr-reviewer:
    enabled: true
    seams: [raw_to_processed, processed_to_curated]
    analysts:
      - rfcs/0012/example-teams/hr-reviewer/analysts/ssn-detector.py
      - rfcs/0012/example-teams/hr-reviewer/analysts/pii-cooccurrence-warn.py
    policies:
      - rfcs/0012/policies/teams/hr-pii-warn.yaml
    severity_map: { critical: block, high: warn }
    scope:
      data_classes: [hr, payroll]
    clarifying_prompts:
      upload: rfcs/0012/clarifying-prompts/upload-prompts.example.yaml
      analyze: rfcs/0012/clarifying-prompts/analyze-prompts.example.yaml

  snowflake-reviewer:
    enabled: true
    seams: [raw_to_processed, processed_to_curated]
    analysts:
      - rfcs/0012/example-teams/snowflake-reviewer/analysts/phi-marker-block.py
      - rfcs/0012/example-teams/snowflake-reviewer/analysts/patient-id-warn.py
      - rfcs/0012/example-teams/snowflake-reviewer/analysts/free-text-phi-scan.py
    policies:
      - rfcs/0012/policies/teams/snowflake-phi-block.yaml
    severity_map: { critical: block, high: warn }
    scope:
      data_classes: [warehouse, snowflake, healthcare]
    clarifying_prompts:
      upload: rfcs/0012/clarifying-prompts/upload-prompts.example.yaml
```

**User ergonomics:** clone the example, set `enabled: true` on the teams they
want, override 1–2 fields. 2 YAML edits, ship. Renovate-style preset composition
keeps shared templates DRY.

---

## Clarifying prompts — decision-tree schema

Decision-tree YAML with skip-logic, closed answer sets, and metadata attachment.
The prompt schema lives in `rfcs/0012/clarifying-prompts/schema.yaml`; example
prompt trees ship as `upload-prompts.example.yaml` and `analyze-prompts.example.yaml`.

Answer payload attaches to the event as `metadata.clarifications`; policy engine
reads it during evaluation. Example flow:

```
Upload event arrives
  → ask "Does this file contain PHI?"
      yes  → ask "Is it destined for a HIPAA-regulated jurisdiction?"
      no   → skip jurisdiction prompt
      uncertain → triage analyst runs, asks follow-up
  → answers stored on event.metadata.clarifications
  → review teams' seams fire; policies read metadata when deciding verdict
Analyze event arrives
  → ask "Where will results be shared?" (internal | external | public)
      external → ask "Is there a signed DPA?"
        no  → analyze blocked, escalate to legal
  → answers stored on event.metadata.clarifications
```

**Why this matters:** none of the surveyed prior-art (Presidio, Purview, Macie,
DLP) does interactive intent-capture at upload/analyze time. Stripe Radar's
4-action model (block / allow / review / challenge) is the closest precedent.
This is an OpenClaw differentiator — the prompt isn't UI fluff, it's the path
by which analyst skills get the context they need to make non-trivial verdicts.

---

## Test harness — what `make` runs

```
# In openclaw-test-harnesses/

make install            # python 3.13 + uv + (optional) orbstack for perf runs
make gen-data           # regenerate mock-data/*/data.csv.gz from seeds (deterministic)
make policy-test        # ingest mock data → load review teams → assert verdicts vs annotations.yaml
                        # → emit verdict-tape/<ts>/REPORT.md (human-readable)
make perf-test          # delegates to pipeline-bench harness, replays mock-data as event stream
                        # variant: pipeline-real-claws (uses the hr-reviewer + snowflake-reviewer teams)
make perf-test-vs-bench # runs both pipeline-bench's synthetic pass-analyst variants AND
                        # perf-real-claws side-by-side; emits comparison REPORT.md.
                        # This is the "real cost" number for the next RFC update.
make all                # policy-test + perf-test-vs-bench
make clean
```

`make perf-test-vs-bench` is the headline number for the openclaw/rfcs#11 follow-up:
*"the substrate cost is X; with real review teams loaded, the cost is X + Y."*
That's the cost reviewers care about — not the synthetic pass-analyst best-case.

---

## Implementation ordering

Each step is independently verifiable. Sized for a fresh M5 Pro Claude session
to execute in order.

| Step | Repo | Output | Verifiable when |
|---|---|---|---|
| 0 | both | Branches: `openclaw-rfcs:rfc/0012-review-teams`; create `openclaw-test-harnesses` repo | `git ls-remote` succeeds for new repo |
| 1 | openclaw-rfcs | RFC 0012 doc (skeleton, fill prose per outline above) | doc renders cleanly on GitHub |
| 2 | openclaw-rfcs | Control-plane config schema + example-config + clarifying-prompts schemas | `yamllint rfcs/0012/**/*.yaml` clean |
| 3 | openclaw-rfcs | System policies + shared-lib + team-scoped policy YAML | spot-check `block-ssn.yaml` regex matches the annotated SSN rows in mock data |
| 4 | openclaw-rfcs | Example review teams (hr-reviewer + snowflake-reviewer) — analysts in Python, runnable | `python -m hr_reviewer.ssn_detector --in fixtures/ssn-row.json` returns BLOCK |
| 5 | openclaw-test-harnesses | mock-data + generators + annotations | `make gen-data && diff <(zcat data.csv.gz) <(./gen.py --seed N)` is empty |
| 6 | openclaw-test-harnesses | Policy-eval harness (ingest, load teams, assert) | `make policy-test` is green; verdict tape spot-checks |
| 7 | openclaw-test-harnesses | Perf harness (`pipeline-real-claws` variant, delegates to pipeline-bench) | `make perf-test` produces metrics.json |
| 8 | openclaw-test-harnesses | Comparison report generator | `make perf-test-vs-bench` produces side-by-side REPORT.md |
| 9 | openclaw-rfcs | RFC 0012 final pass + open PR; link comparison REPORT.md from `openclaw-test-harnesses` | PR open on `openclaw/rfcs` with reproducible numbers |

## Wall-clock budget

| Step | Estimate |
|---|---|
| 0 — branches + repo creation | 10 min |
| 1 — RFC 0012 prose | 90 min (longest single step — write the case, not the spec only) |
| 2 — config schemas | 45 min |
| 3 — policy YAML | 30 min |
| 4 — example review teams (4–6 small Python files) | 60 min |
| 5 — mock data + generators | 60 min |
| 6 — policy-eval harness | 90 min |
| 7 — perf harness (most reuse from pipeline-bench) | 45 min |
| 8 — comparison reporter | 30 min |
| 9 — RFC 0012 final pass + PR | 30 min |
| **Total** | **~8h** (one focused day on M5 Pro) |

This is intentionally not bundled with the M5 perf-bench plan — that ships first
(~1h 20m next week per `implementation.md`), gives us the bench numbers in
openclaw/rfcs#11, and the policy-harness work follows as a separate session
that builds on those numbers.

---

## Sanity gates (required before posting RFC 0012 PR)

1. **All annotated mock rows produce the documented verdict.** If any row's
   actual verdict differs from `annotations.yaml`, fix or re-annotate before
   shipping — the harness is only useful if it matches the spec.
2. **Policy composition unit tests are green.** Specifically: a row that hits
   both `system/block-ssn` and `claw/hr-pii-warn` returns BLOCK with both
   verdicts in the audit trail (system layer wins, scoped is recorded as
   advisory).
3. **Clarifying-prompt metadata routes correctly.** A row uploaded with
   `clarifications.phi-detection = no` should NOT trigger the PHI-block analyst
   even if the row contains MRN-shaped data (this is the operator-asserted
   exemption path; logged but not enforced).
4. **Perf monotonicity:** `pipeline-noop ≤ pipeline-real-claws-pass-only ≤ pipeline-real-claws-mixed`.
   If real claws beat synthetic pass-analysts, instrumentation is wrong.
5. **Cost delta is citable:** the difference between pipeline-noop and
   pipeline-real-claws is the number that goes in the follow-up to
   openclaw/rfcs#11.

---

## Design decisions surfaced (correct any of these now)

1. **New repo name = `openclaw-test-harnesses`.** Singular `test-harness` was
   considered; plural makes room for future RFCs to add sibling harness sets.
2. **RFC 0012 follow-up vs RFC 0010 addendum:** went with separate RFC. Keeps
   0010 focused on substrate; reviewers can land 0010 on its own.
3. **Example review teams live in `openclaw-rfcs/rfcs/0012/example-teams/`, not
   in the test-harnesses repo.** Reasoning: they're part of the RFC artifact —
   the spec includes a reference implementation. Mock data and the harness that
   exercises them are separate concerns and live in test-harnesses.
4. **Mock data is gzipped CSV checked into the repo + a deterministic generator.**
   The gzipped CSV is the canonical fixture; the generator is the reproducibility
   path. Size budget: ~1MB per dataset compressed.
5. **Policy composition rule:** system always first; BLOCK from any layer is
   final; scoped layer can add but not downgrade. Cited precedent: AWS IAM
   explicit-deny + MS Purview most-restrictive-wins.
6. **Clarifying prompts are decision-tree YAML with closed answer sets and
   skip-logic.** Not free-text. Answers attach as `metadata.clarifications` and
   feed policy evaluation. UI rendering is out of scope for RFC 0012.

## Open questions for David

1. Should this run *before* or *after* the M5 perf-bench in
   `implementation.md`? Default in this plan: after — get RFC 0010 numbers
   posted first, then build the follow-up. Reverse only if you'd rather have
   the integrated story land in one PR thread.
2. RFC 0012 review teams use the names `hr-reviewer` and `snowflake-reviewer`.
   These will end up in upstream docs. Renamings to consider before they bake
   in?
3. `openclaw-test-harnesses` repo: public or private at first? The perf numbers
   are publication-grade; the mock data is synthetic-safe; nothing here is
   confidential. Default = public mirror of openclaw-rfcs.

---

## Sources referenced (research synthesis)

- AWS IAM evaluation logic / MS Purview DLP / K8s admission policy / OPA Rego —
  layered-policy composition precedent.
- Renovate / CodeRabbit / Snyk / CODEOWNERS — review-team config patterns.
- Synthea / MIMIC-IV / HIPAA 18 identifiers / AWS Macie + Cloud DLP detectors —
  PHI mock schema.
- Workday / BambooHR / Faker / AWS Macie + MS Purview + Cloud DLP — HR PII mock
  schema.
- Stripe Radar 4-action model / Qualtrics skip logic / OneTrust intake
  templates — clarifying-prompt UX patterns. Note: none of the surveyed
  prior-art does interactive intent-capture at upload/analyze; this is the
  OpenClaw novelty.

Each section's research writeup is preserved in this session's log.
