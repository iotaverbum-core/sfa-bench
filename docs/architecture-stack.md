# Architecture Stack

SFA-Bench v0.9 adds deterministic policy-guided retry above failure
fingerprinting while keeping the verifier fixed, offline, replayable, and
CI-safe. It is not a production live-provider integration.

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
-> Failure fingerprinting
-> Policy-guided retry
--- current v0.9 boundary ---
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
- model identity carried as reporting-only transcript/occurrence provenance
- illustrative fixed-condition multi-model transcript fixtures
- sealed occurrence derivation and deterministic per-model fingerprints
- fingerprint reassignment/drop tamper checks and comparison guards
- sealed recurrence-to-directive policy decisions
- explicit threshold, compose-all priority, and escalation/termination rules
- policy-blind verifier and policy mutation/contamination guards
- replay and attestation of sealed artifacts and the ledger chain

Release sequence:

- v0.5 — external candidate provenance boundary
- v0.6 — offline transcript replay boundary
- v0.7 — optional live adapter boundary
- v0.8 — failure fingerprinting
- v0.9 — policy-guided retry

The repo is stable as the deterministic offline instrument with an optional
adapter airlock and fixture fingerprint analysis, not as a live benchmark or
the full future live-agent system.

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

Failure history in this repository is seeded/demo fixture history and local run
observations. The v0.8 fingerprint examples are explicitly illustrative
model-labelled fixtures, not observed multi-model live runs.

Failure fingerprints describe the distribution of observed failure families
under a fixed pack, prompt condition, and taxonomy. `model_id` is a first-class
provenance/reporting grouping axis, but is never a verifier input. Legacy
occurrences without `model_id` resolve to `unknown` and are not rewritten.

Policy-guided retry is implemented only on the generator side. Warnings and
policy decisions may shape the next generation prompt or adapter input, but
must never shape verifier judgment or normalized candidate semantics.

## Roadmap Constraints

Live adapters must be optional and disabled in CI. The v0.9 invariant suite
fails if a live adapter is reachable in CI. The benchmark can remain model-free
by ingesting external candidates or transcripts produced elsewhere.

If a production live adapter is added later, the model must live outside the
sealed deterministic core. Each live attempt must be sealed immediately as raw
source before normalization and verification. The normalized candidate may then
be passed to the verifier, but the live transcript, warning, and provenance must
not be verifier inputs.
