# AutoLab Item 5 Checkpoint - Lineage + Rollback

Scope: a frozen promotion-history layer that inscribes human-ratified
promotions into append-only lineage and requires a sealed, human-token-gated
rollback event to move the current target back to a restore ref.

## Delivered

- `autolab/lineage.py` - promotion inscription, deterministic lineage-state
  derivation, sealed rollback records, and rollback append policy.
- `lineage_demo.py` - offline deterministic runner added to `verify_all.py`.
- `tests/test_autolab_lineage.py` - deterministic tests for ratification-only
  inscription, duplicate-current rejection, rollback token requirement,
  rollback tamper detection, state derivation, and frozen-zone integration.
- `docs/autolab-lineage.md`.
- Frozen-zone amendment `fz-v0.5.0-add-lineage-rollback`: the lineage module
  joins the frozen zone and the manifest is resealed as `fz-v0.5.0`.

## Acceptance Notes

- **Promotion requires inscription.** Item 4 promotion remains explicit, but a
  target becomes current only after a separate `promotion_inscribed` event.
- **Builder cannot inscribe.** Inscription requires a meta-ledger hash for an
  existing `human_ratification` event. Builder-completed events and self-reported
  refs are rejected.
- **Rollback is append-only.** Rollback appends `rollback_inscribed`; it does not
  delete, reorder, or rewrite the prior promotion.
- **Human rollback token required.** A sealed rollback record is necessary but not
  sufficient. A matching out-of-loop rollback token is also required.
- **Current-target binding.** Rollback can only target the current derived
  lineage ref. Stale, unknown, or tampered rollback records are rejected.
- **Frozen zone.** `autolab/lineage.py` is frozen; changing it requires the
  human amendment channel.

## Verification

Run in an LF checkout/worktree:

```bash
python lineage_demo.py
python -m unittest discover -s tests -t . -p "test_*.py"
python verify_all.py
python release_gate.py --ci
```

The lineage layer is stdlib-only and does not call a model, provider, or network.
