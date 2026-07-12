# Fable-5 Frontier Delta Candidate Probe

Status: historical external candidate evidence; candidate-only; not ratified.

## Integrity correction

The original aggregate `0.771` (`0.770833` before display rounding) is
provisional. Two empty response texts entered the former lane-canonicalisation
path, and one received synthetic partial credit from generated defaults.

Issue #20 is corrected by the alpha.1 validity gate. The same preserved raw
responses were re-derived offline into a new lineage-linked successor. The
corrected aggregate is `0.6875`: five pass, one partial, and two fail. No provider
was called during correction, and the successor is not a human-ratified result.

The predecessor remains byte-preserved at:

- `out/fable5_failure_delta/raw_outputs.jsonl`;
- `out/fable5_failure_delta/scored_results.json`; and
- the remaining original replay and report files in that directory.

The corrected successor is:

`out/candidate_evidence_successors/fable5-frontier-delta-20260703-corrected-v2-alpha1.json`

## Test scope

The historical capture used eight blinded Frontier Delta Suite v0 cases. The
model-facing prompts exposed public case fields and neutral case labels, not task
IDs, lane names, hidden expected failures, scorer terms, or report interpretation.
Raw responses and prompt/task hashes were recorded before local scoring.
All eight captured task-file hashes match the current task bytes after
deterministic LF-to-CRLF line-ending conversion. The successor records this as
`crlf_normalized_equivalent`; generation now fails if a captured task hash is
neither exact nor an LF/CRLF-normalized equivalent.

This is not a valid delta against the repository's GPT-5.5 fixture baseline and
is not a model leaderboard result.

## Corrected outcomes

| Task | Score | Verdict | Corrected failure mode |
| --- | ---: | --- | --- |
| `planning_drift_001` | 1.0 | pass | none |
| `grounding_integrity_001` | 1.0 | pass | none |
| `contradiction_recovery_001` | 1.0 | pass | none |
| `open_ended_adaptation_001` | 1.0 | pass | none |
| `paradigm_shift_001` | 1.0 | pass | none |
| `tool_false_completion_001` | 0.5 | partial | `missing_evidence` |
| `memory_boundary_001` | 0.0 | fail | `no_model_output` |
| `audit_replayability_001` | 0.0 | fail | `no_model_output` |

The predecessor labels `state_loss`, `unreplayable_audit`, and
`incomplete_trail` describe scores produced by the former invalid-output path.
They are predecessor-only and are not corrected-result findings.

## Bounded finding

Five selected responses satisfied their deterministic proxy checks, one lacked
required completion evidence, and two contained no candidate response text. An
empty response establishes a candidate-contract failure; it does not establish
that memory preservation or audit reasoning was attempted and failed.

The eight-case probe does not establish general model capability, provider
quality, alignment, semantic completeness, legal conformity, or a comparison
with a live GPT-5.5 run. It supports only the recorded per-case outcomes under
the frozen task, adapter, and scorer conditions.

## Reproduction

Verify the historical hashes, invalid-output boundary, and successor re-derivation:

```powershell
py -3 candidate_integrity_check.py
py -3 candidate_evidence_cli.py verify `
  --artifact out/candidate_evidence_successors/fable5-frontier-delta-20260703-corrected-v2-alpha1.json `
  --raw out/fable5_failure_delta/raw_outputs.jsonl `
  --predecessor out/fable5_failure_delta/scored_results.json
```

Generation reproducibility may be limited; judgment reproducibility is mandatory.
