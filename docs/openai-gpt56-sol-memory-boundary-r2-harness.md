# GPT-5.6 Sol permitted-state R2 execution harness

This document describes the guarded control plane for the preregistered study
`openai-gpt56-sol-memory-boundary-r2`.

The harness implementation is offline by default. Its presence, CI execution,
or merge does not authorize any provider request.

## Frozen study

The controlling preregistration fixes 48 fresh executions in twelve blocks of
four. Every block contains one execution from each condition:

1. prose representation without a retention reminder;
2. JSON representation without a retention reminder;
3. prose representation with a retention reminder;
4. JSON representation with a retention reminder.

Each condition has twelve executions and occupies every ordinal block position
exactly three times.

## Commands

### Initialize the canonical slot plan

```powershell
py -3 openai_gpt56_r2.py initialize
```

This command is credential-free. It derives the 48 slots mechanically from the
committed preregistration, writes the plan exclusively, reads it back, and
verifies its canonical bytes and digest before reporting success.

### Inspect status

```powershell
py -3 openai_gpt56_r2.py status
py -3 openai_gpt56_r2.py status --full
```

Status is derived from the canonical plan, run directories, attempt records,
and canonical block authorizations. It makes no provider request. A later
occupied slot while an earlier slot is pending, a second attempt, or a model
identity mismatch fails closed.

### Authorize the next block

```powershell
py -3 openai_gpt56_r2.py authorize-block `
  --operator "Matthew Neal" `
  --block 1 `
  --rationale "Authorize only the four frozen executions in R2 block 1."
```

Only the block containing the next pending slot can be authorized. The
authorization binds the preregistration digest, slot-plan digest, exact four
slots, fixed order, one-attempt policy, no replacement, no tools, no storage,
and no silent substitution. The stored record is read back and verified before
success is reported.

A block authorization permits only the four declared provider generations. It
does not authorize judgment, ratification, ranking, endorsement, promotion,
publication, release, certification, legal approval, or regulatory approval.

### Execute the next exact slot

```powershell
py -3 openai_gpt56_r2.py execute-next `
  --operator "Matthew Neal" `
  --block-authorization "<canonical block authorization path>" `
  --execute
```

`execute-next` refuses preparation-only use. It derives the next slot from
durable state and exposes no model, campaign, condition, position, prompt, or
execution-ID override.

The command verifies:

- the canonical slot plan;
- the exact next slot and block;
- the canonical stored block-authorization path and digest;
- the declared operator identity;
- the exact model alias `gpt-5.6-sol`;
- the condition prompt generated from the frozen R2 generator;
- the prompt SHA-256 bound in the slot plan;
- the one-attempt and no-substitution policy.

The execution-specific authorization ID incorporates the complete block
authorization digest. One initialized run consumes the slot. Interrupted or
failed transport is retained and is not retried or replaced.

## Provider boundary

The three offline commands never read `OPENAI_API_KEY`. Provider access is
reachable only after all execution checks pass and explicit `--execute` is
present. The underlying transport uses the existing execution-only OpenAI
Responses adapter with `store: false` and no tools.

Implementation tests mock delegation and make no live provider request.

## Prompt identity

Each condition prompt is generated deterministically by
`sfa_bench/campaigns/r2_plan.py`. The slot plan binds the SHA-256 of all four
prompts, and each slot carries the hash of its exact condition prompt. Before
execution, the prompt is regenerated and both bindings are rechecked. The exact
request bytes are then sealed by the existing alpha.2 capture authorization.

## Human gates after capture

Capture does not imply acceptance. Each execution remains unratified until the
existing offline sequence is completed separately:

1. seal and verify the capture;
2. create the deterministic judgment;
3. inspect the secret-free review bundle;
4. record an explicit human disposition.

Campaign closure, evidence preservation, publication, and release remain
separate later authorities.

## Current authority state

Merging the harness does not initialize the study, create a block
authorization, or send a provider request. The first provider generation
requires a later, explicit human authorization for block 1.
