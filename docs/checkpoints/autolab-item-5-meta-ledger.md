# Checkpoint — AutoLab Item 5: Meta-ledger + circuit breakers

Scope: patch fingerprints, rejection inscription, recurrence-fed caution
directives into the next proposal context, and six halt-and-hold circuit
breakers (zone hash mismatch, chain break, holdout budget exhausted, N
consecutive rejections, gate/policy diff, cost/time budget) requiring human
restart; wither terminal for K-fail patch lineages.

## Deliverables

- `autolab/meta_ledger.py` — append-only hash-chained meta-ledger,
  `inscribe_from_loop`, `caution_directives` + `is_withered`,
  `evaluate_breakers`, `halt`/`clear_halt` (**frozen** via amendment `fz-v0.5.0`).
- `meta_ledger_demo.py` — ledger + wither + all six breakers + halt/restart
  (added to `verify_all.py`).
- `tests/test_meta_ledger.py` — 25 deterministic tests.
- `autolab/frozen_manifest.json` → `fz-v0.5.0` (16 frozen files);
  `autolab/amendments/fz-v0.5.0-add-meta-ledger.json` records the
  `410db5b2… → ba5ce1c5…` transition.
- `docs/autolab-meta-ledger.md`.

## Acceptance criteria

- **Each breaker unit-tested against a fixture.** `CircuitBreakerTests` trips
  each of the six breakers against a dedicated fixture and asserts a clean
  context does not halt; the demo trips all six.
- **Wither terminal for K-fail patch lineages.** `test_lineage_withers_at_k` and
  `test_wither_is_terminal`: a lineage rejected K times withers to a terminal
  "do not re-propose" and stays withered.

## The six hard invariants — explicit accounting

1. **Frozen zone.** `autolab/meta_ledger.py` is added to the zone (amendment
   `fz-v0.5.0`). One breaker, `gate_policy_change_proposed`, halts on **any**
   proposed diff touching a frozen path — a second line of defense reinforcing
   invariant 1 (`test_gate_policy_change_breaker`). ✔ Enforced.

2. **Asymmetric gate.** Unchanged and reinforced: a rejection streak
   (`consecutive_rejections`) and a proposed gate/policy change both halt the
   loop; nothing here can promote. ✔ Respected.

3. **Builder cannot attest.** Caution directives are explicitly `advisory` and
   `excluded_from_gate`; they shape only the *next* proposal, never a verdict
   (`test_context_is_advisory_and_gate_excluded`). ✔ Enforced.

4. **Append-only lineage.** *Central to this item.* The meta-ledger is
   hash-chained; edit/insert/reorder break `verify_chain`
   (`test_edit_breaks_chain`, `test_reorder_breaks_chain`); a broken chain trips
   the `chain_break` breaker. Rejections are inscribed with fingerprints and
   reasons; recurrence over the append-only ledger drives cautions and wither. ✔
   Enforced.

5. **Budgeted holdout.** The `holdout_budget_exhausted` breaker halts the loop
   when the metered holdout budget is spent
   (`test_holdout_budget_exhausted_breaker`), completing the Item-3 metering with
   a hard stop. ✔ Enforced.

6. **Determinism and offline CI.** Chaining, recurrence, breaker evaluation, and
   the sealed breaker report are pure functions; no wall-clock, network, or
   model. 25 tests + the demo run offline. ✔ Enforced.

## Halt requires human restart

A tripped breaker yields `requires_human_restart = true`; `clear_halt` refuses to
un-halt without a human restart token (`SFA_AUTOLAB_RESTART_TOKEN`) — no
autonomous restart (`test_halt_holds_without_token`,
`test_halt_cleared_only_by_human_token`).

## Verification run

- `python -m unittest discover -s tests` → all OK (25 new).
- `python meta_ledger_demo.py` → PASS.
- `python verify_all.py` → PASS (includes `meta_ledger_demo.py`).
- `python release_gate.py --ci` → PASS.
- `python frozen_zone_check.py` → attestation PASS at `fz-v0.5.0`.

## Merge-order note

Stacks on Items 1–4 (PRs #22–#25) and targets `main` (genesis → the frozen-zone
amendment gate passes without a token). After earlier items land, a rebase makes
the `fz-v0.5.0` bump a real amendment requiring
`SFA_FROZEN_ZONE_AMENDMENT_TOKEN=fz-v0.5.0-add-meta-ledger`.

## Conflicts encountered

None. No invariant was bent.

## Not in this item

Item 6 (docs/autolab.md scope map) and the version-of-record bump are the final
PR. Version stays `v1.1.0` here.
