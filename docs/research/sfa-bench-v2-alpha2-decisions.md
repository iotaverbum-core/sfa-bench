# SFA-Bench v2.0.0-alpha.2 Campaign Capture Decision Log

Status: accepted implementation design; implementation version remains
`v2.0.0-alpha.1` until the separate release-preparation amendment.

This log records inspectable decisions and evidence. It does not record private
reasoning or grant authority to software, adapters, captured outputs, or models.

## Baseline evidence

- Audited base, local `main`, `origin/main`, and immutable tag
  `v2.0.0-alpha.1` all resolve to
  `7e3e03146bd42a70dbd7c647a4f7fa2ebcbae6d8`.
- The untouched base passed the 26-command offline suite. A first sandboxed
  attempt failed at command 10 because Windows denied a temporary-directory
  write and cleanup; the identical `py -3 verify_all.py` command passed 26/26
  with normal filesystem access.
- `py -3 release_gate.py --ci` passed on the untouched base.
- `py -3 frozen_zone_check.py --ci --base origin/main` passed with manifest
  `fz-v0.8.0` and zone hash
  `706fefaed9ff7a066ca4ee41f9073e1424e04dd9b130bc43c3db30c53217db36`.
- Six independent read-only audits covered trust boundaries, campaign
  architecture, evidence/provenance, security, CI/packaging, and claims.

## ADR-A2-001: Use additive successor surfaces

- Problem: the published alpha.1 lock binds `campaign_cli.py`, the entire
  `campaigns/schemas/` directory, and the existing `sfa_bench/campaigns`
  implementation files. Adding or editing those surfaces would break alpha.1
  lock reproduction.
- Alternatives: extend the alpha.1 files; amend alpha.1; add versioned siblings.
- Selected option: add `campaign_capture_cli.py`,
  `sfa_bench/campaigns/capture/`, and `campaigns/alpha2/`. Do not edit the
  alpha.1 campaign CLI, schemas, protocol, locking module, or package initializer.
- Evidence: the alpha.1 preregistration binds those files and directory
  membership; lock verification compares every bound byte and declared tree
  member with Git.
- Affected trust boundary: published benchmark lock to alpha.2 execution.
- Compatibility impact: alpha.1 lock bytes and semantics remain unchanged.
- Rollback or rejection condition: an alpha.1 lock or valid-output regression
  changes because alpha.2 files were added.

## ADR-A2-002: Derive lifecycle state from immutable events

- Problem: mutable status files can skip transitions, contradict prior state,
  or imply success after interruption.
- Alternatives: one mutable state file; append JSONL; immutable event files.
- Selected option: store one canonical, hash-chained event per exclusive,
  sequence-numbered file. Derive current state by verifying the entire chain.
  Legal primary transitions are `draft -> validated -> locked ->
  execution_authorized -> capturing -> captured -> sealed -> judged ->
  review_required`. Explicit `interrupted` and `aborted` branches preserve
  incomplete outcomes without inventing completion.
- Evidence: the existing JSONL ledgers are protected and do not provide the
  required crash/concurrency publication guarantees.
- Affected trust boundary: runtime occurrence evidence to campaign state.
- Compatibility impact: additive successor ledger only.
- Rollback or rejection condition: a missing, extra, reordered, repeated,
  contradictory, or hash-invalid event can produce a successful state.

## ADR-A2-003: Treat authorization as execution-only declared evidence

- Problem: execution permission must be separate from preregistration and must
  never be confused with ratification or verified real-world identity.
- Alternatives: CLI flag; adapter-supplied token; separate sealed artifact.
- Selected option: require a separately supplied, digest-sealed authorization
  artifact bound to campaign ID, lock digest, execution ID, request digest,
  adapter identity/version, retry scope, and declared operator identity. The
  artifact permits execution/capture only.
- Evidence: alpha.1 already excludes automatic ratification and promotion and
  keeps provider metadata outside judgment.
- Affected trust boundary: human/operator declaration to adapter dispatch.
- Compatibility impact: none to alpha.1 ratification or lineage.
- Rollback or rejection condition: capture can mint its own authorization,
  reuse one outside scope, or claim ratification/approval.

The software verifies artifact consistency. It does not establish that the
submitter is human, legally authorized, entitled, or approved by a provider.

## ADR-A2-004: Preserve adapter-boundary bytes as content-addressed blobs

- Problem: canonical JSON hashing loses original whitespace, encoding, binary
  content, and other byte distinctions.
- Alternatives: parsed JSON only; base64 in summaries; exact `.bin` blobs plus
  descriptors.
- Selected option: preserve the exact request and response-body bytes observed
  at the declared adapter capture boundary in immutable content-addressed blob
  files. Hash the bytes directly with SHA-256. Canonical summaries reference but
  never replace the raw blobs.
- Evidence: existing canonical hashes prove object identity, not original byte
  identity; the historical PowerShell harness coerces provider content to text.
- Affected trust boundary: adapter delivery to preserved evidence.
- Compatibility impact: additive binary-capable artifact format.
- Rollback or rejection condition: non-UTF-8 bytes cannot round-trip exactly,
  or a derived/redacted value is described as original evidence.

