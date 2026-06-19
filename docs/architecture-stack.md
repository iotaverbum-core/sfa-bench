# Architecture Stack

SFA-Bench v0.6 is stable as a deterministic offline instrument. It is not yet a
full live-agent system.

The current repository implements the sealed core through local files,
deterministic verification, tamper-evident records, transcript normalization,
and CI-safe demos. Live model use remains outside the current release boundary.

```text
Benchmark
↓
Failure archive
↓
Tamper-evident history
↓
Verifier invariants
↓
Runtime memory
↓
External provenance
↓
Transcript replay / re-derivation
—— offline deterministic airlock ——
Live model boundary
↓
Failure fingerprinting
↓
Policy-guided retry
```

## Release Boundary

Layers 1-7 describe the current deterministic sealed instrument:

- benchmark cases and verifier rules
- sealed failure artifacts
- append-only occurrence ledger
- tamper checks
- verifier history-blindness and normalization-isolation invariants
- generator-side warning generation from failure history
- local external candidate provenance
- offline transcript fixtures and deterministic transcript normalization
- supported transcript verdict re-derivation from sealed normalized inputs
- replay and attestation of sealed artifacts and the ledger chain

Layers 8-10 describe the live/frontier roadmap:

- optional live model adapters
- failure fingerprinting across models
- policy-guided retry based on recurring failure families

The repo is stable as the deterministic offline instrument, not as the full
future live-agent system.

## Core Boundary

Everything in the sealed core must remain deterministic, offline, replayable,
and CI-safe. CI should never require API keys, network access, browser access,
or live model calls.

The boundary between replay/provenance and live model use is a fault line, not a
soft seam. The verifier remains on the sealed side of that line. It judges only:

- input
- evidence
- candidate
- verifier rules

It must remain blind to history, ledger entries, artifacts, agent runs,
warnings, provenance, adapter metadata, transcript metadata, model metadata, and
gold labels.

Verifier invariants are not a single completed rung. They are a spine that must
continue to guard every future layer.

## Current Limitations

`replay.py` currently attests sealed artifacts and the occurrence ledger chain.
When a source case still exists, it checks case hashes and verifier/category
stability for that case. Transcript replay re-derivation is handled by
`rederive.py` for supported transcript replay records.

The v0.5 raw-source/provenance flow is local JSON and appears candidate-shaped.
v0.6 adds offline transcript fixtures with prompt text or prompt hash, raw
response text, placeholder model metadata, and deterministic extraction of one
candidate JSON block. These are still local fixtures, not live model calls.

Failure history in this repository is seeded/demo fixture history and local
run observations. It is not yet a corpus of observed multi-model live runs.

Failure fingerprinting across models is not implemented. That extension needs
`model_id` or equivalent model identity as a first-class grouping axis.

Policy-guided retry is not implemented. Any future policy guidance must remain
generator-side only. Warnings and prior-attempt context may shape the next
generation prompt, but must never shape verifier judgment.

## Roadmap Constraints

Live adapters must be optional and disabled in CI. The benchmark can remain
model-free by ingesting external candidates or transcripts produced elsewhere.

If a live adapter is added later, the model must live outside the sealed
deterministic core. Each live attempt must be sealed immediately as raw source
before normalization and verification. The normalized candidate may then be
passed to the verifier, but the live transcript, warning, and provenance must
not be verifier inputs.
