# SFA-Bench v1.1.0

![SFA-Bench](https://github.com/iotaverbum-core/sfa-bench/actions/workflows/test.yml/badge.svg)

SFA-Bench is a deterministic benchmark harness for preserving AI reasoning failures as replayable, tamper-evident historical records.

## What SFA-Bench is

SFA-Bench is a small, model-agnostic, offline research instrument. It evaluates
fixture candidate answers against explicit evidence and rules, seals failures,
records occurrences in a hash-chained ledger, and replays those records to test
whether the evidence, candidate, verdict, taxonomy assignment, and history remain
consistent.

The repository also demonstrates isolated transcript normalization, an optional
and disabled-by-default adapter boundary, deterministic failure fingerprints, and
generator-side retry policy. These layers preserve a fixed, history-blind
verifier boundary.

## What this is not

- Not a live model leaderboard.
- Not a production provider integration.
- Not a claim that fixture data represents real model behaviour.
- Not a replacement for human evaluation.
- Not a verifier that learns from history.
- Not a claim that every possible form of tampering is impossible.

See [Claims and Limitations](docs/claims-and-limitations.md) before interpreting
results.

## Requirements and installation

- Python 3.11 or later.
- Git, for the release gate.
- No third-party Python packages.
- No API keys, provider credentials, network access, or live adapter.

From a clean clone:

```bash
git clone https://github.com/iotaverbum-core/sfa-bench.git
cd sfa-bench
python verify_all.py
```

There is no package-install step. Run commands from the repository root.

## Quickstart

Run the benchmark, attest the generated records, and inspect history:

```bash
python run_benchmark.py
python replay.py
python report.py
```

`run_benchmark.py` may create ignored sealed artifacts and append observations to
`history/occurrences.jsonl`. For reproducible full verification without changing
the checked-out ledger, use the isolated runner below.

## Run everything offline

```bash
python verify_all.py
```

`verify_all.py` copies the current source into a temporary isolated worktree,
runs all twelve commands in release order, stops on the first failure, and then
removes the temporary worktree. The checked-out occurrence ledger and runtime
directories are not modified. The environment forces CI mode and disables
adapter-selection environment variables. If operating-system permissions prevent
cleanup, the retained `.verify-all-*` runtime path is printed explicitly and can
be removed after inspection.

The command covers:

1. benchmark execution;
2. artifact and ledger replay;
3. history reporting;
4. tamper and contamination checks;
5. verifier invariants;
6. the SFA-Agent demo;
7. external candidate provenance;
8. transcript normalization;
9. transcript verdict re-derivation;
10. the offline adapter boundary;
11. failure fingerprint re-derivation; and
12. policy-guided retry.

For individual non-mutating checks:

```bash
python replay.py
python rederive.py
python invariant_suite.py
python fingerprint_report.py
python policy_demo.py
```

## Release gate

```bash
python release_gate.py
python release_gate.py --ci
python release_gate.py --release v1.1.0
```

The gate explicitly runs `git status --short --untracked-files=all`; it never
treats `git diff --name-only` as release clearance. It fails for untracked files,
changes to protected history/verifier/taxonomy paths, staged runtime or generated
sealed output, incomplete CI command coverage, and command headers or a package
version of record (`sfa.__version__`) that disagree with the declared release. See
[Prior State](docs/prior-state.md).

## Architecture and release stack

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

- v0.1 — deterministic benchmark and failure archive
- v0.2 — sealed artifacts and occurrence history
- v0.3 — tamper and contamination checks
- v0.4 — minimal SFA-Agent loop and invariant spine
- v0.5 — external candidate provenance boundary
- v0.6 — offline transcript replay boundary
- v0.7 — optional live adapter boundary
- v0.8 — deterministic failure fingerprinting
- v0.9 — deterministic generator-side policy-guided retry
- v1.0 — researcher readiness, reproducibility, release automation, and claims discipline
- v1.1 — AGI-axis research extension: prior-state trial, deferred-consequence task
  family, recurrence-decline metric, gold-absent property contract, and causal-edge
  taxonomy (schema v2)

v1.1 adds research capability without weakening the spine. The verifier invariants
hold through every new layer: generators, priors, metrics, and property contracts
may shape or measure proposals, but every accept/reject decision remains a fixed,
deterministic function and no LLM output participates in any verdict. Policy may
shape the next answer; it may never shape the judgment.

See [Architecture Stack](docs/architecture-stack.md) for data-flow and trust
boundaries.

## Core guarantees

Under the checked-in fixtures and implemented checks:

- sealed artifacts replay against current inputs, evidence, candidates, and rules;
- the occurrence ledger is verified as a hash chain;
- covered artifact, ledger, lineage, taxonomy, and contamination mutations are detected;
- verifier history-blindness and metadata isolation are tested;
- transcript normalization is isolated from verifier inputs;
- live adapters are optional, disabled by default, and blocked in CI;
- failure fingerprints are deterministic under fixed fixture conditions;
- policy decisions are deterministic, generator-side, and excluded from verifier judgment; and
- the package version of record, the release gate, and every command header are verified to declare a single release version.

## Interpreting fixtures

Cases and transcript packs are deterministic test fixtures. Model labels in the
fingerprint demo are illustrative identifiers, not observations of production
models. Passing the suite establishes reproducibility of the repository's
implemented checks; it does not establish external model quality or semantic
completeness.

The [Researcher Guide](docs/researcher-guide.md) explains outputs, fixture scope,
and supported interpretations.

## Limitations

SFA-Bench does not call live models, rank real providers, prove that a retry
policy improves models, inspect hidden chain-of-thought, or provide security
guarantees beyond its implemented canonical hashing, sealing, replay, and test
checks. The rule-based verifier is intentionally narrow and is not semantically
complete.

## GroundLedger product layer

A separately versioned commercial layer built on top of this research core lives
in [`product/`](product/) (the `groundledger` package). It is not part of this
research instrument's release line or its DOI. See
[`product/README.md`](product/README.md),
[`product/TRUST_MODEL.md`](product/TRUST_MODEL.md), and
[`product/SECURITY.md`](product/SECURITY.md).

## Documentation

- [Researcher Guide](docs/researcher-guide.md)
- [Claims and Limitations](docs/claims-and-limitations.md)
- [Architecture Stack](docs/architecture-stack.md)
- [Concept](docs/concept.md)
- [Verifier Invariants](docs/invariants.md)
- [SFA-Agent](docs/sfa-agent.md)
- [External Adapter Boundary](docs/external-adapter-boundary.md)
- [Failure Fingerprinting](docs/failure-fingerprinting.md)
- [Policy-Guided Retry](docs/policy-guided-retry.md)
- [Tamper Suite](docs/tamper-suite.md)
- [Prior State](docs/prior-state.md)
- [Prior State Trial](docs/prior-state-trial.md)
- [Deferred-Consequence Task Family](docs/deferred-consequence.md)
- [Recurrence-Decline Metric](docs/recurrence-decline.md)
- [Property-Based Verifier Contract](docs/property-contract.md)
- [Causal-Edge Taxonomy (Schema v2)](docs/causal-edges.md)
- [AutoLab Frozen Zone](docs/autolab-frozen-zone.md)
- [AutoLab Pre-registration Gate](docs/autolab-preregistration.md)
- [AutoLab Loop Controller](docs/autolab-loop-controller.md)
- [AutoLab Promotion / Rollback](docs/autolab-promotion-rollback.md)
- [Prior State Memory: Why AI Needs Memory Before the Next Mistake](docs/prior-state-memory.md)

## Citation

Use the repository metadata in [`CITATION.cff`](CITATION.cff). A plain-text form:

> Neal, Matthew. (2026). SFA-Bench v1.1.0: AGI-Axis Research Extension. https://github.com/iotaverbum-core/sfa-bench

DOI: https://doi.org/10.5281/zenodo.20766587

## License

See [LICENSE](LICENSE).
