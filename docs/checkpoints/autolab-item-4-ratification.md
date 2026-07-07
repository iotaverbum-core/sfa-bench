# AutoLab Item 4 Checkpoint - Human Ratification

Scope: a frozen promotion layer that requires a deterministic gate-green result
and a human-supplied token matching a sealed ratification record before any
candidate can be promoted.

## Delivered

- `autolab/ratification.py` - sealed human ratification records, promotion
  evaluation, and meta-ledger append for successful human ratification.
- `ratification_demo.py` - offline deterministic runner added to `verify_all.py`.
- `tests/test_autolab_ratification.py` - deterministic tests for token
  requirement, red-gate rejection, binding checks, tamper detection,
  meta-ledger append behavior, and frozen-zone integration.
- `docs/autolab-ratification.md`.
- Frozen-zone amendment `fz-v0.4.0-add-ratification`: the ratification module
  joins the frozen zone and the manifest is resealed as `fz-v0.4.0`.

## Acceptance Notes

- **Asymmetric gate preserved.** The Item 2 gate still has no promotion path.
  Promotion is a separate Item 4 decision that can succeed only after the gate is
  green.
- **Human token required.** Gate-green without a matching ratification token is
  rejected.
- **Gate red cannot be overridden.** A human token cannot promote a report that
  the deterministic gate rejects.
- **Builder cannot attest.** Promotion recomputes the gate decision and binds the
  sealed ratification record to declaration hash, report hash, and gate-decision
  hash. Builder rationale and self-reported booleans do not affect promotion.
- **Append-only lineage.** Successful promotion appends `human_ratification` to
  the Item 3 meta-ledger; rejected attempts append nothing.
- **Frozen zone.** `autolab/ratification.py` is frozen; changing it requires the
  human amendment channel.

## Verification

Run in an LF checkout/worktree:

```bash
python ratification_demo.py
python -m unittest discover -s tests -t . -p "test_*.py"
python verify_all.py
python release_gate.py --ci
```

The ratification layer is stdlib-only and does not call a model, provider, or
network.
