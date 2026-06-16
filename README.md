# SFA-Bench v0.3

![SFA-Bench](https://github.com/iotaverbum-core/sfa-bench/actions/workflows/test.yml/badge.svg)

**Sealed Failure Artifacts** — a small, deterministic benchmark for preserving
AI reasoning failures as replayable, tamper-evident historical records.

v0.1 proved that a failure could be sealed and replayed.

v0.2 adds the next layer:

> Not merely failure storage. Failure history.

v0.3 adds deterministic tamper and contamination checks for that history.

Most AI evaluation compresses failure into a score. SFA-Bench keeps the failure
record itself: what failed, why it failed, what family of failure it belongs to,
when it recurred, whether it declined, and whether it went extinct.

**Core rule:** No hidden repair. No gold leakage. No rewritten history.
Evidence → verdict → artifact → ledger → replay → history.

stdlib only · no network · no LLM calls · no repair step.

---

## Public explanation

Read: [Why AI Needs a Memory of Its Own Failed Reasoning](docs/why-ai-needs-failure-memory.md)

Core claim:

> SFA-Bench is not trying to make models smarter. It is trying to make reasoning history harder to falsify.

---

## Quick start

```bash
python invariant_suite.py # prove verifier history-blindness invariants
python run_benchmark.py    # verify all cases, seal FAIL artifacts, append ledger observations
python replay.py           # re-attest artifacts and the hash-chained ledger
python report.py           # inspect recurrence, growth, extinction, and lineage
python tamper_suite.py     # prove corruption attempts are detected in temp copies
```

Optional demo history:

```bash
python seed_history.py     # seed synthetic 2026-2029 history + a lineage chain
python report.py
```

The seeder is clearly marked synthetic. It exists so the historical reporting
subsystem has a multi-year dataset to demonstrate growth, decline, extinction,
and lineage without relying on external model calls.

---

## Tamper & Contamination Suite

```bash
python tamper_suite.py
```

The tamper suite deliberately corrupts temporary copies of artifacts, cases,
taxonomy, and ledger entries, then confirms SFA-Bench detects the corruption
without repairing it.

See [docs/tamper-suite.md](docs/tamper-suite.md).

---

## What changed

### v0.1

- sealed artifacts
- replayability
- artifact hashes
- gold-verdict isolation
- basic failure categories

### v0.2

- hierarchical failure families
- leaf-family classification
- parent/child lineage on artifacts
- append-only occurrence ledger
- ledger hash-chain attestation
- recurrence metrics
- extinction status
- historical reports
- non-destructive v0.1 migration

### v0.3

- deterministic tamper and contamination suite
- edited artifact detection
- edited input, evidence, and candidate detection
- deleted, edited, and reordered ledger-entry detection
- fake lineage parent detection
- taxonomy drift detection
- gold leakage guard
- hidden repair guard
- CI execution of the full trust-layer command set

The benchmark begins answering:

- Is this failure new?
- Has this failure happened before?
- What family does it belong to?
- What descendants emerged from it?
- Is it growing, declining, or extinct?
- Can corruption or contamination attempts be detected?
- How has this reasoning system changed over time?

---

## Repository layout

```text
sfa-bench/
├── README.md
├── run_benchmark.py
├── replay.py
├── report.py
├── migrate.py
├── seed_history.py
├── tamper_suite.py
├── families.json
├── history_config.json
├── artifacts/
│   └── .gitkeep
├── history/
│   └── .gitkeep
├── cases/
│   ├── case_001_grounded_pass/
│   ├── case_002_contradicts_evidence/
│   ├── case_003_fabricated_citation/
│   ├── case_004_unsupported_claim/
│   └── case_005_missing_field/
├── docs/
│   ├── concept.md
│   ├── tamper-suite.md
│   └── why-ai-needs-failure-memory.md
└── sfa/
    ├── __init__.py
    ├── artifact.py
    ├── case.py
    ├── categories.py
    ├── families.py
    ├── hashing.py
    ├── history.py
    ├── ledger.py
    ├── tamper.py
    ├── validation.py
    └── verifier.py
```

---

## Case boundary: no gold leakage

Each directory under `cases/` contains five files:

| file | role | who may read it |
|---|---|---|
| `input.json` | the task / question | verifier |
| `evidence.json` | the facts the answer must be grounded in | verifier |
| `candidate_answer.json` | the model answer under test | verifier |
| `verifier_rules.json` | the rules + verifier version | verifier |
| `expected_verdict.json` | gold label | **scoring only — never the verifier** |

`run_benchmark.py` calls `load_verification_inputs()` first, produces a verdict,
seals failures, appends ledger observations, and only then calls
`load_expected_verdict()` for scoring.

The verifier signature has no gold parameter:

```python
verify(input_obj, evidence_obj, candidate_obj, rules_obj)
```

Gold leakage therefore requires a visible code change.

---

## Failure categories vs failure families

A **category** is the verifier's primary rejection reason:

- `CONTRADICTS_EVIDENCE`
- `UNSUPPORTED_CLAIM`
- `FABRICATED_ENTITY`
- `MISSING_REQUIRED_FIELD`
- `SCHEMA_VIOLATION`

A **family** is the historical grouping used for recurrence and evolution.

`families.json` defines the taxonomy:

```text
unsupported_claim
├── unsupported_number
├── unsupported_attribution
├── unsupported_date
└── unsupported_citation
contradicts_evidence
fabricated_entity
missing_required_field
schema_violation
uncategorized
```

Artifacts store only the leaf family. Parentage and depth are derived from the
taxonomy so the hierarchy does not get duplicated across records.

---

## Sealed artifact v0.2

A failure artifact is written to `artifacts/<case_id>.sealed.json` for every
FAIL. It includes:

```text
schema
case_id
sealed_at
input_hash
evidence_hash
candidate_hash
verifier_version
failure_category
failure_family
failure_explanation
parent_artifact_id
lineage_depth
artifact_hash
```

`artifact_hash` seals every other field. Change the artifact and `replay.py`
reports tampering.

Artifacts are append-only. Re-running the benchmark confirms an existing artifact
instead of overwriting it. If the case changed underneath the artifact, the runner
reports `DIVERGENCE`.

---

## Occurrence ledger

Artifacts record distinct failures. The ledger records observations of failures
over time.

`history/occurrences.jsonl` is append-only and hash-chained. Each line contains:

```text
seq
observed_at
period
run_id
artifact_hash
case_id
category
family
synthetic
prev_hash
entry_hash
```

This means SFA-Bench can distinguish:

- the sealed identity of a failure artifact, and
- the historical recurrence of that failure across runs.

`replay.py` verifies the whole ledger chain. Deleting, inserting, reordering, or
editing a ledger entry breaks the chain.

---

## Historical reporting

`report.py` derives history from the ledger. It writes nothing.

Reports include:

- family status table
- top recurring failures
- fastest growing failures
- longest surviving failures
- extinct failures
- newest failure families
- lineage chains

The key question changes from:

> Did this run pass?

To:

> How has this system's reasoning changed over time?

---

## Extinction rules

`history_config.json` controls period bucketing and extinction logic.

Default:

```json
{
  "period_granularity": "year",
  "extinction": {
    "silent_periods_for_extinct": 1,
    "decline_window": 3
  }
}
```

A family is:

- `active` if it appears in the latest period,
- `declining` if its latest window strictly decreases and remains nonzero,
- `extinct` if it existed before but is silent in the latest period.

---

## What counts as contamination

A run is contaminated if any of these happen:

- **Gold leakage** — `expected_verdict.json` reaches the verifier.
- **Hidden repair** — the candidate answer or evidence is changed so a failed
  answer passes instead of being recorded as a failure.
- **Rewritten history** — sealed artifacts or ledger entries are edited after
  the fact.
- **Verifier laundering** — the verifier is allowed to learn from gold labels or
  expected outcomes and then pretend it judged only evidence.
- **Non-determinism** — network calls, LLM calls, or non-canonical hashing inside
  the verifier path.

v0.3 makes these easier to detect:

- gold is structurally outside the verifier path,
- artifacts are content-sealed,
- the ledger is hash-chained,
- replay recomputes both record-level and history-level integrity,
- the tamper suite deliberately corrupts temporary copies and confirms detection.

---

## Learning without rewriting history

SFA-Bench does not repair answers. It preserves failure.

A future learner may read artifacts and ledger entries, cluster failure families,
and improve future candidates. But it may not rewrite the artifact that recorded
the original failure.

That is the standard:

> AI may learn from failure, but it may not launder failure.

---

## Migration from v0.1

If you have v0.1 artifacts in `artifacts/`, run:

```bash
python migrate.py
```

Migration is additive and non-destructive. v0.1 artifacts are not rewritten. The
script only backfills ledger entries so old sealed failures become part of the
v0.2 historical record.

---

## Philosophy

SFA-Bench is not trying to make a model smarter.

It is trying to give AI a preserved history of failed reasoning.

That matters because intelligence without history keeps rediscovering the same
mistakes. Intelligence with preserved history can accumulate disciplined
self-correction.

The failure record is the product.
