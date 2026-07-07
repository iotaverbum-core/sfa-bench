# AutoLab Controller (Item 3)

The controller is the temporal boundary around an AutoLab iteration. Item 2
defined a pre-registration declaration and asymmetric gate; Item 3 makes the
ordering executable: the declaration is sealed into an append-only meta-ledger
before the builder callback can run, and any declared holdout use is consumed
against a bounded budget in that same ledger.

`autolab/controller.py` is frozen-zone machinery (added in manifest `fz-v0.3.0`).
The loop cannot rewrite it without a human amendment token.

## Iteration Order

`run_iteration(...)` performs one controlled builder iteration:

1. verify the existing meta-ledger hash chain;
2. attest the frozen zone and append `zone_attested_pre`;
3. seal the declaration and append `declaration_sealed`;
4. if the eval plan declares `holdout`, append `holdout_budget_consumed`;
5. append `builder_invoked`;
6. invoke the builder callback with the sealed declaration;
7. hash the builder result and append `builder_completed`;
8. attest the frozen zone again and append `zone_attested_post`.

The builder never writes the declaration, holdout receipt, zone attestation, or
hash-chain links. It receives the sealed declaration only after those controller
records exist. Promotion remains separate: Item 4 requires human ratification
after the deterministic gate is green.

## Meta-ledger

The meta-ledger is JSONL. Each entry has:

```json
{
  "schema": "sfa.autolab.meta_ledger.entry.v0",
  "seq": 0,
  "prev_hash": "GENESIS",
  "run_id": "controller-demo-run",
  "event_type": "declaration_sealed",
  "payload": { "...": "..." },
  "entry_hash": "<sha256 of the entry minus this field>"
}
```

`verify_meta_ledger(path)` detects deletion, insertion, reordering, or editing by
checking sequence numbers, `prev_hash`, and `entry_hash`.

## Holdout Budget

Holdout use must be explicit in `eval_plan.holdout`:

```json
{
  "suite": "public+holdout",
  "holdout": {
    "budget_id": "frontier-delta-holdout:hd-v0.1.0",
    "suite": "frontier-delta-holdout",
    "version": "hd-v0.1.0",
    "units": 1
  }
}
```

The controller compares that binding to a controller-side budget object
(`schema: sfa.autolab.holdout_budget.v0`) and refuses to run the builder if the
requested units would exceed `max_uses`. A plan that names a holdout suite but
omits `eval_plan.holdout` fails closed.

## CLI / Demo

```bash
python autolab_controller_demo.py
```

The demo uses a temporary meta-ledger and deterministic fake builder. It checks
that the declaration and holdout receipt are visible in the ledger before the
builder returns, that a second holdout consumption is rejected, and that the
frozen-zone hash is equal before and after the iteration.

Tests live in `tests/test_autolab_controller.py`.
