# SFA-Bench v2.0.0-alpha.1 Decision Log

This log records inspectable engineering decisions for the candidate-integrity
and campaign-foundation tranche. It records evidence and boundaries, not private
reasoning. A decision remains subject to rejection by tests or independent review.

## ADR-V2-001: Audit Before Implementation

- Problem: issue #20 crosses extraction, canonicalisation, scoring, historical
  evidence, and protected release surfaces.
- Alternatives: patch the first scoring symptom; trace one lane; trace the full
  response-to-verdict and release path first.
- Selected option: complete and accept a read-only repository audit before edits.
- Evidence: baseline commit `f09b02f7bd61f8ae8b7cb3e329752819d6c4e923`;
  full offline verification passed 24/24 outside the Windows temp ACL sandbox;
  the release gate passed.
- Affected trust boundary: all candidate and release boundaries.
- Compatibility impact: none.
- Rollback or rejection condition: repository state differs from the audited base.

## ADR-V2-002: Preserve the Baseline Environment Failure

- Problem: the sandbox denied Python 3.14 temporary-directory writes at command
  8/24, which could be confused with a repository failure.
- Alternatives: report a failed baseline; ignore the result; preserve it and
  reproduce the same command outside the filesystem sandbox.
- Selected option: retain both results and accept the unsandboxed offline pass as
  the repository baseline.
- Evidence: sandbox run failed with `PermissionError`; the same command passed
  all 24 commands with no provider or network access outside the sandbox.
- Affected trust boundary: verification evidence.
- Compatibility impact: none.
- Rollback or rejection condition: a later failure reproduces outside the sandbox.

## ADR-V2-003: One Invalid-Output Gate

- Problem: invalid responses become `{}` and reach lane canonicalisers, where
  generated defaults can receive credit.
- Alternatives: add guards to every lane; add one gate before dispatch; allow
  scoring and zero results afterward.
- Selected option: add one typed validity boundary before canonicaliser lookup.
- Evidence: empty `memory_boundary_001` scored `0.666667` on the audited baseline;
  issue #20
  identifies the same path.
- Affected trust boundary: raw candidate response to canonical output.
- Compatibility impact: invalid responses become explicit zero-score failures;
  valid JSON objects retain the existing canonicaliser and scorer path.
- Rollback or rejection condition: any invalid response invokes a canonicaliser
  or scorer, or any valid fixture changes score or result hash.

## ADR-V2-004: Separate Campaign Protocol Module

- Problem: V2 campaigns need deterministic preregistration and locking without
  turning frozen AutoLab policy into provider execution machinery.
- Alternatives: extend frozen AutoLab modules; encode campaign logic in docs;
  add a separate provider-neutral protocol package.
- Selected option: add a separate `sfa_bench.campaigns` package and offline CLI.
- Evidence: AutoLab preregistration, ratification, and lineage modules are frozen;
  existing canonical JSON conventions can be reused without changing them.
- Affected trust boundary: campaign metadata to benchmark execution evidence.
- Compatibility impact: additive; V1 and AutoLab behavior remain unchanged.
- Rollback or rejection condition: campaign code requires provider access, changes
  frozen policy, or permits metadata to affect a verdict.

## ADR-V2-005: Lineage-Linked Evidence Successor

- Problem: the historical Fable-5 score is provisional, but its raw evidence is
  sufficient for deterministic correction.
- Alternatives: overwrite the artifact; document only; build a new successor.
- Selected option: preserve every predecessor byte and generate a new,
  canonically hashed and sealed successor through an offline no-overwrite command.
- Evidence: the raw JSONL has eight records and SHA-256
  `2b46cd926bddf7bc8dd04c6b8039dd69bd18d9febb5d350c73acd4309d833998`.
- Affected trust boundary: historical evidence and research claims.
- Compatibility impact: append-only evidence lineage.
- Rollback or rejection condition: predecessor hashes change, raw output is
  reconstructed, or successor generation requires a provider call.

## ADR-V2-006: Release Bump as a Frozen Amendment

- Problem: public `v2.0.0-alpha.1` and PEP 440 `2.0.0a1` cannot agree under the
  current frozen release parsers.
- Alternatives: leave the tranche labelled v1.1.0; use a non-PEP-440 package
  version; make a final frozen-zone amendment after feature acceptance.
- Selected option: keep `1.1.0` through the accepted core implementation commit,
  then perform a distinct release-preparation amendment before final integrated
  red-team and reproducibility review.
- Evidence: `release_gate.py`, `sfa/invariants.py`, and command header parsing are
  frozen and currently accept only stable `vN.N.N` labels.
- Affected trust boundary: release gate and version of record.
- Compatibility impact: alpha-aware parsing is additive; the verifier, taxonomy,
  and historical release records remain unchanged.
- Rollback or rejection condition: amendment attestation fails, version surfaces
  disagree, or the change weakens an existing release check.

## ADR-V2-007: Preserve Missing Structured Output as None

- Problem: the Frontier fixture loader turns a missing `output` field into `{}`.
- Alternatives: leave it as a fixture convention; reject the row; preserve it as
  `None` for the scorer's existing explicit no-output result.
