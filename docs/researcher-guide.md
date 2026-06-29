# SFA-Bench Researcher Guide

## Research problem

Most evaluation pipelines retain aggregate scores and discard the exact failure
record. That makes later questions difficult: what failed, under which evidence
and rules, whether the record changed, whether a failure recurred, and whether a
later verdict was influenced by history.

SFA-Bench treats the failure record as the research object. It is a deterministic
offline harness for preserving failures, attesting them later, and testing a
narrow set of trust-boundary invariants. It is not a live model study.

## Architecture

The stack is cumulative:

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

The verifier invariants are the spine of the stack, not a completed historical
phase. Candidate generators, transcript adapters, history summaries, fingerprint
reports, and policy decisions remain outside verifier judgment.

Generator-side memory may shape a proposal. A deterministic policy may shape the
next answer. Neither may shape the judgment: the verifier receives only the
case input, evidence, normalized candidate, and verifier rules.

See [Architecture Stack](architecture-stack.md) for component details.

## Run from a clean clone

Requirements are Python 3.11+ and Git. No dependency installation, secret,
network connection, model call, or live adapter is required.

```bash
git clone https://github.com/iotaverbum-core/sfa-bench.git
cd sfa-bench
python verify_all.py
```

The full runner creates an isolated temporary copy and executes the twelve
release commands there. This design lets mutation-producing demos run without
changing the checked-out ledger or leaving runtime directories in the clone.
The runner reports the path if operating-system permissions prevent automatic
temporary-worktree cleanup.

To inspect the main flow interactively:

```bash
python run_benchmark.py
python replay.py
python report.py
```

This direct flow can append ledger observations and create ignored artifacts.
Use it when those records are part of the investigation. Use `verify_all.py` for
a non-mutating release verification.

## Interpret the main outputs

`run_benchmark.py` prints one verdict per case, expected-verdict agreement, the
number of newly sealed artifacts, and ledger observations. Expected verdicts are
loaded only after a verdict exists; they score the verifier and are not verifier
inputs.

`replay.py` independently reports:

- seal integrity and case-input consistency for artifacts; and
- hash-chain integrity for occurrence history.

An `ATTESTED` result means the checked records satisfy the implemented replay
checks. It does not prove every possible attack is impossible.

`report.py` summarizes recurrence, growth, survival, extinction, new families,
and lineage from the occurrence ledger. Those are descriptions of recorded
fixtures and observations, not population estimates about models.

`rederive.py` verifies supported transcript replay records from sealed normalized
inputs. `fingerprint_report.py` rebuilds the illustrative fixed-condition report.
`policy_demo.py` demonstrates deterministic generator guidance and confirms that
policy metadata is absent from verifier inputs.

## What fixtures mean

Files under `cases/` are small deterministic verifier cases. They exercise a
fixed rule/evidence boundary and expected outcomes. Files under
`examples/external_transcripts/`, `examples/fingerprints/`, and
`examples/policy/` are reproducibility fixtures for the corresponding layers.

Model-like identifiers in fingerprint fixtures are labels for illustrative data.
They are not evidence that named or production models produced those records.
Results are conditioned on the checked-in case set, evidence pack, prompt and
adapter framing, transcript fixtures, taxonomy, and implementation version.

## Inspect tamper and invariant results

Run:

```bash
python tamper_suite.py
python invariant_suite.py
```

The tamper suite applies controlled mutations in temporary copies. Each `PASS`
means the relevant implemented check detected or rejected that mutation. Review
the named case to understand the scope; the suite is a set of tested corruption
classes, not a universal security proof.

The invariant suite tests history-blind verification, gold isolation, adapter and
transcript metadata isolation, deterministic fingerprinting, policy/verifier
separation, and repository version-of-record consistency. A passing invariant
means the checked call paths and fixtures obey that boundary under the test
conditions.

## Reproducibility and release checks

Before release clearance, run:

```bash
python verify_all.py
python release_gate.py --release v1.0.0
git status --short --untracked-files=all
```

The release gate separately inspects untracked files, protected files, staged
runtime output, generated sealed artifacts, CI command coverage, command headers,
and the package version of record (`sfa.__version__`). It fails when the package
version, the gate's expected release, or any command header disagree on the
release. `git diff --name-only` is useful for tracked changes but is insufficient
because it omits untracked files.

## Supported interpretation

The repository supports claims about determinism and separation under the
checked-in implementation and fixtures: replay of sealed artifacts and the
ledger, re-derivation of supported transcript verdicts, tested verifier
history-blindness and metadata isolation, fixed-condition fingerprint
determinism, and deterministic generator-side policy decisions.

It does not support claims about real-world model rankings, provider performance,
universal tamper resistance, hidden reasoning correctness, policy-caused model
improvement, or semantic completeness. See [Claims and
Limitations](claims-and-limitations.md) for the normative statement.

## Citation

Use `CITATION.cff` from the repository root. The release citation is:

> Neal, Matthew. (2026). SFA-Bench v1.0.0: Researcher Readiness & Reproducibility. https://github.com/iotaverbum-core/sfa-bench

SFA-Bench can be cited using its Zenodo DOI:

DOI: https://doi.org/10.5281/zenodo.20766587

When reporting results, also identify the repository commit, fixture set,
taxonomy version, and command used. This is necessary to make a deterministic
result independently reproducible.
