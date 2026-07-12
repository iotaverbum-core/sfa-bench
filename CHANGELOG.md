# Changelog

All notable changes to SFA-Bench will be documented in this file.

## 2.0.0-alpha.1 - 2026-07-12

### Added

- A single candidate-output validity gate before Frontier lane canonicalisation,
  with distinct `no_model_output`, `unparseable_model_output`, and
  `invalid_model_output` zero-credit outcomes.
- Deterministic, no-overwrite successor evidence tooling and a lineage-linked
  correction of the provisional Fable-5 candidate result.
- Provider-neutral campaign, candidate-manifest, execution-plan, benchmark-lock,
  and ratification-policy validators with inspectable JSON Schemas.
- Offline campaign and evidence CLIs, lock provenance checks, adversarial tests,
  and non-mutating release verification commands.
- Benchmark-lock bindings for declared system prompts and user/case-set
  references, including deterministic directory digests.

### Fixed

- Issue #20: empty, refusal-like, malformed, and non-object candidate responses
  can no longer receive synthetic credit from lane defaults.
- Missing structured fixture output remains `None` rather than becoming `{}`.
- Public lock APIs no longer accept caller-injected commit provenance.
- Nested ratification/promotion key variants and non-finite JSON numbers now fail
  closed with stable validation codes.
- Unpaired Unicode surrogates, recursive draft-completion claims, and
  noncanonical portable paths now fail before dispatch or serialization.
- Historical task-capture hashes must match exact bytes or a deterministic
  LF/CRLF-normalized equivalent.
- Every campaign lock binding and declared directory membership must match its
  declared Git commit. The release identifier is read from that commit's version
  source; deleted, ignored, untracked, or repository-control inputs fail closed.

### Governance

- The original Fable evidence remains byte-preserved and its `0.771` aggregate
  is explicitly provisional. The corrected `0.6875` successor is not ratified.
- No live provider campaign, GPT-5.6 result, provider ranking, alignment proof,
  legal conformity, automatic ratification, or automatic promotion is claimed.
- The frozen zone now protects the original Fable evidence and corrected
  successor through an explicit human-authorized amendment record.

## Unreleased — SFA-AutoLab v0

### Added (AutoLab Item 7 - End-to-end runner)

- **End-to-end AutoLab runner** (`autolab/runner.py`,
  `autolab_runner_demo.py`): a frozen orchestration policy that wires the
  existing AutoLab primitives into one sequence. The runner refuses to start
  while a halt is active, evaluates circuit breakers before invoking the builder,
  runs the controller-ordered declaration/holdout/attestation path, seals and
  gates the evaluator report, appends rejection events for red gates or failed
  human ratification, requires sealed human approval plus matching token before
  promotion, inscribes successful promotions into lineage, and evaluates
  breakers again after the iteration. The module is added to the frozen zone via
  amendment `fz-v0.7.0-add-runner`; no verifier, taxonomy, or version-of-record
  change. See [docs/autolab-runner.md](docs/autolab-runner.md) and
  [docs/checkpoints/autolab-item-7-runner.md](docs/checkpoints/autolab-item-7-runner.md).

### Added (AutoLab Item 6 - Circuit breakers)

- **Circuit-breaker halt-and-hold layer** (`autolab/circuit_breakers.py`,
  `circuit_breakers_demo.py`): a frozen safety policy that evaluates deterministic
  stop conditions around the AutoLab loop, appends `autolab_halted` only for a
  sealed halted breaker report, and requires a sealed human restart clearance
  plus a matching out-of-loop token before appending `autolab_restart_authorized`.
  Breakers cover frozen-zone mismatch, meta-ledger chain break, holdout budget
  exhaustion, consecutive rejections, proposed frozen-path changes, cost/time
  budget overrun, and re-proposal of a withered lineage. Caution/wither
  directives are advisory and excluded from gate inputs. The module is added to
  the frozen zone via amendment `fz-v0.6.0-add-circuit-breakers`; no verifier,
  taxonomy, or version-of-record change. See
  [docs/autolab-circuit-breakers.md](docs/autolab-circuit-breakers.md) and
  [docs/checkpoints/autolab-item-6-circuit-breakers.md](docs/checkpoints/autolab-item-6-circuit-breakers.md).

### Added (AutoLab Item 5 - Lineage + rollback)

