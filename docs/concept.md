# SFA-Bench Concept

SFA-Bench exists to preserve AI reasoning failures as replayable historical records.

Most AI evaluation compresses failure into a score. SFA-Bench treats the failure record itself as the object of study.

The central question is not only:

> Did the system pass?

The deeper question is:

> What failed, why did it fail, has this kind of failure appeared before, and can the history still be replayed?

## Core thesis

A reasoning system should never lose the history of how it became what it is.

This does not require consciousness, personhood, or subjective memory. It requires disciplined records:

- evidence used,
- candidate answer produced,
- verifier rule applied,
- verdict reached,
- failure category assigned,
- sealed artifact written,
- occurrence logged,
- replay attested.

## Why sealed artifacts matter

A failure that can be quietly rewritten is not evidence. It is a mutable anecdote.

A sealed failure artifact is different. It is content-addressed and tamper-evident. The artifact records the hashes of the input, evidence, candidate answer, verifier version, and failure explanation. If the record changes, the seal breaks.

That gives researchers a stable object for later analysis.

## Why the ledger matters

An artifact proves that one failure was preserved.

A ledger shows when failures recur.

v0.2 adds an append-only occurrence ledger. Each entry links to the previous entry by hash. Deleting, editing, inserting, or reordering history breaks the chain.

This lets SFA-Bench ask historical questions:

- Which failure families recur most often?
- Which are growing?
- Which are declining?
- Which have gone extinct?
- Which failures descend from earlier failures?

## Why no repair step

SFA-Bench intentionally does not repair the candidate answer.

Repair is useful in other systems, but it can also hide contamination. If a benchmark allows hidden repair, it becomes difficult to know whether the final answer came from the evidence, the verifier, or an accidental leak from the gold verdict.

SFA-Bench therefore keeps the pipeline narrow:

```text
input -> evidence -> candidate -> verifier -> artifact -> ledger -> replay -> report
```

The verifier must never read `expected_verdict.json` during verification. Gold verdicts are for scoring after the verifier has already produced its own verdict.

## What success looks like

A stranger should be able to clone the repo, run the benchmark, and inspect the output without trusting the author personally.

The repo should prove its own basic claims:

```bash
python run_benchmark.py
python replay.py
python report.py
```

If those commands pass, the repository demonstrates the first trust layer: failure preservation, replayability, and tamper-evident history.

As of v0.8, the stable implementation is the deterministic offline instrument:
benchmark, failure archive, tamper-evident history, verifier invariants,
generator-side runtime memory, external provenance, transcript replay /
re-derivation, optional live adapter boundary, offline fixture adapter, and
fixed-condition failure fingerprinting over illustrative fixtures.

SFA-Bench v0.8 does not run live models in CI, include production provider API
calls or observed provider results, claim absolute model behaviour, or
implement policy-guided retry.

## What SFA-Bench is not

SFA-Bench is not a larger model.

It is not an agent framework.

It is not a retrieval system.

It is not a self-repair loop.

It is a minimal benchmark for preserving, replaying, classifying, and historically analyzing AI reasoning failures without rewriting the record.
