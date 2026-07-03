# Frontier Delta Suite (v0)

A frozen, fixture-based behavioural benchmark that establishes a **GPT-5.5
baseline** so future GPT-5.6 candidates (Sol, Terra, Luna) can be compared as
**behavioural deltas**, not accepted as marketing claims.

> SFA-Bench freezes a GPT-5.5 frontier baseline so future GPT-5.6 results can be
> measured as behavioural deltas rather than accepted as marketing claims.

**Not an AGI claim.** This suite measures whether a model preserves **truth,
state, objective, and accountability** under specific benchmark pressure across
eight lanes. It says nothing about general intelligence or overall quality.

## The eight lanes

| Lane | What it measures | Task |
| --- | --- | --- |
| Long-horizon planning drift | Keeps the original objective + constraints across many steps | `planning_drift_001` |
| Memory / state boundary | Uses only authorized state; no fabrication, no off-limits keys | `memory_boundary_001` |
| Tool-use false completion | Only claims "complete" when the tool actually succeeded | `tool_false_completion_001` |
| Grounding integrity | Every claim cites existing evidence and matches its value | `grounding_integrity_001` |
| Contradiction recovery | Uses the corrected value **and** flags the contradiction | `contradiction_recovery_001` |
| Open-ended adaptation | Adapts to a mid-task requirement change without regression | `open_ended_adaptation_001` |
| Paradigm-shift recognition | Notices when the founding premise is invalidated and replans | `paradigm_shift_001` |
| Audit replayability | Emits an audit trail whose declared hash re-derives exactly | `audit_replayability_001` |

## How it works

1. **Tasks** (`tasks/*.json`) are deterministic JSON with a machine-readable
   `scoring_rubric.checks` list.
2. **Model outputs** are supplied as a JSONL fixture (`fixtures/gpt55_outputs.jsonl`),
   one `{task_id, output}` record per task. v0 is fixture-only — no live API calls,
   so CI is deterministic.
3. **Scorers** (`scorers/`) run each task's checks with a deterministic engine and
   return structured results: `score` (0–1), `verdict` (pass/fail/partial),
   `detected_failure_modes`, `evidence_snippets`, `explanation`, `replay_possible`,
   and `scoring_mode` (`deterministic` or `rubric_assisted`).
4. **Runner** (`runner.py`) scores the whole suite and **report** (`report.py`)
   seals a baseline with per-lane / per-task scores, a failure-mode tally, replay
   status, and a hash-chained `results_root_hash` (SFA-Bench ledger pattern).

## Run it (fixture mode)

```bash
python -m sfa_bench.frontier_delta.runner \
    --suite frontier_delta_v0 \
    --model gpt-5.5 \
    --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl \
    --out out/frontier_delta_gpt55_baseline
```

An example sealed baseline is committed under `examples/gpt55_baseline/`
(`baseline_report.json`, `per_task_results.jsonl`, `summary.txt`).

## Adding real model outputs later

Produce the same JSONL shape from a real run — one `{"task_id": ..., "output": {...}}`
record per task, where `output` carries the fields each lane's rubric inspects
(e.g. `final_objective_id`, `claimed_state_keys`, `tool_log`, `claims`,
`audit_trail` + `audit_hash`). Point `--input` at that file and `--model` at the
candidate label (e.g. `gpt-5.6-sol`). The suite is unchanged, so the result is a
directly comparable delta against the frozen GPT-5.5 baseline.

## Freeze

The suite is frozen at v0 — see [`FROZEN_SUITE_v0.md`](FROZEN_SUITE_v0.md) for
exactly what may and may not change after the baseline is generated. Substantive
changes require a new suite version (`frontier_delta_v1`), keeping v0 comparable.

## Limitations

- Fixture-based: it scores the *structured artifact* of a model's run, not the raw
  transcript. Extracting that artifact faithfully from a real run is the
  integrator's responsibility.
- Two lanes are `rubric_assisted`; their machine scores are directional proxies.
- Small (one task per lane) by design, to keep the frozen baseline crisp. Breadth
  is added via new suite versions, not by mutating v0.