- Selected option: preserve missing output as `None`.
- Evidence: `score_task(task, None)` already returns deterministic zero-score
  `no_model_output`; `{}` can satisfy vacuous checks.
- Affected trust boundary: structured candidate fixture to frozen scorer.
- Compatibility impact: valid fixture outputs are unchanged.
- Rollback or rejection condition: existing valid fixture reports or hashes change.

## ADR-V2-008: Prove Lock Commit and Release Provenance

- Problem: copying campaign-declared commit and release strings into a lock can
  attribute uncommitted worktree bytes to an unrelated revision.
- Alternatives: treat declarations as trusted; record dirty state; resolve the
  commit and prove every bound file matches it before lock creation.
- Selected option: resolve the full Git commit, compare every bound blob and
  declared directory membership against it, and derive the public release from
  the version source at that commit.
- Evidence: independent review reproduced a valid lock with a false all-zero
  commit before remediation; the accepted release implementation anchor is
  `9744d547e80cc0ad8ad72e598ea9ca19e4458b51`.
- Affected trust boundary: pre-registration to benchmark lock.
- Compatibility impact: public lock creation now requires Git provenance and a
  matching package release. Pure tests use explicitly private content helpers;
  no public API accepts an injected provenance context.
- Rollback or rejection condition: a false commit, dirty bound file, or mismatched
  release can produce a valid CLI lock.

## ADR-V2-009: Reconcile Duplicate Campaign Policies

- Problem: root retry, exclusion, and halt policy could disagree with the
  execution-plan copies.
- Alternatives: remove one representation; choose one implicitly; require exact
  equality and seal both.
- Selected option: require exact equality and emit `POLICY_SURFACE_MISMATCH`.
- Evidence: independent review reproduced a campaign with contradictory retry
  counts and no validation issue before remediation.
- Affected trust boundary: pre-observation policy to execution.
- Compatibility impact: ambiguous declarations now fail closed.
- Rollback or rejection condition: contradictory policy surfaces validate.

## ADR-V2-010: Restrict Unhashed Lock Envelopes

- Problem: an excluded envelope could carry unsealed outcome or ratification claims.
- Alternatives: hash timestamps; permit arbitrary metadata; allow only narrow
  provenance strings and reject outcome language.
- Selected option: allow only a timezone-qualified ISO `created_at`. Reject
  every other envelope field, including free-form provenance text.
- Evidence: adversarial tests cover outcome, provider, regulatory, legal, and
  credential text while proving creation-time changes do not affect the
  deterministic lock digest.
- Affected trust boundary: nondeterministic metadata to deterministic evidence.
- Compatibility impact: creation-time provenance remains possible without an
  unhashed free-text claim channel.
- Rollback or rejection condition: excluded metadata can assert an outcome.

## ADR-V2-011: Bind Prompt References as Lock Inputs

- Problem: declared prompt hashes could be fabricated while referenced prompt
  files or directories remained outside lock bindings.
- Alternatives: trust declared hashes; bind campaign text only; bind and verify
  the referenced repository content.
- Selected option: bind system and user/case-set references as separate groups.
  A file uses its byte SHA-256; a directory uses the canonical sorted binding-set
  digest.
- Evidence: independent review built an official lock with false prompt hashes
  before remediation; false hashes and post-lock prompt mutation now fail tests.
- Affected trust boundary: pre-registered prompts to observed candidate output.
- Compatibility impact: lockable campaigns require resolved prompt references.
- Rollback or rejection condition: false prompt hashes or prompt mutations pass.

## ADR-V2-012: Reject Ambiguous Governance and JSON Values

- Problem: nested spelling variants could assert promotion or ratification, and
  Python-specific `NaN` or infinity values could enter otherwise machine-readable
  documents.
- Alternatives: inspect only named policy fields; normalize recursively; accept
  permissive Python JSON.
- Selected option: normalize case and separators for governance-control keys,
  scan arbitrary configuration recursively, reject non-finite numbers, and parse
  CLI JSON with non-standard constants disabled.
- Evidence: adversarial variants and non-finite documents are covered by stable
  error-code tests.
- Affected trust boundary: untrusted campaign/manifest input to governance state.
- Compatibility impact: non-standard or ambiguous documents now fail closed.
- Rollback or rejection condition: a nested automatic-promotion claim or
  non-finite number validates.

## ADR-V2-013: Strict Scalar and Path Boundaries

- Problem: permissive JSON constants, unpaired Unicode surrogates, ambiguous
  governance text, and noncanonical portable paths could cross validation
  boundaries or crash later canonical serialization.
- Alternatives: catch serialization failures late; constrain only named fields;
  validate every untrusted value before hashing or dispatch.
- Selected option: reject non-finite numbers and unpaired surrogates recursively,
  scan arbitrary configuration/metadata text for governance and draft-completion
  claims, and reject empty/dot, colon, trailing-dot, and reserved path segments.
- Evidence: all-lane no-dispatch tests, CLI malformed-input tests, governance
  value probes, and Windows path-form probes pass.