- **Promotion lineage and rollback layer** (`autolab/lineage.py`,
  `lineage_demo.py`): a frozen promotion-history policy that turns an existing
  `human_ratification` meta-ledger event into an explicit `promotion_inscribed`
  event before the target becomes current, and that records rollback only as an
  append-only `rollback_inscribed` event. Rollback requires a sealed rollback
  record, a matching out-of-loop human rollback token, and a target ref that
  matches the currently derived lineage target. Rejected or tampered rollback
  attempts append nothing. The module is added to the frozen zone via amendment
  `fz-v0.5.0-add-lineage-rollback`; no verifier, taxonomy, or
  version-of-record change. See [docs/autolab-lineage.md](docs/autolab-lineage.md)
  and [docs/checkpoints/autolab-item-5-lineage-rollback.md](docs/checkpoints/autolab-item-5-lineage-rollback.md).

### Added (AutoLab Item 4 - Human ratification)

- **Human ratification promotion layer** (`autolab/ratification.py`,
  `ratification_demo.py`): a deterministic promotion policy that recomputes the
  pre-registration gate, requires it to be green, and then requires a sealed
  human approval record plus a matching out-of-loop token before appending a
  `human_ratification` event to the AutoLab meta-ledger. Gate-green alone does
  not promote; a red deterministic gate cannot be overridden by a human token;
  the ratification record binds the exact declaration hash, report hash, and
  gate-decision hash; tampering with the ratification record is detected by its
  seal. The builder cannot attest or talk its way through promotion because
  builder rationale and self-reported booleans remain outside the recomputed gate
  decision. The module is added to the frozen zone via amendment
  `fz-v0.4.0-add-ratification`; no verifier, taxonomy, or version-of-record
  change. See [docs/autolab-ratification.md](docs/autolab-ratification.md) and
  [docs/checkpoints/autolab-item-4-ratification.md](docs/checkpoints/autolab-item-4-ratification.md).
### Added (AutoLab Item 3 - Controller + budgeted holdout)

- **Frozen AutoLab controller** (`autolab/controller.py`,
  `autolab_controller_demo.py`): a deterministic controller that attests the
  frozen zone before an iteration, seals the pre-registration declaration into an
  append-only meta-ledger before invoking the builder callback, consumes declared
  holdout use against a bounded budget, records the builder result hash, and
  attests the frozen zone again after the builder returns. The meta-ledger is a
  JSONL hash chain (`seq`, `prev_hash`, `entry_hash`) so insertion, deletion,
  reordering, or edits are detected before another iteration can run. Holdout use
  must be explicitly bound in `eval_plan.holdout` (`budget_id`, suite, version,
  units); a suite that names holdout without a budget binding fails closed, and a
  second consumption beyond `max_uses` rejects before the builder runs. The
  controller is added to the frozen zone via amendment
  `fz-v0.3.0-add-controller`; no verifier, taxonomy, or version-of-record change.
  See [docs/autolab-controller.md](docs/autolab-controller.md) and
  [docs/checkpoints/autolab-item-3-controller.md](docs/checkpoints/autolab-item-3-controller.md).
### Added (AutoLab Item 2 — Pre-registration module)

- **Pre-registration declaration + asymmetric gate** (`autolab/preregistration.py`,
  `preregistration_demo.py`): a sealed declaration — target metric, direction,
  pre-registered threshold + significance rule, the exact evaluation plan, and
  protected-metric tolerances — committed *before* a patch is generated. A frozen
  evaluator later produces an improvement report from raw artifacts; the gate
  (`evaluate_gate`) compares the sealed report to the sealed declaration. The gate
  is **asymmetric** (it may only reject; no `promote` field exists — promotion
  still needs a human token), **builder-blind** (every pass/fail is recomputed
  from the report's raw numbers and the declared thresholds; the advisory
  `builder_rationale` and any self-reported booleans are ignored), and
  **deterministic** (canonical-hash-sealed declaration/report; pure function; no
  wall-clock/network/model). Checks: declaration-hash binding, eval-plan
  conformance, primary direction/threshold/decision-rule, and a **Pareto
  no-regression** check over protected metrics. Ships sealed fixtures
  (`examples/preregistration/`) — a passing report and a mismatch report that
  regresses protected metrics and is rejected — and 20 deterministic tests. The
  gate module is **gate policy**, so it is added to the frozen zone via the human
  amendment channel: manifest → `fz-v0.2.0` (13 frozen files), resealed, with an
  append-only amendment record `fz-v0.2.0-add-preregistration`. No verifier,
  taxonomy, or version-of-record change. See
  [docs/autolab-preregistration.md](docs/autolab-preregistration.md) and
  [docs/checkpoints/autolab-item-2-preregistration.md](docs/checkpoints/autolab-item-2-preregistration.md).

### Added (AutoLab Item 1 — Frozen-zone manifest + enforcement)

