# Frontier Delta Suite (v0)

A frozen, fixture-based behavioural benchmark for comparing captured candidate
artifacts against a stored baseline without changing the deterministic scorer.

## Historical labels

The strings `GPT-5.5`, `GPT-5.6`, `Sol`, `Terra`, and `Luna` occur in
historical fixtures and preregistration records. They are labels, not proof of a
provider model identifier, availability, provenance, snapshot, or completed run.
The stored `gpt55_outputs.jsonl` fixture does not establish named-model
performance.

**Not an AGI or alignment claim.** This suite measures specified behaviour under
eight benchmark lanes. It does not establish general intelligence, semantic
completeness, legal conformity, or overall model quality.

## The eight lanes

| Lane | What it measures | Task |
| --- | --- | --- |
| Long-horizon planning drift | Keeps the original objective and constraints | `planning_drift_001` |
| Memory / state boundary | Uses only authorized state | `memory_boundary_001` |
| Tool-use false completion | Claims completion only after tool success | `tool_false_completion_001` |
| Grounding integrity | Cites and matches supplied evidence | `grounding_integrity_001` |
| Contradiction recovery | Uses and flags the corrected value | `contradiction_recovery_001` |
| Open-ended adaptation | Applies a requirement change without regression | `open_ended_adaptation_001` |
| Paradigm-shift recognition | Replans after a premise is invalidated | `paradigm_shift_001` |
| Audit replayability | Emits a trail whose hash re-derives | `audit_replayability_001` |

## How it works

1. Tasks under `tasks/*.json` contain deterministic
   `scoring_rubric.checks`.
2. Fixture mode reads one `{task_id, output}` record per task. It makes no live
   API call.
3. Scorers return a score, verdict, failure modes, evidence snippets,
   explanation, replay status, and scoring mode.
4. The runner seals each result and a hash-chained report.

## Run fixture mode

```powershell
py -3 -m sfa_bench.frontier_delta.runner `
    --suite frontier_delta_v0 `
    --model historical-fixture-label `
    --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl `
    --out out/frontier_delta_fixture_baseline
```

An example sealed fixture baseline remains under `examples/gpt55_baseline/`.
Its historical model field is metadata and is not verified provider provenance.

## Add captured outputs later

A later capture component may produce the same JSONL shape. Point `--input` at
that file and use a candidate identity confirmed at execution:

```powershell
py -3 -m sfa_bench.frontier_delta.runner `
    --suite frontier_delta_v0 `
    --model TO_BE_CONFIRMED_AT_EXECUTION `
    --input path/to/candidate_outputs.jsonl `
    --out out/frontier_delta_candidate
```

This alpha release does not implement or run a provider adapter. Capture
fidelity remains outside the deterministic scorer.

## Freeze

See [`FROZEN_SUITE_v0.md`](FROZEN_SUITE_v0.md). Substantive task or scoring
changes require a new suite version.

## Limitations

- Fixture scoring does not prove the origin of captured data.
- Two `rubric_assisted` lane scores are directional proxies.
- One task per lane provides narrow coverage.
