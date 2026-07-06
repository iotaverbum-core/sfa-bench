# AutoLab Meta-ledger + Circuit Breakers (Item 5)

The meta-ledger is an append-only, hash-chained record of AutoLab events one
level above the occurrence ledger: proposals, rejections, promotions, rollbacks,
and halts. Circuit breakers put the loop into **halt-and-hold** on dangerous
conditions, and a halt can only be cleared by a **human restart**.

`autolab/meta_ledger.py` is **frozen** (invariant 1/4; amendment `fz-v0.5.0`).

## The meta-ledger

Each event carries a **patch fingerprint**, an event kind, the `loop_hash`, a
`lineage_id`, and (for rejections) the gate reasons. Entries are chained
(`prev_hash`/`entry_hash`) exactly like `sfa/ledger.py`, so deleting, inserting,
reordering, or editing an event breaks `verify_chain`. `inscribe_from_loop`
records a gate-green iteration as `proposed` and a rejected one as `rejected`
with its reasons.

## Recurrence-fed caution directives + wither

Recurrence over the ledger drives **caution directives** for the *next* proposal
context:

- A lineage rejected at least once earns a **caution** listing its known failure
  reasons.
- A lineage rejected **K times withers** (`DEFAULT_WITHER_K = 3`): its directive
  becomes **TERMINAL — do not re-propose**. Wither is terminal; there is no
  un-wither.

`next_proposal_context(entries)` returns `{advisory: true, excluded_from_gate:
true, cautions: [...], withered_lineages: [...]}`. These directives are
**advisory** — they shape the next proposal but **never enter the gate**
(invariant 3).

## Circuit breakers (halt-and-hold)

`evaluate_breakers(BreakerContext)` trips on any of six conditions; any trip
means `halted = true`:

| Breaker | Trips when |
| --- | --- |
| `zone_hash_mismatch` | the frozen-zone attestation does not match the manifest |
| `chain_break` | the meta-ledger hash chain is broken |
| `holdout_budget_exhausted` | the holdout exposure budget is spent |
| `consecutive_rejections` | ≥ N rejections in a row (default 3) |
| `gate_policy_change_proposed` | a proposed diff touches any frozen-zone path |
| `cost_time_budget_exceeded` | cost or time exceeds its budget |

The report is deterministic and sealed with a `report_hash`.

## Halt requires a human restart

A halt yields a `HaltState` with `requires_human_restart = true`. `clear_halt`
returns *still halted* unless a human restart token
(`SFA_AUTOLAB_RESTART_TOKEN`) is supplied — the loop cannot un-halt itself. There
is no autonomous restart path.

## CLI / tests

```bash
python meta_ledger_demo.py     # ledger + wither + all six breakers + halt/restart
```

`tests/test_meta_ledger.py` unit-tests each breaker against a fixture (and that a
clean context does not halt), the terminal wither of a K-fail lineage, the
append-only chain (edit/reorder detection), the advisory caution context, and
the human-restart-only halt clearance.

## How it closes the loop

The caution context feeds the controller's *next* proposal (advisory config,
excluded from the gate). The breakers wrap an iteration: a zone drift, a broken
chain, an exhausted holdout, a rejection streak, a proposed gate/policy change,
or a blown budget all halt the loop until a human restarts it — the safety
envelope around the self-improvement loop.