- **Frozen-zone manifest, attestation, and CI enforcement** (`autolab/frozen_zone.py`,
  `autolab/frozen_manifest.json`, `frozen_zone_check.py`): a path manifest of the
  parts that the AutoLab loop may never patch — verifier verdict logic
  (`sfa/verifier.py`, `sfa/categories.py`), gate policy (`release_gate.py`),
  ledger code (`sfa/ledger.py`, `sfa/hashing.py`), invariant suite
  (`invariant_suite.py`, `sfa/invariants.py`), the holdout pre-registration
  commitment, seed machinery (`seed_history.py`), and the enforcement itself. Two
  deterministic, offline mechanisms enforce it: (1) a git-free **zone-hash
  attestation** — the manifest seals a SHA-256 over the canonical content of every
  frozen file (the manifest's own digest excludes its self-referential
  `zone_hash`/`file_digests` keys to break circularity), so any content drift
  without a resealed manifest fails closed; and (2) a git-based **amendment gate**
  that rejects any change to files frozen as of the PR base — or to the manifest's
  zone definition — unless authorized by a human amendment token
  (`SFA_FROZEN_ZONE_AMENDMENT_TOKEN`, a protected CI input the builder cannot set)
  matching an append-only amendment record that binds one `prev_zone_hash ->
  new_zone_hash` transition. The zone protects itself (manifest, library, and CI
  command are all frozen). `seal` is idempotent human tooling refused under
  `--ci`. Genesis-safe: a base with no manifest passes. 18 deterministic tests
  (`tests/test_frozen_zone.py`) cover attestation determinism, the zone-touch
  failure, and the gate; the check is wired into `verify_all.py` and a dedicated CI
  step. No verifier, taxonomy, or version-of-record change. See
  [docs/autolab-frozen-zone.md](docs/autolab-frozen-zone.md) and
  [docs/checkpoints/autolab-item-1-frozen-zone.md](docs/checkpoints/autolab-item-1-frozen-zone.md).

## v1.1.0 — AGI-Axis Research Extension (2026-07-02)

The research core gains five frontier-capability layers, each preserving the five
hard invariants: the proposer is never the verifier (every accept/reject is a
deterministic function; no LLM output participates in a verdict), history is
append-only, sealed outputs replay byte-for-byte, gold never reaches the proposer
path, and CI stays offline. The `sfa/verifier.py` boundary is unchanged.

### Added (AGI-axis extension)

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

- **Causal-edge taxonomy (schema v2)** (`sfa/families.py`, `sfa/causal_report.py`,
  `causal_report.py`, `families.json`): a typed directed causal overlay `A → B` on
  top of the parent/child family tree, expressing "failure A tends to lead to
  failure B." `families.json` declares `taxonomy_schema_version`
  (`sfa.taxonomy_schema.v2`) and an `edges` list. The `Taxonomy` loader validates
  the overlay at load — known endpoints, no self-loops, no duplicates, and a
  **DAG** (cycles raise) — and exposes `edges()`, `causes()`, `effects()`, and
  `edge_type()`. Backward compatible: a v1 file (no `edges`) loads as an empty edge
  set, with an idempotent `migrate_to_v2` helper. A deterministic, sealed
  upstream/downstream **recurrence-linkage report** (`causal_report.py`) joins the
  overlay with ledger recurrence to show that a downstream family declines as its
  upstream cause is addressed, over the fixture
  `examples/causal/causal_ledger.jsonl`. See
  [docs/causal-edges.md](docs/causal-edges.md).

### Taxonomy

- Added two **additive** failure-family leaves, `deferred_consequence` and its
  child `deferred_consequence_stale`, to `families.json` for the deferred-
  consequence family's fingerprint support. The change is backward compatible: the
  family-set is a superset of the prior one, and `classify_family` refines a
  contradiction to `deferred_consequence_stale` only when scoring evidence is
  marked `task_family == "deferred_consequence"`. Evidence without that marker
  classifies exactly as before, so existing artifacts, the ledger, and the
  fingerprint demo re-derive byte-for-byte unchanged.
- Upgraded the taxonomy file to **schema v2** (`taxonomy_schema_version`), adding a
  backward-compatible typed causal-edge overlay with DAG validation and migration.
  The family-set version (`taxonomy_version`) is unchanged and edges never affect
  classification, so the fingerprint demo re-derives byte-for-byte unchanged.

### Changed

- Version of record bumped to `1.1.0`: `sfa.__version__`, the release gate's
  `EXPECTED_RELEASE`, every command header, the README, and `CITATION.cff` now
  declare `v1.1.0`.

### Not Changed

- No verifier behaviour or `sfa/verifier.py` change; no `sfa/categories.py`
  change. No LLM output participates in any verdict.
- No API, model, provider, or network calls in CI.
- The GroundLedger product layer (`product/`) is unaffected and independently
  versioned; it is not part of this research-instrument release line or its DOI.

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
