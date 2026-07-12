# SFA-Bench v2.0.0-alpha.1

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

The alpha.1 V2 tranche adds one validity gate before candidate lane
canonicalisation, append-only correction lineage for provisional external
evidence, provider-neutral campaign pre-registration, and deterministic
benchmark locking. It does not add provider capture or change the frozen judge.

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
- No API keys, provider credentials, network access, or live adapter for the
  canonical verification and alpha.1 campaign tooling.

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
runs the 26-command offline set in release order, stops on the first failure, and then
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
11. failure fingerprint re-derivation;
12. policy-guided retry;
13. V2 candidate-output integrity and corrected-evidence lineage; and
14. V2 campaign validation and deterministic lock verification.

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
python release_gate.py --release v2.0.0-alpha.1
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
- v2.0.0-alpha.1: candidate-output integrity, corrected-evidence lineage,
  campaign pre-registration, and benchmark locking

v1.1 adds research capability without weakening the spine. The verifier invariants
hold through every new layer: generators, priors, metrics, and property contracts
may shape or measure proposals, but every accept/reject decision remains a fixed,
deterministic function and no LLM output participates in any verdict. Policy may
shape the next answer; it may never shape the judgment.

In alpha.1, empty, plaintext, malformed, and non-object candidate responses are
classified before lane dispatch and receive zero credit. Valid JSON objects
continue through the existing canonicaliser and fixed scorer path. Campaign and
provider metadata remain evidence only and never become verdict inputs.

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
- invalid candidate text cannot reach a lane canonicaliser or receive default-field credit;
- corrected external evidence is lineage-linked without overwriting its predecessor;
- campaign declarations and candidate manifests validate deterministically offline;
- benchmark locks detect tested changes to prompts, cases, evidence, rules,
  taxonomy, normalisers, adapters, schemas, and protected verifier files;
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

Canonical verification and the alpha.1 correction/campaign commands do not call
live models. The repository preserves historical external candidate evidence,
but provider capture and repeated live campaigns remain outside the trusted core
and CI. SFA-Bench does not rank real providers, prove that a retry policy improves
models, inspect hidden chain-of-thought, or provide guarantees beyond its
implemented checks. The rule-based verifier is intentionally narrow and is not
semantically complete.

Generation reproducibility may be limited; judgment reproducibility is mandatory.

SFA-Bench evidence may support governance review and compliance-oriented
documentation, but passing SFA-Bench does not establish legal or regulatory
conformity.

## V2 alpha.1 offline commands

```bash
python candidate_integrity_check.py
python campaign_protocol_check.py
python campaign_cli.py validate --campaign campaigns/examples/gpt56-draft-preregistration.json
python campaign_cli.py validate-candidate --manifest campaigns/examples/gpt56-draft-candidate-manifest.json
```

The GPT-5.6 files are `draft_not_executed` examples with unconfirmed provider
identifiers. They do not assert API access, execution, a result, or a ranking.

## GroundLedger product layer

A separately versioned commercial layer built on top of this research core lives
in [`product/`](product/) (the `groundledger` package). It is not part of this
research instrument's release line or its DOI. See
[`product/README.md`](product/README.md),
[`product/TRUST_MODEL.md`](product/TRUST_MODEL.md), and
[`product/SECURITY.md`](product/SECURITY.md).

## Documentation

