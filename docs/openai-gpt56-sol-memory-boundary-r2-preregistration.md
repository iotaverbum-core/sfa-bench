# SFA-Bench R2 Preregistration: Permitted-State Preservation

## Status

**Preregistered design only. No R2 provider request is authorized by this document or its implementation.**

Study ID:

```text
openai-gpt56-sol-memory-boundary-r2
```

Tracked by issue #59.

## Research question

> How do public-state representation and an explicit retention reminder affect preservation of permitted identity state, particularly `customer_id`, without increasing forbidden-state use?

R1 produced 20 partial `state_loss` outcomes across 30 completed and ratified executions. In every partial outcome, `customer_id` was omitted while the observed outputs continued to respect the forbidden-state boundary. R2 therefore investigates a task-specific mechanism instead of repeating R1 unchanged.

## Frozen design

R2 uses one declared mutable provider alias:

```text
gpt-5.6-sol
```

The alias is not treated as an immutable model snapshot. Exact provider identity must be checked at execution time, every execution date must be retained, and no substitution is permitted.

The study is a balanced 2 × 2 design:

| Condition | State representation | Explicit retention reminder | Executions |
|---|---|---:|---:|
| `prose-no-reminder` | prose | no | 12 |
| `json-no-reminder` | structured JSON | no | 12 |
| `prose-reminder` | prose | yes | 12 |
| `json-reminder` | structured JSON | yes | 12 |
| **Total** |  |  | **48** |

The task, system prompt, deterministic scorer, taxonomy, and candidate normalizer remain bound to the existing memory-boundary case. The condition prompts are generated deterministically by `sfa_bench/campaigns/r2_plan.py`.

## Hypotheses

### H1 — Representation

Holding reminder status balanced, structured JSON representation will preserve all required permitted state at least as often as prose representation.

### H2 — Reminder

Holding representation balanced, an explicit retention reminder will preserve all required permitted state at least as often as no reminder.

### H3 — Interaction

The effect of the reminder may differ between prose and JSON representation. This interaction will be reported descriptively without significance testing.

## Sample size and ordering

R2 contains 48 fresh executions: 12 per condition.

Execution order is frozen as twelve blocks of four. Four balanced block orders are repeated three times. Consequently, every condition:

- appears exactly 12 times;
- appears exactly once in every block;
- occupies each ordinal block position exactly three times.

This is a fixed balancing procedure, not outcome-dependent randomization. The sample size prioritizes exact balance and operational feasibility and is not presented as a formal power calculation.

## Primary endpoint

For each condition:

> the proportion of completed, ratified deterministic judgments that preserve every required permitted field while using no forbidden state.

Completion counts are reported separately from the judgment denominator.

## Secondary endpoints

For each condition, R2 will report:

- `customer_id` loss proportion;
- forbidden-state-use proportion;
- any permitted-state-loss proportion;
- mean deterministic score;
- exact result-hash frequencies;
- refusal and malformed-output counts;
- transport-interruption counts.

The report will also provide descriptive pooled contrasts for representation and reminder status, plus a descriptive interaction contrast. No null-hypothesis significance tests or model rankings are preregistered.

## Attempt and stopping policy

- one request and one attempt per slot;
- no automatic retry;
- no replacement execution;
- no silent model substitution;
- no tools;
- `store: false`;
- no optional stopping;
- no outcome-dependent reordering;
- transport interruption consumes the initialized attempt and is preserved;
- model unavailability halts the affected slot without substitution;
- the campaign stops after the forty-eighth preregistered slot or an explicit human halt.

## Pilot rule

No R2 provider pilot is planned. The task, provider adapter, capture system, deterministic scorer, and ratification path were already exercised in R1. The new condition prompts are tested offline, and the complete confirmatory design is frozen before any R2 response is observed.

Any future deviation that introduces a pilot requires a new post-pilot preregistration. Pilot outcomes may not be added to the present R2 estimates.

## Governance sequence

Every execution remains subject to the existing separated workflow:

```text
explicit execution authorization
→ capture
→ seal
→ deterministic judgment
→ verification
→ human ratification
→ cohort closure
→ preservation
→ separate publication authorization
```

This preregistration grants none of those later authorities. In particular, merging this design does not authorize a provider request.

## Interpretation limits

R2 studies one frozen task under one declared mutable provider alias. It does not establish:

- general model quality or intelligence;
- fitness for a deployment or regulated industry;
- a provider or model ranking;
- a universal state-loss rate;
- an immutable model-snapshot claim;
- endorsement, certification, legal approval, or regulatory approval.

Condition effects are task-specific and may not generalize to other prompts, state schemas, providers, or execution dates.

## Offline implementation

The accompanying module:

- validates the complete preregistration;
- rejects execution or publication authority;
- generates the four exact prompt variants deterministically;
- derives the canonical 48-slot plan;
- binds every slot to the SHA-256 of its condition prompt;
- verifies exact condition and ordinal-position balance;
- fails closed on policy, identity, block-order, or digest changes;
- performs no network or provider request.

The accompanying tests cover balance, prompt-factor binding, deterministic regeneration, authority overreach, retry/substitution changes, block-order changes, and slot-plan tampering.

## Next gate

After this preregistration is merged and CI is green, execution still remains prohibited. A separate implementation must add a guarded R2 execution harness and pass offline review. Only then may the operator issue a distinct, explicit authorization for the first fixed R2 block.
