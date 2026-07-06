# Checkpoint — AutoLab Item 4: Promotion / rollback

Scope: tagged states, a human-token promotion path, a tested rollback restoring
the incumbent bit-exact, and an anchor suite pinned at v-root.

## Deliverables

- `autolab/promotion.py` — tagged `State`, `promote` (gate-green + human-token,
  asymmetric), `rollback` (bit-exact), append-only hash-chained `Lineage`,
  `promote_rollback_round_trip` + `replay_round_trip` (**frozen** via amendment
  `fz-v0.4.0`).
- `promotion_demo.py` — refusals + authorized round trip + replay (added to
  `verify_all.py`).
- `tests/test_promotion.py` — 17 deterministic tests.
- `autolab/frozen_manifest.json` → `fz-v0.4.0` (15 frozen files);
  `autolab/amendments/fz-v0.4.0-add-promotion.json` records the
  `7edfb561… → 410db5b2…` transition.
- `docs/autolab-promotion-rollback.md`.

## Acceptance criteria

- **promote → rollback → replay round-trip test.** `promote_rollback_round_trip`
  runs `root → promote → rollback`; `replay_round_trip` re-derives it
  byte-for-byte and re-checks the bit-exact restore
  (`test_round_trip_restores_and_replays`, `test_round_trip_is_deterministic`).
- **Rollback restores the incumbent bit-exact** — `restores_bit_exact` and the
  restored `state_hash` equals the incumbent's (`test_rollback_restores_
  incumbent_bit_exact`).
- **Anchor pinned at v-root** — every tagged state carries `anchor_tag ==
  "v-root"` (`test_anchor_never_moves`, `test_promotion_pins_anchor_and_links_
  parent`).

## The six hard invariants — explicit accounting

1. **Frozen zone.** `autolab/promotion.py` is added to the zone (amendment
   `fz-v0.4.0`). ✔ Enforced.

2. **Asymmetric gate.** *Central to this item.* `promote` is refused unless the
   loop record is **gate-green** AND an explicit **human token** is supplied
   (optionally an authorization binding the `loop_hash`); it also refuses a loop
   record that claims self-promotion. Promotion can only fail, never happen by
   default — there is no tokenless promotion path
   (`test_promotion_refused_without_token`, `test_promotion_refused_with_red_gate`,
   `test_promotion_refused_if_loop_claims_self_promotion`). ✔ Enforced.

3. **Builder cannot attest.** Promotion consumes only the frozen-evaluator gate
   verdict (`loop_record["gate"]["gate_green"]`) and human authority. No
   builder-supplied field influences whether a promotion is allowed. ✔ Respected.

4. **Append-only lineage.** *Central to this item.* Tagged states are hash-chained
   into an append-only `Lineage`; **rollback is a first-class tagged, replayable
   operation** that adds a new event rather than mutating history and is covered
   by a round-trip replay test (`test_lineage_is_hash_chained`,
   `test_rollback_is_tagged_event`). ✔ Enforced.

5. **Budgeted holdout.** Not exercised here; unchanged. The anchor pinned at
   v-root keeps the original holdout baseline in view across promotions. ✔
   Respected.

6. **Determinism and offline CI.** `promote`, `rollback`, and the round trip are
   pure functions; canonical hashes seal states and the lineage; no wall-clock,
   network, model, or randomness. 17 tests + the demo run offline; the round trip
   replays byte-identically. ✔ Enforced.

## Verification run

- `python -m unittest discover -s tests` → all OK (17 new).
- `python promotion_demo.py` → PASS.
- `python verify_all.py` → PASS (includes `promotion_demo.py`).
- `python release_gate.py --ci` → PASS.
- `python frozen_zone_check.py` → attestation PASS at `fz-v0.4.0`.

## Merge-order note

Stacks on Items 1–3 (PRs #22–#24) and targets `main` (genesis → the frozen-zone
amendment gate passes without a token). After earlier items land, a rebase makes
the `fz-v0.4.0` bump a real amendment requiring
`SFA_FROZEN_ZONE_AMENDMENT_TOKEN=fz-v0.4.0-add-promotion`.

## Conflicts encountered

None. No invariant was bent.

## Not in this item

The persisted meta-ledger (inscribing promotions/rejections across iterations)
and the circuit breakers are Item 5. Version of record stays `v1.1.0`.
