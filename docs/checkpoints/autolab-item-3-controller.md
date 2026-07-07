# AutoLab Item 3 Checkpoint - Controller + Budgeted Holdout

Scope: a frozen controller that seals the pre-registration declaration into an
append-only meta-ledger before invoking the builder, records frozen-zone
pre/post attestation around the iteration, and consumes any declared holdout use
against a bounded budget.

## Delivered

- `autolab/controller.py` - controller API, meta-ledger hash chain, holdout budget
  receipts, and pre/post frozen-zone attestation.
- `autolab_controller_demo.py` - offline deterministic runner added to
  `verify_all.py`.
- `tests/test_autolab_controller.py` - deterministic tests for temporal ordering,
  holdout-budget bounds, identity binding, tamper detection, and frozen-zone
  integration.
- `docs/autolab-controller.md`.
- Frozen-zone amendment `fz-v0.3.0-add-controller`: the controller joins the
  frozen zone and the manifest is resealed as `fz-v0.3.0`.

## Acceptance Notes

- **Temporal commitment.** The builder callback runs only after
  `declaration_sealed` is already in the meta-ledger. Tests inspect the ledger
  from inside the builder callback.
- **Append-only lineage.** The meta-ledger carries `seq`, `prev_hash`, and
  `entry_hash`; edits to prior entries are detected before another iteration can
  run.
- **Budgeted holdout.** Any eval plan naming holdout use must bind
  `budget_id`, `suite`, `version`, and `units`. The controller appends a
  `holdout_budget_consumed` receipt before builder invocation and refuses a
  request that exceeds `max_uses`.
- **Frozen zone.** `autolab/controller.py` is frozen; changing it requires the
  human amendment channel.
- **Builder cannot attest.** Builder output is hashed and recorded, but builder
  output cannot create the declaration, consume holdout budget, or attest the
  frozen zone.

## Verification

Run in an LF checkout/worktree:

```bash
python autolab_controller_demo.py
python -m unittest discover -s tests -t . -p "test_*.py"
python verify_all.py
python release_gate.py --ci
```

The controller itself is stdlib-only and does not call a model, provider, or
network.
