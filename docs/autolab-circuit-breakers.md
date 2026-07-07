# AutoLab Circuit Breakers (Item 6)

Item 6 is the halt-and-hold boundary around the AutoLab loop. Items 3-5 record
controlled iterations, human ratification, and append-only lineage; Item 6
decides when the loop must stop before another proposal can run.

`autolab/circuit_breakers.py` is frozen-zone safety policy (manifest
`fz-v0.6.0`). The loop cannot rewrite it without a frozen-zone amendment token.

## Breaker Report

`evaluate_breakers(...)` returns a sealed deterministic report. It evaluates:

- frozen-zone attestation drift or expected-zone mismatch;
- controller meta-ledger chain break;
- exhausted holdout budget receipts;
- too many consecutive rejection events;
- proposed changes touching frozen paths;
- cost or time budget overrun;
- re-proposal of a withered lineage.

The report is a pure function of repository bytes, meta-ledger entries, explicit
inputs, and numeric budget counters. It performs no network, model, clock, or
random operation.

## Halt Event

`append_halt(...)` appends `autolab_halted` to the Item 3 controller meta-ledger
only when the breaker report is sealed and `halted=true`. It refuses duplicate
halts while an active halt is already present.

If the meta-ledger chain itself is broken, the report can still identify
`chain_break`, but a new halt cannot be appended to the damaged ledger. That is
intentional: a broken append-only ledger must be handled out of band by a human.

## Restart Clearance

Restart is not automatic. `append_restart_clearance(...)` requires:

- a sealed `sfa.autolab.restart_clearance.v0` record;
- a matching out-of-loop human token (`SFA_AUTOLAB_RESTART_TOKEN` or explicit
  `restart_token`);
- a clearance record bound to the currently active halt entry hash.

Accepted restart appends `autolab_restart_authorized`. Rejected clearances append
nothing.

## Wither Directives

Repeated rejection of the same `lineage_id` produces caution directives. Once a
lineage reaches the configured threshold it is marked withered: a terminal
do-not-re-propose directive for that lineage. These directives are marked
`advisory=true` and `excluded_from_gate=true`; they may shape the next proposal
context but never participate in the deterministic gate verdict.

## CLI / Demo

```bash
python circuit_breakers_demo.py
```

The demo shows a clean context, trips a frozen-path-change breaker, appends a
halt, rejects a restart without a token, and appends a token-authorized restart.

Tests live in `tests/test_autolab_circuit_breakers.py`.
