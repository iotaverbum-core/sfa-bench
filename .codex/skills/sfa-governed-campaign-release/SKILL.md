---
name: sfa-governed-campaign-release
description: Audit, implement, verify, and prepare governed SFA-Bench campaign-execution releases with frozen-zone, benchmark-lock, exact-evidence, human-authority, offline-CI, adversarial-review, and claims boundaries. Use for SFA-Bench release tranches that add or change preregistration, campaign lifecycle, provider adapters, evidence capture, provenance, judgment, review bundles, release gates, version surfaces, or associated tests and documentation.
---

# SFA Governed Campaign Release

## Establish authority and scope

Treat the task brief as implementation scope, not as authority to execute a live
provider campaign, use credentials, amend a protected path, ratify evidence,
merge, tag, push, publish, or release unless the human explicitly supplies the
separate authority required for that action.

Stop before:

- any live provider or network call;
- any credential or secret request;
- a protected frozen-zone amendment without the matching human token;
- an irreversible Git or GitHub action;
- automatic ratification, promotion, publication, or release.

Never install a third-party skill or plugin without explicit approval.

## Audit before editing

1. Confirm the current branch, clean status, exact HEAD, local and remote main,
   immutable release-tag target, merge base, package version, public version, and
   command-header surfaces.
2. Read every applicable AGENTS.md, frozen manifest/rule, claim boundary,
   decision log, campaign schema, release gate, verifier invariant, provenance
   path, and lineage path.
3. Run the documented offline baseline exactly. On Windows, preserve a sandbox
   temp/ACL failure and rerun the identical command with normal filesystem access
   before classifying it as a repository failure.
4. Run read-only parallel audits for:
   - repository and trust boundaries;
   - campaign protocol and artifact architecture;
   - raw evidence and provenance;
   - adversarial/security risks;
   - tests, CI, packaging, clean clones, and versions;
   - scientific and authority claims.
5. Wait for the audits and consolidate conflicts before editing.

Use the narrowest additive path. Treat every path in
autolab/frozen_manifest.json as protected. Also inspect campaign lock directory
bindings: adding a new member beneath a bound directory changes its membership
and may break predecessor lock reproduction.

## Select an implementation surface

Prefer a versioned additive sibling when predecessor files or directories are
lock-bound. Do not change the frozen verifier or existing valid-output judgment
behavior.

Require an executing campaign lock to bind:

- the capture and judgment implementation;
- schemas;
- adapter and normalizer;
- prompt and case references;
- benchmark and verifier commits;
- release identifier; and
- declared commands.

Use isolated worktrees only when the environment can create and control them.
Otherwise use one dedicated codex/ branch with sequential, reviewable commits.
Never let multiple agents edit overlapping files.

## Preserve evidence

Preserve the exact bytes observed at the declared adapter capture boundary.
Hash raw bytes directly. Do not parse, normalize, decode, redact, or embed them in
canonical JSON before calculating their byte identity.

Keep separate:

1. private raw request and response-body bytes;
2. allowlisted transport metadata;
3. redacted operational diagnostics labelled derived_redaction;
4. derived canonical candidate content;
5. deterministic judgment.

Do not describe adapter-boundary bytes as authenticated provider wire bytes.
Label provider/model/request identifiers provider_declared_unverified unless a
separately reviewed signed-provider mechanism exists.

Use exclusive execution and attempt IDs, fsynced staging, atomic no-overwrite
publication, immutable event files, chained hashes, explicit partial/interrupted
records, and successor lineage. Never infer completion from file presence.

## Preserve human authority

Require a separately supplied execution-only authorization artifact bound to the
campaign, lock, execution ID, request bytes, adapter, retry scope, commits, and
release.

Make lifecycle transitions explicit and fail closed. Include interruption and
abort paths. End execution at sealed captured evidence.

Perform judgment in a separate offline operation only after re-verifying the
lock, implementation, raw blobs, lifecycle, manifest, task binding, and verifier
commit. Keep provider, adapter, retry, and authorization metadata out of
judgment.

Build a separate secret-free review bundle with:

- raw evidence hashes, not raw bodies;
- integrity report and deterministic judgment;
- warnings and lineage references;
- ratification_status: unratified;
- packaging_is_approval: false.

Expose no ratify, promote, merge, tag, push, publish, or release command.

## Test and verify

Use deterministic synthetic adapters for every canonical test. Cover at least:

- valid object, empty, refusal-like, malformed, non-object, non-finite, binary,
  timeout, transport error, retry, duplicate provider ID, partial stream,
  interruption, misleading metadata, and credential-like metadata;
- altered lock/prompt/case/bound bytes/commit/release/verifier;
- duplicate execution/attempt and concurrent writer collisions;
- partial or missing evidence and recovery without invented completion;
- raw/manifest/ledger/judgment/bundle tamper;
- secret leakage and metadata authority claims;
- traversal, repository-control, Windows-reserved, Unicode, duplicate-key,
  noncanonical JSON, symlink/junction/reparse, and line-ending cases;
- unchanged predecessor valid-output canonical forms, scores, verdicts, and
  protected hashes.

Run the repository's exact Windows commands where supplied. The usual spine is:

    py -3 -m unittest discover -s tests -t . -p "test_*.py"
    py -3 campaign_capture_check.py
    py -3 verify_all.py
    py -3 release_gate.py --ci
    py -3 frozen_zone_check.py --ci --base origin/main
    git diff --check
    git diff --name-only origin/main...HEAD
    git status --short --untracked-files=all

Keep CI offline and credential-free. Reproduce from committed HEAD in clean
full-history LF and Windows core.autocrlf=true clones. Verify independent product
packaging without changing unrelated product versions.

## Obtain independent acceptance evidence

After implementation, assign separate reviewers for:

- security, provenance, secrets, path safety, atomicity, concurrency;
- verifier isolation, candidate integrity, predecessor compatibility;
- lifecycle, human authority, forbidden transitions;
- tests, CI, packaging, Windows/Linux clean clones;
- claims, scientific limits, and release wording.

Wait for every reviewer. Remediate supported findings and rerun the complete
suite. Do not let the implementation agent mark its own work accepted.

## Prepare, do not perform, release actions

Keep the implementation at the prior public/package version until all checks and
reviews pass. If a version bump touches frozen release surfaces, stop at the
human amendment boundary. Only after the matching token and amendment record are
available, align every version surface in one distinct release-preparation
change.

Do not create a tag, GitHub Release, merge, or live campaign.

## Report exact evidence

Report:

- completed, partial, or blocked outcome;
- base, branch, final HEAD, merge base, commits, and clean/dirty status;
- architecture and every trust boundary;
- exact commands, pass/fail counts, seals, clean-clone and reproducibility result;
- predecessor compatibility and successor formats;
- supported and explicitly unsupported claims;
- independent findings, severity, disposition, and evidence;
- remaining human actions;
- proposed PR title/body, issue text, and release-note draft;
- exact inspect, verify, push, PR, and check commands without executing
  human-only commands.

Never smooth over an interrupted or unrun check.