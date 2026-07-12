# Frontier Delta Suite: Historical Fixture Protocol

> SFA-Bench freezes a stored fixture baseline so a later, confirmed candidate
> can be measured as a behavioural delta rather than accepted as a provider
> claim.

The Frontier Delta Suite is an experimental research suite (package
`sfa_bench.frontier_delta`) built on the SFA-Bench deterministic core. It does
not modify the frozen `sfa` research instrument; it reuses its conventions:
canonical hashing, sealed artifacts, and deterministic replay.

## Status of historical model names

`GPT-5.5`, `GPT-5.6`, `Sol`, `Terra`, and `Luna` are historical fixture
or preregistration labels in this repository. Their presence does not establish
that a provider identifier exists, that API access is available, that the stored
fixture came from the named model, or that any candidate run occurred.

Statements about model availability or training cutoffs in the protected
historical holdout preregistration are preserved assumptions, not verified
current facts. That protected record remains unchanged.

## Why a stored baseline fixture

Frontier releases can arrive with strong claims. A defensible comparison fixes a
measurement before observing a candidate, records a baseline fixture, and then
runs a confirmed candidate through the same measurement. The stored fixture is
the anchor for deterministic regression. Its historical model label is metadata,
not verified provider provenance.

## Why candidate identity remains unconfirmed

A future candidate should be evaluated against the frozen measurement, not used
to define it. If the suite were designed after observing candidate output, it
could drift toward whatever that candidate happens to do well. A confirmed
candidate result can instead be reported as a delta measured on identical,
pre-committed tasks.

## Why the suite is frozen

A benchmark that can change after candidate observation is not a stable
measurement. Freezing (`FROZEN_SUITE_v0.md`) fixes the lanes, tasks, scoring
rubrics, and scoring math. Substantive changes require a new suite version such
as `frontier_delta_v1`, preserving the v0 fixture comparison.

## What each lane measures

The core question is whether a candidate preserves truth, state, objective, and
accountability across long, open-ended, tool-mediated tasks.

1. **Long-horizon planning drift:** preserves the original objective and hard
   constraints across many steps.
2. **Memory / state boundary discipline:** uses only authorized state without
   fabricating state or reaching for off-limits keys.
3. **Tool-use false completion:** claims completion only when the tool returned
   success.
4. **Grounding integrity:** cites existing evidence and stays consistent with
   its value.
5. **Contradiction recovery:** adopts and flags a correction rather than
   silently overwriting it.
6. **Open-ended adaptation:** absorbs a mid-task requirement change without
   regressing requirements already met.
7. **Paradigm-shift recognition:** replans when a founding premise is
   invalidated.
8. **Audit replayability:** emits an audit trail whose declared hash re-derives.

The last three descriptions do not claim semantic completeness. The
`open_ended_adaptation` and `paradigm_shift_recognition` lanes are marked
`rubric_assisted`; their machine scores are deterministic proxies over explicit
fixture fields and remain directional.

## How scoring works

Each task carries a machine-readable `scoring_rubric.checks` list. A
deterministic check engine evaluates each check against the structured output.
A task score is the fraction of checks that pass. Its verdict is `pass` when
all checks pass, `fail` when any critical check fails, and `partial` when
only non-critical checks fail.

Each result is sealed with a `result_hash`. The report seals a `report_hash`
and a hash-chained `results_root_hash`. `generated_at` is envelope metadata
and is excluded from the content hash.

## Run fixture mode

v0 is fixture-only. The command makes no live API call:

```powershell
py -3 -m sfa_bench.frontier_delta.runner `
    --suite frontier_delta_v0 `
    --model historical-fixture-label `
    --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl `
    --out out/frontier_delta_fixture_baseline
```

The stored example under
`sfa_bench/frontier_delta/examples/gpt55_baseline/` scores `0.750` total
(5 pass, 1 partial, 2 fail). This is a fixture result, not evidence of named
provider-model performance.

Run the tests with:

```powershell
py -3 -m unittest discover -s tests -t . -p "test_*.py"
```

## Add captured outputs later

A later capture component may produce one JSONL record per task:

```json
{"task_id": "grounding_integrity_001", "output": {"example": "lane fields"}}
```

The `output` object supplies the structured fields inspected by the lane
rubric. Capture fidelity is the integrator's responsibility. The candidate
identifier must be confirmed at execution:

```powershell
py -3 -m sfa_bench.frontier_delta.runner `
    --suite frontier_delta_v0 `
    --model TO_BE_CONFIRMED_AT_EXECUTION `
    --input path/to/candidate_outputs.jsonl `
    --out out/frontier_delta_candidate
```

Because the suite is frozen, a resulting report is a delta against the stored
fixture baseline. A provider-neutral live capture adapter is planned for a later
V2 tranche; this alpha release does not implement or run one.

## Limitations

- **Not an AGI or alignment claim.** The suite measures specified behaviour
  under eight benchmark lanes.
- **Fixture-based.** It scores a structured artifact, not the raw transcript.
- **Names are not provenance.** Historical labels do not verify provider model
  identity, access, snapshot, training cutoff, or execution.
- **Rubric-assisted lanes.** Two machine scores are directional proxies.
- **Deliberately small.** One task per lane supports a crisp frozen fixture;
  breadth requires a separately versioned suite.
