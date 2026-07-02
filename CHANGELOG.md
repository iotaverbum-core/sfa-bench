# Changelog

All notable changes to SFA-Bench will be documented in this file.

## Unreleased

### Added (AGI-axis extension, toward v1.1.0)

- **Prior State Trial harness** (`sfa/prior_state_trial.py`, `prior_state_trial.py`):
  a controlled, three-arm measurement of whether a matured lesson (prior) injected
  into the proposer improves outcomes, scored entirely by the deterministic
  verifier. Arms: `true_prior`, length/format-matched `placebo_prior` (the
  headline control), and `baseline`. Per-arm mean, W/L/D, and a fixed-seed
  bootstrap 95% CI on the `true_prior − placebo` delta. Sealed hash-chained report
  with a `report_sha`; offline deterministic `replay <report>` mode; `--live` fails
  closed (user-supplied adapter/key, never in CI). Determinism invariant added to
  the invariant suite; CLI dry-run added to `verify_all.py`. See
  [docs/prior-state-trial.md](docs/prior-state-trial.md).

- **Deferred-consequence task family v0** (`sfa/deferred_consequence.py`,
  `deferred_consequence.py`): a HOP3-03-class probe for failing to propagate an
  update through a deferred consequence. A premise at `T` sets `X = v0`; an update
  at `T+u` (`1 ≤ u ≤ k`) sets `X := v1`; the query binds at the horizon `T+k`,
  where the correct answer is the propagated `v1` and the characteristic failure
  preserves the stale `v0`. Horizon `k` is parameterised (default `{1, 3, 5}`),
  with four rotating surface skins (`inventory`, `ledger_balance`,
  `access_policy`, `document_status`) over one invariant logical core. Cases are
  deterministic (SHA-256-seeded, no wall-clock time), sealed with a `case_hash`
  and a chained `pack_hash`, and replay byte-for-byte. Gold isolation: the
  proposer-facing view carries only ordered episodes and the query, while the
  gold-bearing scoring evidence stays verifier-side. Scoring is the fixed SFA
  verifier (zero LLM): the propagated answer passes and the stale answer fails as
  `CONTRADICTS_EVIDENCE`. Determinism invariant added to the invariant suite; CLI
  dry-run added to `verify_all.py`. See
  [docs/deferred-consequence.md](docs/deferred-consequence.md).

- **Recurrence-decline metric** (`sfa/recurrence_metric.py`,
  `recurrence_metric.py`): a continual-learning score computed as a pure function
  of the append-only, hash-chained occurrence ledger. For each failure fingerprint
  (default: the failure `family`) it builds a per-epoch recurrence series over the
  ledger's own `period` buckets and scores the decline from the fingerprint's peak
  epoch to the final epoch, `decline_score = (peak − final) / peak ∈ [0, 1]`
  (`1.0` = eliminated), with `eliminated` and `monotone_post_peak` trajectory
  flags. Aggregates: mean `continual_learning_score` and a peak-weighted variant.
  Sealed with a `metric_hash`; `compute_from_path` attests the ledger chain and
  refuses a tampered one. Ships with a hand-verifiable synthetic ledger fixture
  (`examples/recurrence/synthetic_ledger.jsonl`) whose exact scores are pinned by
  a unit test in the invariant suite. See
  [docs/recurrence-decline.md](docs/recurrence-decline.md).

- **Property-based verifier contract for gold-absent tasks**
  (`sfa/property_contract.py`, `property_contract.py`): a gold-absent verdict path
  that decides accept/reject from decidable properties instead of a stored gold
  answer. Four property families — `schema_validity`, `citation_grounding`,
  `internal_consistency`, and `invariant_preservation` (with `temporal_recency`
  and `value_admissibility` invariants) — each a pure deterministic predicate. The
  contract is versioned and sealed (`contract_hash`); the verdict is the
  deterministic conjunction (`all`) of its properties, sealed with a
  `verdict_hash`. Wires the item-2 deferred-consequence family: `temporal_recency`
  decides correctness from the sealed timeline (the propagated answer passes; the
  stale answer fails `recency`) with no gold label. Property definitions are sealed
  and never enter a proposer prompt. Determinism/behaviour invariant added to the
  suite; CLI dry-run added to `verify_all.py`. The fixed `sfa/verifier.py` is
  unchanged. See [docs/property-contract.md](docs/property-contract.md).

### Taxonomy

