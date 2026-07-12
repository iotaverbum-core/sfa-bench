# External Candidate Provenance Boundary

The external boundary, introduced in v0.5-v0.7 and retained through
v2.0.0-alpha.1, can
evaluate candidate answers produced outside this repository
without letting external metadata contaminate the verifier.

This keeps the benchmark model-free: external candidates or transcripts can be
produced elsewhere and ingested locally without adding live model calls to CI.

The verifier still receives only:

- input
- evidence
- normalized candidate
- verifier rules

It remains blind to history, ledgers, artifacts, agent run folders, warnings,
provenance, adapter metadata, and gold labels.

The verifier invariants remain the architectural spine. Adapters may shape or
transport proposals; adapter state may never shape verifier judgment.

## Manual JSON Adapter

`ExternalCandidateAdapter` reads one local JSON file. It performs no network
calls and has no dependency on any model provider.

The adapter preserves the raw JSON source and normalizes it into
`candidate_answer.json` format:

```json
{
  "conclusion": "...",
  "cited_evidence": ["f2"],
  "claims": [{"subject": "approval_status", "value": "pending"}]
}
```

Supported raw source shapes include the canonical candidate shape, a nested
`candidate` object, or a compact manual form with `answer`, `evidence_ids`, and
`claims_by_subject`.

The v0.5 raw source is local JSON and is still candidate-shaped. For offline
model-style transcript fixtures, use the v0.6 transcript replay path or the
v0.7 optional adapter boundary documented in [Architecture Stack](architecture-stack.md).

## Optional Adapter Boundary

SFA-Bench v0.7 introduces `sfa.adapters`, a proposer-side adapter interface and
registry. The default adapter is `fixture-transcript-adapter-v0`, an offline
fixture adapter that returns transcript-shaped raw source compatible with the
v0.6 transcript normalizer.

Live adapters are disabled by default. When `CI=true`, the registry exposes only
offline adapters and rejects live adapter opt-in even if
`SFA_ENABLE_LIVE_ADAPTERS=1` is set.

The adapter returns a transcript. The transcript normalizer extracts the
candidate. The verifier receives only the normalized candidate, evidence, input,
and verifier rules.

## V2 Candidate-Output Validity Gate

The Frontier Delta candidate adapter applies one deterministic gate before lane
canonicalisation:

- empty or whitespace text: `no_model_output`;
- no strict JSON object found, including non-finite constants or unpaired
  Unicode surrogates: `unparseable_model_output`;
- valid non-object JSON: `invalid_model_output`; and
- valid JSON object: continue through the existing lane canonicaliser.

Invalid text receives zero credit and never reaches a canonicaliser or scorer.
For surrounding prose, extraction uses the first decodable top-level object;
when multiple top-level objects occur, the first wins. Objects nested inside a
non-object container such as an array are not extracted.
The gate preserves a deterministic response-text SHA-256 and parse notes; it does not
repair invalid text or invent a replacement object. Valid objects retain the
legacy canonicalisation contract, including its lane-specific normalization.

The historical Fable capture harness is preserved as external evidence tooling;
it is not a live adapter in the trusted registry and is not selected by CI. No
new provider capture surface is implemented in alpha.1.

## Provenance

Every attempt writes `attempt_NNN_provenance.json` beside the attempt files. The
record includes adapter identity, source location, raw source hash, normalized
candidate hash, input hash, evidence hash, creation time, whether a warning was
used, and `verifier_blind_to_provenance: true`.

Future production live attempts, if implemented, must be sealed immediately as
raw source before normalization and verification. Live adapter metadata may be
recorded in provenance, but must not be passed to the verifier.

As of v0.8, transcript provenance also formalizes `model_id` for grouping in
failure fingerprint reports. New transcript-derived ledger occurrences may
carry that field; legacy entries remain valid and resolve to `unknown`. Model
identity, fingerprint summaries, recurrence profiles, and fixed-condition
metadata remain outside the verifier boundary.

`sfa.provenance.verify_attempt_files()` compares the stored hashes to the run
folder files. If the raw source or normalized candidate is edited after the run,
the corresponding hash check fails.

## Demo

Run:

```bash
python external_candidate_demo.py
```

The demo loads a bad external candidate from
`examples/external_candidates/bad_candidate.json`, records raw source and
provenance, verifies the normalized candidate, seals/logs the failure, generates
a history warning, and retries once with
`examples/external_candidates/good_candidate.json`.

Both attempts are preserved under `agent_runs/<run_id>/`.

See [Architecture Stack](architecture-stack.md) for the boundary between the
deterministic offline instrument and the optional adapter surface. v1.0.0 adds
no provider integration. Alpha.1 adds candidate integrity and campaign controls,
not provider execution.
