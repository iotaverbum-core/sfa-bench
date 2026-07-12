# Alpha.2 Campaign Capture Threat Model

## Assets and trust boundaries

Protected assets are the benchmark lock, lock-bound code and prompts/cases,
authorization artifact, exact adapter-boundary bytes, lifecycle chain, capture
manifest, fixed verifier result, and unratified review bundle. The adapter,
provider labels, request identifiers, transport metadata, operator declarations,
timestamps, and raw candidate content are untrusted evidence inputs.

## Threats and controls

| Threat | Control | Residual limit |
|---|---|---|
| Lock substitution or dirty bound file | Full Git commit/blob and directory-membership verification immediately before dispatch and judgment | Relies on local Git object integrity |
| Altered capture/judgment code | Required alpha.2 package, CLI/check, and schemas must appear in lock bindings | Does not authenticate the Git hosting account |
| Prompt or case drift | Exact prompt/case references and digests in authorization and lock | Does not prove semantic equivalence |
| Duplicate execution/attempt | Exclusive directories and no-overwrite records | Denial-of-service remains possible |
| Concurrent ledger writers | Exclusive sequence file publication and chained verification | Filesystem durability depends on platform guarantees |
| Crash or partial write | Fsync staging, partial blobs, explicit interruption/recovery/abort, no file-presence success inference | Sudden hardware failure may exceed OS durability promises |
| Response or manifest tamper | Raw byte, attempt, manifest, ledger-root, judgment, and bundle seals | SHA-256 is not a digital signature |
| Secret leakage | Metadata allowlist, credential-pattern rejection, private raw blobs, hash-only public bundle | Pattern scanning cannot prove absence of every possible secret |
| Fabricated provider provenance | Provider/model/request ID fields labelled declared and unverified | No provider-signed receipt is implemented |
| Metadata changes verdict | Empty metadata projection in judgment and existing fixed candidate path | Fixed verifier limitations remain |
| Retry drift | Authorization must exactly match preregistered retry policy and attempt budget | Operator-declared retry reason is not independently authenticated |
| Automatic authority claim | No ratify/promote/publish/release CLI; schemas require unratified/false authority fields | Privileged humans retain repository control |
| Path traversal/symlink escape | Portable path validation plus reparse-ancestor rejection | Filesystem attacks by privileged host administrators are out of scope |

## Required rejection evidence

The focused suite and existing alpha.1 suites cover authorization/lock mismatch,
false request bytes, retry drift, automatic governance fields, duplicate IDs,
attempt conflict, raw/manifest/review tamper, missing/partial evidence,
interruption, credential and misleading metadata, invalid JSON/Unicode/path
forms, concurrent writers, and explicit zero credit for invalid candidate output.

Existing alpha.1 campaign tests additionally cover false or unresolved commits,
commits with different bound bytes, dirty bound files, prompt/case mutation,
fabricated aggregate digests, release mismatch, repository-control paths,
directory membership drift, non-finite JSON, and Windows path forms. Existing
candidate tests pin valid-output scores, verdicts, and protected result hashes.

## Forbidden operations

Canonical verification must remain offline. Neither the core nor its CLI may
open a network connection, import a live provider SDK, read a provider
credential, execute a provider campaign, create a Git commit/tag/merge/push,
invoke GitHub publication, ratify evidence, or claim regulatory status.
