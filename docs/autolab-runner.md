# AutoLab End-to-End Runner (Item 7)

Item 7 adds the frozen runner that wires Items 1-6 into one sequence. The runner
does not build patches itself; it controls when the builder may run and records
every gate, rejection, promotion, and halt in the append-only meta-ledger.

## Sequence

`run_autolab_iteration(...)` enforces:

1. reject start if an `autolab_halted` entry is active;
2. evaluate circuit breakers before invoking the builder;
3. run the Item 3 controller so declaration sealing, holdout consumption, and
   pre/post frozen-zone attestation are ordered before and after the builder;
4. seal the frozen-evaluator improvement report and recompute the
   pre-registration gate;
5. append `gate_rejected` when the deterministic gate is red;
6. require a sealed human ratification record plus matching token before
   appending `human_ratification`;
7. inscribe the promoted target into append-only lineage; and
8. evaluate circuit breakers again after promotion, appending `autolab_halted`
   when the completed iteration exhausts a budget or trips another breaker.

## Rejection Events

The runner appends rejection events instead of silently returning:

- `gate_rejected` for red deterministic gates;
- `human_ratification_rejected` for missing, rejected, or token-mismatched human
  approval;
- `promotion_rejected` for malformed or mismatched promotion records; and
- `autolab_rejected` for controller or lineage failures.

Those events are the history that Item 6 counts for consecutive-rejection and
withered-lineage breakers.

## Demo

```bash
python autolab_runner_demo.py
```

The demo runs a green path through lineage inscription, a gate-red rejection, and
a preflight breaker that halts before the builder callback can run.
