# AutoLab Item 6 Checkpoint - Circuit Breakers

Scope: a frozen halt-and-hold layer that evaluates deterministic breaker
conditions around the AutoLab loop and requires sealed human restart clearance
before the loop can resume after a halt.

## Delivered

- `autolab/circuit_breakers.py` - breaker report evaluation, halt append policy,
  wither directives, sealed restart clearance, and human-token-gated restart.
- `circuit_breakers_demo.py` - offline deterministic runner added to
  `verify_all.py`.
- `tests/test_autolab_circuit_breakers.py` - deterministic tests for each breaker
  family, halt append behavior, restart token requirement, tamper detection,
  wither directives, and frozen-zone integration.
- `docs/autolab-circuit-breakers.md`.
- Frozen-zone amendment `fz-v0.6.0-add-circuit-breakers`: the circuit-breaker
  module joins the frozen zone and the manifest is resealed as `fz-v0.6.0`.

## Acceptance Notes

- **Halt conditions are deterministic.** Breaker evaluation depends only on
  frozen-zone attestation, controller meta-ledger entries, proposed path names,
  explicit budget counters, and configured thresholds.
- **Six breaker families.** The report trips for zone mismatch, chain break,
  holdout exhaustion, consecutive rejections, proposed frozen-path changes, and
  cost/time budget overrun. It also blocks re-proposal of a withered lineage.
- **Append-only halt.** A halt is appended as `autolab_halted`; existing ledger
  history is not rewritten.
- **Human restart required.** Restart appends `autolab_restart_authorized` only
  after a sealed clearance record and matching human token bind the active halt.
- **Builder cannot attest.** Caution/wither directives are advisory and explicitly
  excluded from gate inputs.
- **Frozen zone.** `autolab/circuit_breakers.py` is frozen; changing it requires
  the human amendment channel.

## Verification

Run in an LF checkout/worktree:

```bash
python circuit_breakers_demo.py
python -m unittest discover -s tests -t . -p "test_*.py"
python verify_all.py
python release_gate.py --ci
```

The circuit-breaker layer is stdlib-only and does not call a model, provider, or
network.
