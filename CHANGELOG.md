# Changelog

All notable changes to SFA-Bench will be documented in this file.

## Unreleased

No unreleased changes.

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