- Affected trust boundary: untrusted candidate/campaign input to canonical
  evidence and governance state.
- Compatibility impact: non-standard JSON, ambiguous claims, and nonportable
  paths now fail closed.
- Rollback or rejection condition: malformed scalar input reaches a canonicaliser
  or lock serializer, or a nested claim/path bypass validates.

## ADR-V2-014: Prove Captured Task Digest Lineage

- Problem: historical task hashes differ from current bytes because the capture
  used CRLF while this checkout uses LF; merely recording both hashes does not
  prove their relationship.
- Alternatives: ignore the captured hash; require exact bytes only; accept only
  exact or deterministically normalized LF/CRLF equivalents.
- Selected option: record `exact_bytes`, `lf_normalized_equivalent`, or
  `crlf_normalized_equivalent` and reject every unrelated capture digest.
- Evidence: all eight preserved Fable task hashes resolve to
  `crlf_normalized_equivalent`; an unrelated digest fails generation.
- Affected trust boundary: historical capture evidence to corrected successor.
- Compatibility impact: line-ending-only transport differences remain
  reproducible without accepting arbitrary task drift.
- Rollback or rejection condition: an unrelated captured task hash is accepted.

## ADR-V2-015: Verify Every Lock Binding Against Git

- Problem: worktree-only provenance checks can misattribute ignored or untracked
  bytes, including repository-control files, to a declared commit.
- Alternatives: infer cleanliness from `git diff`; reject only control paths;
  compare every bound file directly with the declared commit blob.
- Selected option: reject repository-control paths; require an exact SHA-256
  match between each worktree binding and `git show <commit>:<path>`; compare
  declared directory membership with the commit tree; and derive the release
  identifier from the version source at the declared benchmark commit.
- Evidence: the campaign protocol suite covers absent commit blobs, changed and
  deleted tracked files across every binding group, dirty version-source bytes,
  ignored-file attribution, and repository-control paths.
- Affected trust boundary: mutable campaign inputs to deterministic benchmark
  lock provenance.
- Compatibility impact: every lock input and lock-eligible directory member must
  exist byte-for-byte at its declared Git commit; uncommitted inputs and version
  labels cannot be represented as committed evidence.
- Rollback or rejection condition: a missing or byte-different commit binding
  verifies successfully.

## ADR-V2-016: Freeze LF Checkout Semantics

- Problem: a normal Windows clone with `core.autocrlf=true` rewrites hash-bound
  JSON and JSONL bytes, so preserved evidence fails its exact digest check.
- Alternatives: require reviewers to configure Git manually; hash normalized
  text instead of preserved bytes; enforce repository checkout semantics.
- Selected option: add and freeze `.gitattributes` with `text=auto eol=lf`.
- Evidence: the original Windows clone reproduced the failure, while a clone
  using LF checkout reproduced the candidate and campaign seals.
- Affected trust boundary: Git object bytes to cross-platform checked-out
  evidence and benchmark inputs.
- Compatibility impact: normal checkouts that honor repository attributes use
  LF for detected text files; binary files remain subject to Git's `text=auto`
  classification.
- Rollback or rejection condition: a normal Windows clone changes a protected
  evidence digest or fails the offline integrity checks.

## ADR-V2-017: Classify Semantic Draft And Governance Assertions

- Problem: exact normalized-key lists missed obvious variants such as
  `run_finished`, `final_score`, and `human_approved`.
- Alternatives: add each observed spelling; whitelist actor/domain prefixes;
  classify semantic markers at key endings or followed by event and
  `by<actor>` suffixes.
- Selected option: use prefix-agnostic semantic marker detection for completion,
  execution, result, approval, acceptance, certification, and endorsement
  assertions, with explicit policy-boundary exceptions and planning
  counterexamples such as `execution_timeout`, `ranking_policy`,
  `result_schema`, and `score_threshold`.
- Evidence: campaign and candidate-manifest matrices cover the reported variants
  plus planning-field counterexamples.
- Affected trust boundary: untrusted campaign and provider metadata to declared
  execution and human-governance state.
- Compatibility impact: semantic self-approval and completed-run assertions now
  fail closed even when separators or prefixes differ.
- Rollback or rejection condition: a draft accepts an execution, result, or
  governance assertion, or a documented planning counterexample is rejected.

## ADR-V2-018: Preserve Embedded Objects After Leading Scalars

- Problem: an incidental leading JSON scalar in surrounding prose caused an
  early non-object verdict and suppressed a later top-level object.
- Alternatives: reject every leading JSON value; scan through all values; scan
  past scalars while retaining the container boundary.
- Selected option: continue the existing top-level object scan after leading
  strings, numbers, booleans, or null, while rejecting leading arrays so nested
  objects cannot escape their container.
- Evidence: scalar-prefix and leading-array regression tests pass.
- Affected trust boundary: raw candidate response to the single validity gate.
- Compatibility impact: valid embedded-object responses retain the documented
  extraction contract without weakening non-object-container rejection.
- Rollback or rejection condition: a leading scalar suppresses a later top-level
  object, or an array exposes a nested object to canonicalisation.
