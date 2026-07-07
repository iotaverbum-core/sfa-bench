# AutoLab Pre-registration Gate (Item 2)

Pre-registration, borrowed from empirical science, means **committing to the
claim before you look at the result.** Before a patch is generated, the AutoLab
loop seals a *declaration*; afterwards a frozen evaluator produces an
*improvement report* from raw artifacts; the gate then checks the report against
the sealed declaration. This stops the loop from generating a patch and *then*
choosing whichever metric happens to look good — the metric, direction,
threshold, evaluation plan, and no-regression constraints are fixed in advance.

`autolab/preregistration.py` is **gate policy** and lives in the frozen zone (see
`autolab/frozen_manifest.json`, amendment `fz-v0.2.0`). The loop cannot patch it.

## The declaration (`sfa.autolab.preregistration.v0`)

Sealed before patch generation:

```json
{
  "schema": "sfa.autolab.preregistration.v0",
  "declaration_id": "prereg-demo-0001",
  "phase": "pre_patch",
  "target": { "metric": "continual_learning_score", "direction": "increase",
              "min_delta": 0.05, "decision_rule": "ci95_low_gt_0",
              "comparator": "incumbent" },
  "eval_plan": { "suite": "public+holdout",
                 "arms": ["candidate", "incumbent", "ancestor_anchor"],
                 "seeds": [...], "n": 30, "bootstrap": 2000,
                 "harness": "sfa.prior_state_trial.v1",
                 "holdout": { "budget_id": "frontier-delta-holdout:hd-v0.1.0",
                              "suite": "frontier-delta-holdout",
                              "version": "hd-v0.1.0", "units": 1 } },
  "protected_metrics": [
    { "name": "public_suite_pass_rate", "direction": "no_decrease", "tolerance": 0.0 },
    { "name": "holdout_lane_pass_count", "direction": "no_decrease", "tolerance": 0.0 },
    { "name": "verifier_latency_ms",     "direction": "no_increase", "tolerance": 5.0 }
  ],
  "declaration_hash": "<sha256 of the declaration minus this field>"
}
```

- **target** — the single primary metric, the direction of the expected effect,
  the pre-registered magnitude threshold (`min_delta`), the significance rule
  (`ci95_low_gt_0` / `ci95_high_lt_0` / `point_delta_only`), and the comparator.
- **eval_plan** — the exact suite, arms, seeds, and bootstrap settings. The
  report must have used *this* plan; a cherry-picked seed set is a deviation.
- **protected_metrics** — the Pareto no-regression constraint: metrics that must
  not move the wrong way beyond their tolerance.

## The improvement report (`sfa.autolab.improvement_report.v0`)

Computed by a **frozen evaluator** from raw artifacts, not by the builder. It
carries the raw numbers (metric values, deltas, bootstrap CI bounds), the
`declaration_hash` it is answering, the eval plan it actually ran, and an
advisory `builder_rationale`.

## The asymmetric gate

`evaluate_gate(declaration, report)` returns a `GateDecision` with `gate_green`
and a list of `reasons`. It embodies three invariants:

- **It may only reject (invariant 2).** `gate_green` means "nothing to reject."
  There is no `promote` field. Promotion needs deterministic-gate-green **and** a
  human ratification token (`autolab/ratification.py`, Item 4); the gate never
  promotes on its own.
- **The builder cannot attest (invariant 3).** Every pass/fail is **recomputed**
  from the report's raw numeric fields and the declaration's thresholds. Builder
  self-reported booleans and `builder_rationale` are ignored — a report cannot
  talk its way past the gate.
- **Determinism (invariant 6).** A pure function of the sealed inputs; canonical
  hashes seal both declaration and report; no wall-clock, network, model, or
  randomness.

Rejection reasons the gate can raise:

| Check | Rejected when |
| --- | --- |
| declaration binding | `report.declaration_hash != declaration.declaration_hash` |
| eval-plan conformance | report's plan ≠ the pre-registered plan |
| primary metric | wrong metric, wrong direction, `|delta| < min_delta`, or decision rule unmet |
| Pareto no-regression | any protected metric moved the wrong way beyond tolerance, or is missing |

The declaration must actually hash to its recorded `declaration_hash` or the gate
raises (a tampered declaration is not evaluated).

## What is and isn't enforced yet

Enforced by Item 2: hash binding of report -> declaration, eval-plan
conformance, recomputed primary + Pareto checks, determinism, and gate
asymmetry. Enforced by Item 3: the loop controller seals the declaration into
the append-only meta-ledger before invoking the builder, and consumes any
declared holdout access against a bounded budget before the builder callback
runs. Enforced by Item 4: gate-green still cannot promote without a sealed
human ratification record and matching token. See
[`docs/autolab-controller.md`](autolab-controller.md) and
[`docs/autolab-ratification.md`](autolab-ratification.md).

## CLI / fixtures

```bash
python preregistration_demo.py     # runs the gate on the sealed fixtures
```

Fixtures live in `examples/preregistration/`: a sealed `declaration.json`, a
`report_pass.json` that meets it, and a `report_regression.json` that violates
the Pareto constraint (a protected metric regressed) and is rejected.
`tests/test_preregistration.py` covers all rejection paths, determinism, and
builder-rationale blindness.
