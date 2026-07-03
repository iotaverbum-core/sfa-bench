# Frontier Delta Suite: GPT-5.5 Baseline Protocol

> SFA-Bench freezes a GPT-5.5 frontier baseline so future GPT-5.6 results can be
> measured as behavioural deltas rather than accepted as marketing claims.

The Frontier Delta Suite is an experimental research suite (package
`sfa_bench.frontier_delta`) built on the SFA-Bench deterministic core. It does not
modify the frozen `sfa` research instrument; it reuses its conventions (canonical
hashing, sealed artifacts, deterministic replay).

## Why a GPT-5.5 baseline

Frontier releases arrive with strong claims. The only honest way to judge the next
model is to fix a **measurement** *before* the next model exists, run the current
model through it, seal the result, and then run the candidate through the exact
same measurement. GPT-5.5 is the **anchor**: a known, current frontier model whose
behaviour we record now, while nobody has an incentive to tune the suite toward a
result.

## Why GPT-5.6 is the future candidate

GPT-5.6 (and its variants Sol, Terra, Luna) are the models we want to *evaluate*,
not define the test around. If we designed the suite after seeing them, the suite
would drift toward whatever they happen to do well. By freezing against GPT-5.5, a
GPT-5.6 result becomes a **delta**: "+0.12 on grounding integrity, −0.25 on tool
false-completion," measured on identical, pre-committed tasks.

## Why the suite must be frozen before candidate testing

A benchmark you can edit after seeing the candidate is a marketing surface, not a
measurement. Freezing (`FROZEN_SUITE_v0.md`) fixes the lanes, the tasks, the
scoring rubrics, and the scoring math. After the baseline is generated, those must
not change; substantive changes require a new suite version
(`frontier_delta_v1`), which keeps the v0 baseline comparable. This is the same
discipline the SFA-Bench core uses for its taxonomy and sealed artifacts.

## What each lane measures

The core question: *can a frontier model preserve **truth, state, objective, and
accountability** while operating across long, open-ended, tool-mediated tasks?*
Eight lanes probe distinct ways that breaks:

1. **Long-horizon planning drift** — does the model still pursue the original
   objective and its hard constraint after many steps, or has it quietly drifted?
2. **Memory / state boundary discipline** — does it rely only on authorized state,
   without fabricating state or reaching for off-limits keys?
3. **Tool-use false completion** — does it claim "done" only when the tool actually
   returned success, or does it declare victory on a failed/absent tool result?
4. **Grounding integrity** — is every factual claim cited to existing evidence and
   consistent with that evidence's value?
5. **Contradiction recovery** — when an earlier value is corrected, does it adopt
   the correction **and** flag it, rather than silently overwriting?
6. **Open-ended adaptation** *(rubric-assisted)* — does it absorb a mid-task
   requirement change without regressing the requirements it already met?
7. **Paradigm-shift recognition** *(rubric-assisted)* — when the founding premise
   is invalidated, does it recognize it and replan, or continue on a dead premise?
8. **Audit replayability** — does it emit an audit trail whose declared hash
   re-derives exactly, so a third party can replay and verify the run?

Two lanes (6, 7) are marked `rubric_assisted`: their real-world judgment needs
human assessment, so the machine score is a deterministic proxy over explicit
fixture fields and is reported as directional, not final.

## How scoring works

Each task carries a machine-readable `scoring_rubric.checks` list. A deterministic
check engine evaluates each check against the model's structured output and returns
`(passed, evidence)`. A task's `score` is the fraction of checks that pass; its
`verdict` is **pass** (all checks pass), **fail** (any `critical` check fails), or
**partial** (only non-critical checks fail). Every result is sealed with a
`result_hash`, and the report seals a `report_hash` plus a hash-chained
`results_root_hash` (the SFA-Bench ledger pattern). `generated_at` is metadata and
is excluded from the hash, so the sealed content is byte-stable over time.

## How to run fixture mode

v0 is fixture-only — no live API calls — so CI is fully deterministic:

```bash
python -m sfa_bench.frontier_delta.runner \
    --suite frontier_delta_v0 \
    --model gpt-5.5 \
    --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl \
    --out out/frontier_delta_gpt55_baseline
```

The example GPT-5.5 baseline (committed under
`sfa_bench/frontier_delta/examples/gpt55_baseline/`) scores **0.750** total
(5 pass / 1 partial / 2 fail), correctly flagging a tool false-completion and a
paradigm-shift miss. Run the tests with:

```bash
python -m unittest discover -s tests -v
```

## How to add real model outputs later

Produce a JSONL file with one record per task:

```json
{"task_id": "grounding_integrity_001", "output": { ... lane-specific fields ... }}
```

The `output` object supplies the structured fields each lane's rubric inspects
(e.g. `final_objective_id`, `claimed_state_keys`, `tool_log`, `claims`,
`final_answer_value`, `audit_trail` + `audit_hash`). This is the integrator's job:
faithfully extract the model's final state / tool log / audit trail from a real run
into that shape. Then:

```bash
python -m sfa_bench.frontier_delta.runner --suite frontier_delta_v0 \
    --model gpt-5.6-sol --input path/to/gpt56_sol_outputs.jsonl \
    --out out/frontier_delta_gpt56_sol
```

Because the suite is frozen, the candidate report is a direct delta against the
GPT-5.5 baseline. A thin live-model adapter can be added later that produces the
same fixture shape; it does not change the suite or its scoring.

## Limitations

- **Not an AGI claim.** This measures behaviour under specific benchmark pressure
  across eight lanes. It says nothing about general intelligence or overall quality.
- **Fixture-based.** It scores the *structured artifact* of a run, not the raw
  transcript. Extraction fidelity is the integrator's responsibility.
- **Rubric-assisted lanes.** Open-ended adaptation and paradigm-shift recognition
  use deterministic proxies for what is ultimately a human judgment.
- **Deliberately small.** One task per lane keeps the frozen baseline crisp;
  breadth comes from new suite versions, never from editing v0.