"Exact" means exact bytes delivered to this capture boundary. It does not prove
provider-side origin, upstream wire fidelity, absence of SDK/proxy transforms,
model identity, or hidden reasoning.

## ADR-A2-005: Separate private raw evidence and public review material

- Problem: transport metadata and raw bodies may contain credentials or other
  sensitive material, while public review must remain secret-free.
- Alternatives: overwrite with redactions; publish everything; separate zones.
- Selected option: keep raw request/response blobs immutable and private to the
  capture store. Public manifests and review bundles contain allowlisted
  metadata, digests, byte lengths, provenance classes, redacted diagnostics,
  derived candidate content, warnings, and deterministic judgments. A redaction
  is always labelled `derived_redaction` and never replaces raw evidence.
- Evidence: current secret scanning is useful but intentionally pattern-limited.
- Affected trust boundary: private operational evidence to public human review.
- Compatibility impact: none.
- Rollback or rejection condition: authorization headers, cookies, API keys, or
  credential-like metadata enter a public artifact.

## ADR-A2-006: Keep the adapter transport-only and synthetic in canonical tests

- Problem: provider code or metadata must not enter deterministic judgment, and
  canonical verification must remain offline.
- Alternatives: provider SDK in core; callback with arbitrary objects; narrow
  byte transport protocol with a deterministic laboratory.
- Selected option: define a provider-neutral protocol that accepts a validated,
  lock-bound request and returns bytes plus allowlisted observations. Ship only
  a deterministic synthetic adapter for canonical tests. Do not import a live
  provider SDK or accept credentials in the trusted offline core.
- Evidence: alpha.1 projects provider/retry/adapter metadata to an empty
  judgment input.
- Affected trust boundary: untrusted transport to trusted capture.
- Compatibility impact: existing scorer and verifier remain unchanged.
- Rollback or rejection condition: adapter metadata, labels, retry fields, or
  provider identifiers can change a verdict.

## ADR-A2-007: Verify provenance immediately before dispatch and judgment

- Problem: a valid lock can be substituted, bound files can drift, or altered
  capture code can replay evidence under a different commit.
- Alternatives: trust stored strings; verify only at initialization; verify at
  every critical boundary.
- Selected option: verify campaign and benchmark lock before dispatch, require
  the alpha.2 capture package and schemas in lock bindings, and verify the sealed
  capture, lock, raw digests, lifecycle root, implementation binding, and
  verifier commit again before judgment.
- Evidence: alpha.1 lock code already resolves commits/releases and compares
  every binding byte and directory member with Git.
- Affected trust boundary: mutable checkout and stored evidence to execution and
  judgment.
- Compatibility impact: alpha.2 campaigns must bind their successor machinery.
- Rollback or rejection condition: a false commit, dirty bound file, lock
  substitution, or different verifier commit can dispatch or judge.

## ADR-A2-008: Make judgment and review separate sealed operations

- Problem: capture must not judge itself, and packaging must not imply approval.
- Alternatives: score during transport; score during sealing; separate offline
  judgment and review operations.
- Selected option: execution ends at sealed capture evidence. A separate offline
  command verifies integrity, derives candidate validity, and invokes the
  existing fixed candidate judgment path. Another deterministic command creates
  a secret-free review bundle with `ratification_status: unratified` and moves
  lifecycle state to `review_required`.
- Evidence: alpha.1 preserves explicit zero credit for missing, refusal-like,
  malformed, non-object, and non-finite outputs and forbids automatic promotion.
- Affected trust boundary: evidence preservation to deterministic judgment and
  human authority.
- Compatibility impact: existing valid-output scoring path is reused unchanged.
- Rollback or rejection condition: capture mutates raw evidence, packaging
  changes a verdict, or any operation claims ratification/promotion/release.

## ADR-A2-009: Keep implementation at alpha.1 until human amendment

- Problem: the public alpha.2 version bump requires changing frozen
  `release_gate.py` and version-consistency surfaces.
- Alternatives: bypass the gate; mix version changes into implementation;
  perform a distinct authorized amendment.
- Selected option: retain public `v2.0.0-alpha.1` and package `2.0.0a1` during
  implementation and review. Stop release preparation at the human amendment
  boundary, then align every version surface in one distinct change only after
  acceptance and a matching amendment token/record.
- Evidence: frozen-zone and version-consistency checks bind the release gate,
  package version, and command headers.
- Affected trust boundary: accepted implementation to public release identity.
- Compatibility impact: no premature public-version claim.
- Rollback or rejection condition: implementation claims alpha.2 release status
  before the human-authorized frozen amendment.

## Claims boundary

If supported by final tests, alpha.2 may claim deterministic synthetic lifecycle,
capture-boundary byte preservation, internal digest/provenance consistency,
tamper detection for covered cases, offline judgment reproducibility, and
secret-free unratified review packaging.

It does not support claims of a live provider run, provider/model identity,
provider rankings, comparative quality, population-level behaviour, alignment,
independent replication, semantic completeness, legal or regulatory conformity,
provider approval, verified human identity, autonomous authority, automatic
ratification, automatic promotion, merge, tag, or release publication.