- [Researcher Guide](docs/researcher-guide.md)
- [SFA-Bench White Paper v1: A Grammar for Governed Improvement](docs/research/sfa-bench-whitepaper-v1.md)
- [Claims and Limitations](docs/claims-and-limitations.md)
- [Architecture Stack](docs/architecture-stack.md)
- [Concept](docs/concept.md)
- [Verifier Invariants](docs/invariants.md)
- [SFA-Agent](docs/sfa-agent.md)
- [External Adapter Boundary](docs/external-adapter-boundary.md)
- [V2 Campaign Protocol](docs/research/sfa-bench-v2-campaign-protocol.md)
- [V2 Threat-Model Amendment](docs/research/sfa-bench-v2-threat-model-amendment.md)
- [V2 Architecture Decisions](docs/research/sfa-bench-v2-alpha1-decisions.md)
- [V2 PowerShell Example](examples/v2_campaign_powershell.md)
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
- [AutoLab Controller](docs/autolab-controller.md)
- [AutoLab Human Ratification](docs/autolab-ratification.md)
- [AutoLab Lineage + Rollback](docs/autolab-lineage.md)
- [AutoLab Circuit Breakers](docs/autolab-circuit-breakers.md)
- [AutoLab End-to-End Runner](docs/autolab-runner.md)
- [External Candidate Harness](docs/external-candidate-harness.md)
- [Ratification Packet + Lineage CLI](docs/ratification-packet-lineage-cli.md)
- [Prior State Memory: Why AI Needs Memory Before the Next Mistake](docs/prior-state-memory.md)

## AutoLab Item 7 Usage

For the `fz-v0.7.0` runner workflow, see
[AutoLab Item 7 Runner](docs/autolab-item-7-runner.md), the
[minimal PowerShell flow](examples/autolab_item7_minimal_usage.md), and the
[expected demo outcomes fixture](tests/fixtures/autolab_item7_expected_outcomes.json).

## External Candidate Harness

Item 9 evaluates a committed candidate branch or SHA against `origin/main`,
records changed paths and frozen-path touches, runs protected verification in a
detached temporary worktree, and writes candidate packets under
`out/candidate_packets/<run_id>/`.

```bash
py -3 external_candidate_harness.py --target <commit-sha>
py -3 external_candidate_harness.py --branch <branch-name>
```

See [External Candidate Harness](docs/external-candidate-harness.md), the
[minimal PowerShell flow](examples/external_candidate_harness_minimal_usage.md),
and the [example packet fixture](tests/fixtures/external_candidate_packet_example.json).

## Ratification Packet + Lineage CLI

Item 10 consumes an Item 9 `candidate_packet.json`, records an explicit human
review action, and writes a ratification packet plus lineage record under
`out/ratification_packets/<run_id>/`. It does not auto-promote candidates.

```bash
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --prepare
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --ratify
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --reject
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --halt
```

See [Ratification Packet + Lineage CLI](docs/ratification-packet-lineage-cli.md),
the [minimal PowerShell flow](examples/ratification_packet_cli_minimal_usage.md),
and the [example ratification fixture](tests/fixtures/ratification_packet_example.json).

## Adversarial Candidate Suite

Item 11 checks that unsafe or malformed external-candidate inputs halt or reject
with predictable outcomes in temporary workspaces.

```bash
py -3 adversarial_candidate_suite.py
py -3 adversarial_candidate_suite.py --ci
```

See [Adversarial Candidate Suite](docs/adversarial-candidate-suite.md), the
[minimal PowerShell flow](examples/adversarial_candidate_suite_minimal_usage.md),
and the [adversarial case fixture](tests/fixtures/adversarial_candidate_cases.json).

## v1.0 Research Release Pack

Item 12 collects the governed candidate-improvement path into a reviewer-facing
research release pack. The pack explains the system, bounded claims, limits,
threat model, architecture, reproducibility path, and reviewer commands.

- [Research Release Overview](docs/research/sfa-bench-v1-research-release.md)
- [Claims and Limits](docs/research/sfa-bench-v1-claims-and-limits.md)
- [Reproducibility Guide](docs/research/sfa-bench-v1-reproducibility-guide.md)
- [Threat Model](docs/research/sfa-bench-v1-threat-model.md)
- [Architecture](docs/research/sfa-bench-v1-architecture.md)
- [Reviewer Commands](examples/v1_research_release_commands.md)
- [Checklist Fixture](tests/fixtures/v1_research_release_checklist.json)

## Citation

Use the repository metadata in [`CITATION.cff`](CITATION.cff). A plain-text form:

> Neal, Matthew. (2026). SFA-Bench v2.0.0-alpha.1: Candidate Integrity and Campaign Foundation. https://github.com/iotaverbum-core/sfa-bench

DOI: https://doi.org/10.5281/zenodo.20766587

## License

See [LICENSE](LICENSE).
