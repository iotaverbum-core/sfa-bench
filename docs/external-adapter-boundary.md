# External Candidate Provenance Boundary

SFA-Agent v0.5 can evaluate candidate answers produced outside this repository
without letting external metadata contaminate the verifier.

The verifier still receives only:

- input
- evidence
- normalized candidate
- verifier rules

It remains blind to history, ledgers, artifacts, agent run folders, warnings,
provenance, adapter metadata, and gold labels.

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

## Provenance

Every attempt writes `attempt_NNN_provenance.json` beside the attempt files. The
record includes adapter identity, source location, raw source hash, normalized
candidate hash, input hash, evidence hash, creation time, whether a warning was
used, and `verifier_blind_to_provenance: true`.

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