- Added two **additive** failure-family leaves, `deferred_consequence` and its
  child `deferred_consequence_stale`, to `families.json` for the deferred-
  consequence family's fingerprint support. The change is backward compatible: the
  family-set is a superset of the prior one, and `classify_family` refines a
  contradiction to `deferred_consequence_stale` only when scoring evidence is
  marked `task_family == "deferred_consequence"`. Evidence without that marker
  classifies exactly as before, so existing artifacts, the ledger, and the
  fingerprint demo re-derive byte-for-byte unchanged. No `taxonomy_version` bump:
  formal taxonomy schema versioning/migration is deferred to the causal-edge work.

### Not Changed

- No verifier behaviour or `sfa/verifier.py` change; no `sfa/categories.py`
  change. No LLM output participates in any verdict.
- No API, model, provider, or network calls in CI.

## v1.0.4 — Release-gate version-of-record enforcement (2026-06-29)

### Fixed

- Corrected the package version of record: `sfa.__version__` was left at `0.9.0`
  while the README, changelog, command headers, and the release gate's
  `EXPECTED_RELEASE` all declared `v1.0.0`. It now declares `1.0.0`.

### Added

- Release-gate enforcement that the package version of record (`sfa.__version__`)
  matches `EXPECTED_RELEASE`, and that every command header declares that same
  release. Replaces the prior v0-only stale-header check with a release-aware one.
- `assert_repository_version_consistency` invariant, run by `invariant_suite.py`,
  so the same drift fails closed on the offline CI path and not only at the gate.

### Not Changed

- No verifier change.
- No taxonomy change.
- No runtime verdict, fingerprint, or policy behaviour change.
- No API, model, provider, or network calls.
- The in-code version of record stays `1.0.0`; v1.0.x tags track documentation
  and release-tooling patches, consistent with v1.0.1–v1.0.3.

### Not Included

- The GroundLedger product layer (`product/`) is a separate commercial artifact
  versioned independently (see `product/CHANGELOG.md`). It is intentionally not
  part of this research-instrument release line or its DOI.

## v1.0.3 — DOI and Citation Update (2026-06-19)

### Added

- Documentation/metadata-only release adding the Zenodo DOI to the README,
  researcher documentation, and citation metadata.

### Not Changed

- No verifier change.
- No taxonomy change.
- No runtime behaviour change.
- No API, model, or network calls.
- No live provider integration.

## v1.0.2 — Zenodo DOI Bootstrap (2026-06-19)

### Purpose

- Documentation/metadata-only release created to trigger Zenodo DOI archiving
  now that the Zenodo GitHub integration is enabled.

### Not Changed

- No verifier change.
- No taxonomy change.
- No runtime behaviour change.
- No live provider integration.

## v1.0.1 — Prior State Memory (2026-06-19)

### Added

- Prior State Memory article naming and explaining the run-start discipline of
  surfacing a previous failure, its correction, and its prevention rule before
  the next action begins.

### Not Changed

- Documentation-only release with no verifier change.
- No taxonomy change.
- No runtime behaviour change.
- No API, model, provider, or network calls.

## v1.0.0 - 2026-06-19

### Added

- Researcher-readiness and clean-clone reproducibility release.
- Stdlib-only `release_gate.py` with explicit untracked-file, protected-path,
  staged-runtime, generated-artifact, CI-coverage, and command-header checks.
- Stdlib-only `verify_all.py` full offline verification runner using an isolated
  temporary worktree so checked-out history is not mutated.
- Researcher guide, claims and limitations, and Prior State development note.
- Consolidated offline CI commands and a canonical human verification command.

### Changed

- Reworked the README quickstart, architecture, guarantees, limitations, and
  citation guidance for a fresh researcher.
- Clarified supported and unsupported claims across the documentation.
- Updated project and user-facing command labels to v1.0.0.

### Not Changed

- No verifier behaviour or verifier version change.
- No taxonomy or taxonomy version change.
- No live model, API, provider, or network calls.
- No required secrets or live adapters in CI.
- No new research-layer capability beyond hardening and documentation.

## v0.9.0 - 2026-06-19

### Added

- Deterministic policy-guided retry from sealed recurrence profiles.
- Versioned `count >= 2` recurrence threshold and fixed compose-all family order.
- Generator-side directives for `fabricated_entity`, `contradicts_evidence`,
  `unsupported_claim`, and `missing_required_field`.
