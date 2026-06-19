# Architecture Stack

SFA-Bench v1.0.0 is the researcher-readiness release of the completed pre-1.0
research stack. v1.0 adds reproducibility and release hardening; it does not add
a new capability layer.

```text
benchmark
↓
failure archive
↓
tamper-evident history
↓
verifier invariants
↓
external provenance
↓
offline transcript replay
↓
optional live adapter boundary
↓
failure fingerprinting
↓
policy-guided retry
```

## Layer responsibilities

### Benchmark and failure archive

The benchmark loads task input, evidence, a candidate, and verifier rules. The
deterministic verifier emits a verdict before the expected verdict is loaded for
scoring. Failures are content-addressed and sealed; existing sealed records are
never silently overwritten.

### Tamper-evident history

Failure occurrences are appended to a hash-chained ledger. Replay independently
checks artifact seals, available case material, reproduced verdict/family, and
ledger-chain continuity. The tamper suite exercises specified mutation and
contamination cases in temporary copies.

### Verifier invariant spine

Verifier invariants are a continuing spine through the architecture, not a
one-time layer. Every later layer must preserve the same judgment boundary:

```text
verifier input = task input + evidence + normalized candidate + fixed rules
```

History, gold labels, raw transcripts, prompts, provenance, model identity,
adapter metadata, fingerprint summaries, recurrence profiles, policy decisions,
and warnings are excluded.

### External provenance and transcript replay

External candidates are ingested from local JSON and their raw-source and
normalized-candidate hashes are recorded outside the verifier. Offline
transcript fixtures add prompt/raw-response preservation and deterministic
normalization. Supported transcript verdicts can be re-derived from sealed
normalized inputs.

### Optional adapter boundary

Adapters are proposer-side only. The default fixture adapter is offline. The
live placeholder has no provider integration, is disabled by default, and is
unreachable when `CI=true`. An adapter produces a transcript; normalization
extracts the candidate; only that candidate crosses the verifier boundary.

### Failure fingerprinting

Fingerprinting aggregates sealed fixture outcomes under fixed case, evidence,
prompt, adapter, transcript, and taxonomy conditions. The fixture model IDs are
illustrative. Fingerprints are reporting data, not verifier inputs and not
real-world model rankings.

### Policy-guided retry

The policy layer deterministically maps sealed recurrence profiles to
generator-side directives and escalation. Generator-side memory may shape
proposals, and policy may shape the next answer. Policy may never shape the
judgment. The verifier remains fixed, history-blind, and policy-blind.

## Trust and data flow

```text
raw source / fixture
        |
        v
proposer or adapter -----> provenance and raw-source seal
        |
        v
normalized candidate
        |
        v
fixed verifier <--------- input + evidence + rules
        |
        +---- PASS ------> score/report
        |
        +---- FAIL ------> sealed artifact --> occurrence ledger
                                              |
                                              v
                                  replay / fingerprint / policy
                                              |
                                              v
                                  generator guidance only
```

The return edge ends at the generator. There is no edge from history, a
fingerprint, or policy into verifier judgment.

## Versioned stack

- v0.1 — benchmark and failure archive
- v0.2 — sealed artifacts and occurrence ledger
- v0.3 — tamper and contamination suite
- v0.4 — minimal agent loop and invariant spine
- v0.5 — external candidate provenance boundary
- v0.6 — offline transcript replay boundary
- v0.7 — optional live adapter boundary
- v0.8 — failure fingerprinting
- v0.9 — policy-guided retry
- v1.0 — researcher readiness and reproducibility hardening

Internal artifact, taxonomy, adapter, fingerprint, and policy schema versions
remain independently versioned. The project release label does not imply a
verifier or taxonomy version change.

## Operational boundary

The canonical verification path is fully offline:

```bash
python verify_all.py
python release_gate.py --ci
```

No API key, provider credential, model execution, network call, or live adapter
is required. Any future live provider integration must remain optional,
proposer-side, immediately seal raw source, and stay outside offline CI and the
verifier boundary.
