# Alpha.2 Capture Artifact Specification

## Storage layout

```text
out/campaign_runs/<campaign_id>/<execution_id>/
  run.json
  preregistration.json
  benchmark-lock.json
  execution-authorization.json
  ledger/events/00000000.json ...
  attempts/000001/request.json
  attempts/000001/attempt.json
  private/raw/blobs/sha256/<digest>.bin
  recovery/000000.json ...
  capture-manifest.json
  judgment.json
  review-bundle.json
```

The configured output root rejects traversal, absolute/UNC/drive paths,
repository-control paths, Windows-reserved segments, trailing dots/spaces, and
symlink, junction, or reparse-point ancestors.

## Exact raw blobs

Raw request and response-body content is hashed directly as bytes and stored in
content-addressed `.bin` files. No text decoding, JSON parsing, newline
normalization, or redaction occurs before the byte digest. A descriptor records:

- representation and private path;
- SHA-256 and byte length;
- media type;
- complete or partial disposition;
- private visibility; and
- `capture_observed` provenance.

"Exact" means the bytes observed by the named adapter at the declared capture
boundary. It is not proof of provider-side origin, upstream wire fidelity,
model identity, SDK/proxy transparency, or hidden reasoning.

## Atomic append-only publication

Every governed file is fully written and fsynced to a same-directory temporary
file, then published through an exclusive hard link. Existing targets are never
overwritten. Initialization is assembled in a unique same-parent staging
directory and exposed with one no-replace directory rename, so a crash cannot
publish a partly initialized execution. A failed initializer can leave a hidden
staging directory for operator inspection; it is not treated as a run. Attempt
directories are created exclusively. Concurrent next-event writers target the
same sequence filename; exactly one can publish and the other fails with a
collision.

Each lifecycle event seals its canonical content, sequence, prior event hash,
execution ID, transition, timestamp, and payload. Verification rejects gaps,
extra files, malformed/noncanonical JSON, chain mismatch, and illegal state
changes.

## Identity hashes

- raw blob SHA-256: exact bytes only;
- event SHA-256: canonical event content including its declared timestamp;
- ledger root: final event hash;
- attempt digest: full immutable attempt record;
- capture content SHA-256: deterministic identities, statuses, and byte hashes,
  excluding capture timestamps and free-form metadata;
- manifest SHA-256: full canonical manifest bytes;
- judgment content SHA-256: deterministic judgment content excluding time;
- judgment and review-bundle SHA-256: full canonical artifact bytes.

Timestamps contribute to event/file seals where explicitly recorded, but do not
alter capture or judgment content identities.

## Provenance classes

| Class | Meaning |
|---|---|
| `git_verified` | Commit and bound bytes verified against Git |
| `capture_observed` | Bytes, lengths, status, and local timestamps observed at capture |
| `provider_declared_unverified` | Provider/model labels, request ID, usage, finish reason |
| `adapter_declared` | Adapter name, version, path, and labels |
| `operator_declared` | Authorization, retry reason, recovery, and abort action |
| `derived_deterministic` | Candidate validity, canonical content, score, and verdict |

No field is labelled verified provider identity without separately implemented
signed-provider evidence; alpha.2 implements no such evidence.

## Public/private separation

Raw blobs remain private and are never embedded in the review bundle. Public
artifacts admit only allowlisted transport metadata. Authorization headers,
cookies, API keys, credentials, and private keys are rejected. If raw bytes look
credential-like, they remain immutable in private storage while the public
manifest carries `SENSITIVE_RAW_PAYLOAD_WITHHELD` and only the digest.

Operational diagnostics contain a bounded code and classification
`derived_redaction`; they never contain an exception message, secret, request
header, cookie, or raw body and never claim to be original evidence.
The public review bundle contains a digest-bound execution-authorization
projection, not the declared operator identity. The private authorization file
remains available to the authorized human review process.

## Corrections and lineage

No stored artifact can be overwritten. A correction must use a new execution or
successor artifact and fill explicit predecessor/successor lineage references.
Alpha.2 leaves review bundles unratified and does not itself create promotion or
ratification lineage.