- Deterministic level-2 constraints and level-3 stop/human-review termination.
- Sealed policy input, recurrence-profile, config, and decision hashes.
- Illustrative single-family, multi-family, escalation, and termination fixtures.
- Offline `policy_demo.py`, policy determinism/composition/escalation invariants,
  and policy mutation/contamination tamper checks.
- Minimal SFA-Agent integration that sends policy output only to the retry adapter.

### Not Added

- No production provider results or live-model repair claims.
- No API, model, or network calls.
- No stochastic or LLM-selected policy.
- No verifier changes.
- No taxonomy changes.

## v0.8.0 - 2026-06-19

### Added

- Deterministic failure-family fingerprinting grouped by transcript provenance
  `model_id`.
- Fixed-condition metadata for evidence pack, case set, prompt/adapter framing,
  transcript fixture set, and taxonomy version.
- Fifteen clearly illustrative transcript fixtures for three fake model IDs,
  all evaluated against the same fixed case and evidence pack.
- Per-model attempts, pass/fail counts, pass rates, family counts and rates,
  dominant family, recurrence summary, and sealed fingerprint input hashes.
- `fingerprint_report.py` for offline fixture normalization, verification,
  occurrence sealing, deterministic aggregation, and report re-derivation.
- Fingerprint tamper checks for model reassignment and dropped occurrences.
- Invariants for fingerprint-blind verification, deterministic derivation, and
  refusal to compare mismatched fixed conditions.
- Backward-compatible `unknown` reporting identity for legacy occurrences that
  have no `model_id`.

### Not Added

- No production provider results or default live-model benchmarking.
- No API, model, or network calls.
- No live calls in CI.
- No policy-guided retry.
- No verifier changes.
- No taxonomy changes.

## v0.7.0 - 2026-06-19

### Added

- Optional live adapter boundary at the proposer side.
- `sfa.adapters` interface and registry for transcript-producing adapters.
- Deterministic offline fixture adapter, `fixture-transcript-adapter-v0`.
- Fail-closed live adapter placeholder that is disabled by default and
  unavailable in CI.
- CI live-adapter unreachability invariant.
- Adapter-airlock and adapter-metadata-blindness invariant coverage.
- `adapter_demo.py`, which uses the offline fixture adapter and v0.6 transcript
  normalization / re-derivation flow.
- CI execution of `adapter_demo.py`.

### Not Added

- No production provider integration.
- No live model calls in CI.
- No API key requirement.
- No model fingerprinting.
- No policy-guided retry.
- No verifier changes.
- No taxonomy changes.

## v0.6.0 - 2026-06-19

### Added

- Offline model-style transcript fixtures.
- Deterministic transcript normalizer that extracts exactly one fenced JSON
  candidate block and fails closed on ambiguity or invalid JSON.
- Static transcript replay records for supported verdict re-derivation without
  model calls.
- `rederive.py` for transcript replay / re-derivation.
- `transcript_demo.py` for offline transcript normalization and re-derivation.
- Normalization-isolation invariant and verifier call-site guard.
- Targeted transcript replay tamper checks.

### Not Added

- No live adapters.
- No model API calls.
- No model fingerprinting.
- No policy-guided retry.
- No verifier history awareness.

## v0.5 - 2026-06-16

### Added

- External/manual JSON candidate adapter for locally produced candidate answers.
- Per-attempt provenance records with raw-source and normalized-candidate hashes.
- External candidate provenance boundary demo.

## v0.4 - 2026-06-15

### Added

- Minimal SFA-Agent proof of concept around the deterministic verifier.
- Deterministic fake adapter with one warning-guided retry.
- Append-only agent run records.

## v0.3 - 2026-06-15

### Added

- Deterministic tamper and contamination suite.
- Verifier invariant suite for history-blindness checks.

## v0.2 - 2026-06-15

Initial public release.

### Added

- Sealed Failure Artifacts v0.2 schema.
- Deterministic verifier with no network calls, no LLM calls, and no repair step.
- Hash-based artifact sealing for tamper evidence.
- Replay script for re-attesting artifacts and case integrity.
- Failure taxonomy with hierarchical failure families.
- Append-only occurrence ledger with hash-chained entries.
- Historical reporting for recurrence, growth, decline, extinction, and lineage.
- Migration helper for v0.1 artifacts.
- Synthetic history seeder for demonstration reports.

### Principles

- No hidden repair.
- No gold leakage.
- No rewritten history.
- Evidence -> verdict -> artifact -> ledger -> replay -> history.
