# Architecture Stack

SFA-Bench v0.7 introduces the optional live adapter boundary while keeping the
deterministic core offline, replayable, and CI-safe. It is not a production
live-provider integration.

The current repository implements the sealed core through local files,
deterministic verification, tamper-evident records, transcript normalization,
an offline fixture adapter, and CI-safe demos. Live model execution remains
outside the current release boundary.

```text
Benchmark
-> Failure archive
-> Tamper-evident history
-> Verifier invariants
-> Runtime memory
-> External provenance
-> Transcript replay / re-derivation
-> Optional live adapter boundary
--- offline deterministic airlock ---
-> Failure fingerprinting
-> Policy-guided retry
```

## Release Boundary

The current deterministic sealed instrument includes:

- benchmark cases and verifier rules
- sealed failure artifacts
- append-only occurrence ledger
- tamper checks
- verifier history-blindness and normalization-isolation invariants
- generator-side warning generation from failure history
- local external candidate provenance
- offline transcript fixtures and deterministic transcript normalization
- supported transcript verdict re-derivation from sealed normalized inputs
- optional adapter interface and registry
- deterministic offline fixture adapter
- CI guard proving live adapters are unreachable in CI
- adapter boundary demo using the offline transcript flow
- replay and attestation of sealed artifacts and the ledger chain

Roadmap layers beyond v0.7:

- v0.8 - failure fingerprinting across models
- v0.9 - policy-guided retry based on recurring failure families

The repo is stable as the deterministic offline instrument with an optional
adapter airlock, not as the full future live-agent system.

## Core Boundary

Everything in the sealed core must remain deterministic, offline, replayable,
and CI-safe. CI should never require API keys, network access, browser access,
or live model calls.

The verifier remains on the sealed side of the adapter line. It judges only:

- input
- evidence
- normalized candidate
- verifier rules

It must remain blind to history, ledger entries, artifacts, agent runs,
warnings, provenance, adapter metadata, transcript metadata, model metadata, and
gold labels.

The verifier must never receive raw transcript text, prompt text or hashes, raw
model responses, model id, provider name, sampling parameters, adapter state,
API keys, warning history, recurrence profiles, fingerprint data, caution
directives, or provenance metadata.

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
candidate JSON block. v0.7 adds an adapter interface and registry whose default
adapter returns transcript-shaped fixture data. These are still local fixtures,
not live model calls.

No production provider integration is implemented in v0.7. The live adapter
placeholder fails closed unless explicitly enabled and still performs no API,
model, or network call.

Failure history in this repository is seeded/demo fixture history and local
run observations. It is not yet a corpus of observed multi-model live runs.

Failure fingerprinting across models is not implemented. That extension needs
`model_id` or equivalent model identity as a first-class grouping axis.

Policy-guided retry is not implemented. Any future policy guidance must remain
generator-side only. Warnings and prior-attempt context may shape the next
generation prompt, but must never shape verifier judgment.

## Roadmap Constraints

Live adapters must be optional and disabled in CI. The v0.7 invariant suite
fails if a live adapter is reachable in CI. The benchmark can remain model-free
by ingesting external candidates or transcripts produced elsewhere.

If a production live adapter is added later, the model must live outside the
sealed deterministic core. Each live attempt must be sealed immediately as raw
source before normalization and verification. The normalized candidate may then
be passed to the verifier, but the live transcript, warning, and provenance must
not be verifier inputs.
