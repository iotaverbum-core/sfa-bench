# SFA-Bench V2 Alpha.2 Campaign Execution Protocol

Status: implementation candidate; repository version remains
`v2.0.0-alpha.1` until the separate human-authorized release amendment.

Alpha.2 adds an offline-testable execution and evidence-capture envelope outside
the deterministic judgment boundary. No live provider campaign was run.

## Trust flow

```text
preregistration + benchmark lock
  -> declared execution-only authorization
  -> provider-neutral byte transport
  -> private append-only capture
  -> sealed capture manifest
  -> separate offline deterministic judgment
  -> secret-scanned, allowlisted, unratified human-review bundle
```

The adapter transports evidence. It does not validate its own lock, score its
response, ratify evidence, or publish anything. Canonical verification imports
no live provider SDK and requires no credential.

## Lifecycle

The current state is derived only from a verified immutable event chain:

```text
draft
  -> validated
  -> locked
  -> execution_authorized
  -> capturing
  -> captured
  -> sealed
  -> judged
  -> review_required
```

Interruption branches are explicit:

```text
capturing -> interrupted -> capturing   # declared successor attempt
capturing -> interrupted -> aborted -> sealed -> review_required
```

Skipped, repeated, contradictory, unknown, removed, inserted, reordered, or
hash-invalid transitions fail closed. File presence is never a completion
signal. `captured` requires a complete immutable attempt record and response
blob; `sealed` requires a verified manifest and lifecycle root.
`judged` requires a reproducible judgment artifact, and `review_required` requires
a source-bound review bundle. Orphaned manifest, judgment, and bundle files are
verified and reconciled without rewriting their original bytes.

## Authorization boundary

`execution-authorization.schema.json` binds:

- campaign and benchmark-lock identities;
- benchmark and verifier commits and release identifier;
- execution ID;
- adapter ID, version, and lock-bound implementation path;
- exact request SHA-256 and byte length;
- prompt and case references present as exact lock bindings;
- preregistered retry scope; and
- a declared operator identity with scope `execution_only`.

All automatic ratify, promote, publish, and release fields must be `false`.
Validation proves internal artifact consistency. It does not verify that the
submitter is human or establish legal authority, consent, entitlement,
ownership, or provider approval.

## Execution boundary

`CaptureAdapter.transport()` accepts `LockedCaptureRequest` and returns
`TransportResult`. The core preserves authorized request bytes before dispatch,
then preserves response or partial-response bytes before interpreting metadata.
Only allowlisted transport observations can enter public records. Provider and
adapter labels remain declared, unverified metadata.

The checked-in `SyntheticAdapter` covers valid JSON objects, empty output,
refusal-like text, malformed/non-object/non-finite JSON, timeouts, transport
errors, retry conditions, duplicate provider identifiers, partial streams,
interrupted writes, binary/non-UTF-8 responses, misleading identity metadata,
and credential-like metadata. It never opens a network connection.

## Capture and judgment separation

`seal_run()` ends execution with immutable captured evidence. `judge_run()` is a
separate offline operation that re-verifies Git and lock provenance, raw blobs,
attempt records, lifecycle continuity, capture manifest, task binding, and
verifier commit before using the unchanged Frontier Delta candidate judgment
path. Invalid candidate outputs receive explicit zero credit before scorer
dispatch, preserving alpha.1 behavior.

Transport, retry, provider, adapter, and authorization metadata project to empty
objects in the judgment artifact. They cannot alter the deterministic result.

## Review boundary

`build_review_bundle()` includes public preregistration, lock, a digest-bound
authorization projection with operator identity redacted, the pre-review
lifecycle chain, raw-evidence hashes, capture manifest, adapter provenance,
integrity report, judgment when available, warnings, limitations, and lineage
placeholders. Its immutable digest is bound by the subsequent
`review_required` event. It excludes raw bodies and states:

```json
{"packaging_is_approval":false,"ratification_status":"unratified","raw_bodies_included":false}
```

Human review remains mandatory. The CLI exposes no ratify, promote, tag, merge,
push, publish, or release command.

## Offline verification

```powershell
py -3 -m unittest tests.test_campaign_capture
py -3 campaign_capture_check.py
py -3 campaign_capture_cli.py --help
```

`campaign_capture_check.py` constructs a lock at committed `HEAD`, requires the
alpha.2 package and schema files in its bindings, runs one deterministic
synthetic capture, seals it, judges it, packages it for review, and re-verifies
the bundle. Runtime evidence is written only to a temporary directory.

## Compatibility

Alpha.2 is additive. It does not edit the alpha.1 campaign CLI, schemas,
protocol, locking module, package initializer, frozen verifier, fixed scorer,
frozen ledger, release gate, or frozen-zone machinery. Alpha.2 campaigns bind
the new implementation and schemas through existing benchmark input paths;
alpha.1 lock reproduction remains byte-identical.
