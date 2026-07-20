# GPT-5.6 30-Slot Replication Harness

This harness controls the post-pilot memory-boundary replication declared in `campaigns/examples/openai-gpt56-memory-boundary-replication-r1.json`.

It derives exactly 30 slots from the committed ten-block order: ten executions each for `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`. Model aliases, campaign IDs, execution IDs, block order, and within-tier sequence numbers are not operator-selectable.

## Authority boundary

`initialize`, `status`, and `authorize-block` are offline and credential-free. They do not contact a provider.

A provider request can occur only through `execute-next` when all of the following are present:

- the immutable slot plan;
- the canonical authorization for the current block;
- the same declared operator identity;
- explicit `--execute`.

Each block authorization covers only its three preregistered slots. It does not authorize judgment, ratification, ranking, endorsement, promotion, publication, release, or legal approval.

## Initialize the plan

Run once after the harness is merged:

```powershell
py -3 openai_gpt56_replication.py initialize
```

The command writes the canonical slot plan beneath:

```text
out/replication_harness/openai-gpt56-memory-boundary-replication-r1/
```

The file is append-only: a second initialization fails rather than replacing it.

## Inspect progress

```powershell
py -3 openai_gpt56_replication.py status
```

Use `--full` to include all 30 slot records. Progress is derived from immutable capture directories, not from an editable counter.

An initialized run directory consumes its slot even if transport never completes. Interrupted, unavailable, or otherwise unsuccessful slots are never retried or replaced.

## Authorize one block

Only the next incomplete block can be authorized:

```powershell
py -3 openai_gpt56_replication.py authorize-block `
  --operator "Matthew Neal" `
  --block 1 `
  --rationale "Authorize the three fixed executions in replication block 1."
```

The resulting record is canonical, hash-bound to the preregistration and slot plan, and stored at the one accepted path for that block.

## Execute the next slot

Run exactly one slot at a time:

```powershell
py -3 openai_gpt56_replication.py execute-next `
  --operator "Matthew Neal" `
  --block-authorization "out\replication_harness\openai-gpt56-memory-boundary-replication-r1\block-authorizations\block-001.json" `
  --execute
```

Repeat `execute-next` for the second and third slots in that block. The harness derives the exact model and execution ID. There are no model, tier, slot, or execution-ID override flags.

After every capture, use the existing campaign workflow to seal, judge, bundle, verify, and obtain an explicit human disposition. The harness performs none of those actions automatically.

Do not authorize the next block until all three members of the current block have been reviewed and disposed. This operating rule keeps execution authority separate from evidence judgment.

## Fail-closed conditions

The harness refuses execution when it detects, among other conditions:

- a skipped or occupied-out-of-order slot;
- an authorization for a later block;
- a copied or tampered authorization record;
- a changed model alias or execution ID;
- more than one attempt in a slot;
- a mismatched operator declaration;
- a provider command without explicit `--execute`.

No provider request is made by installation, testing, initialization, status inspection, or block authorization.
