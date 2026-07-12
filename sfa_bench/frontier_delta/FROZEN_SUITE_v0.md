# FROZEN SUITE - Frontier Delta v0

**Suite name:** Frontier Delta Suite

**Suite version:** `frontier_delta_v0`

**Status:** frozen for fixture-baseline comparison

**Baseline label:** historical fixture label `gpt-5.5`

The baseline label above is preserved metadata. It does not establish provider
model identity, access, provenance, snapshot, or performance. Candidate names in
historical preregistration records are likewise unverified labels.

## Purpose

Establish a frozen behavioural fixture baseline so later captured candidate
artifacts can be rerun against the same unchanged suite and reported as measured
deltas rather than accepted as provider claims.

This suite measures specified preservation of truth, state, objective, and
accountability across long, open-ended, tool-mediated tasks. It is not a claim
of AGI, alignment, semantic completeness, or overall model quality.

## Frozen task list

| Lane | Task ID |
| --- | --- |
| long_horizon_planning_drift | `planning_drift_001` |
| memory_state_boundary | `memory_boundary_001` |
| tool_use_false_completion | `tool_false_completion_001` |
| grounding_integrity | `grounding_integrity_001` |
| contradiction_recovery | `contradiction_recovery_001` |
| open_ended_adaptation | `open_ended_adaptation_001` |
| paradigm_shift_recognition | `paradigm_shift_001` |
| audit_replayability | `audit_replayability_001` |

## Frozen scoring rules

- Each task is scored by the deterministic check engine over its
  `scoring_rubric.checks`.
- A verdict is `pass` if every check passes, `fail` if any critical check
  fails, and `partial` otherwise.
- A score is the fraction of checks passed.
- `open_ended_adaptation` and `paradigm_shift_recognition` are
  `rubric_assisted`; their deterministic fixture scores are directional
  proxies.
- Reports seal deterministic content with a `report_hash` and a hash-chained
  `results_root_hash`. `generated_at` remains outside the content hash.

## What may and may not change

The following MUST NOT change within v0:

- the set of lanes and frozen task IDs;
- task objectives, prompts, hard constraints, supplied state, scoring rubrics,
  and replay requirements;
- check-engine semantics and verdict policy;
- report scoring math.

A substantive change requires a new suite version such as
`frontier_delta_v1`.

The following MAY change without altering the v0 measurement:

- documentation, comments, and bounded claim corrections;
- additive tooling that does not alter scoring;
- new, separately versioned suites.

## Fixture provenance

The stored baseline fixture is
`fixtures/gpt55_outputs.jsonl`. Its filename and model label are historical,
not verified provider provenance. It can be replayed offline:

```powershell
py -3 -m sfa_bench.frontier_delta.runner `
    --suite frontier_delta_v0 `
    --model historical-fixture-label `
    --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl `
    --out out/frontier_delta_fixture_baseline `
    --now 2026-07-03T00:00:00+00:00
```

The example sealed fixture result remains under `examples/gpt55_baseline/`.
It is a reproducibility fixture, not a provider evaluation claim.
