# AutoLab Promotion / Rollback (Item 4)

Promotion is the **only** operation that turns a candidate into the incumbent,
and it is deliberately not autonomous. Rollback is a first-class, tagged,
replayable operation that restores the previous incumbent **bit-exact**.

`autolab/promotion.py` is **frozen** (invariant 1; amendment `fz-v0.4.0`).

## Human-token promotion path

`promote(incumbent, loop_record, candidate_payload, *, human_token, authorization=None)`
requires **both**:

1. a deterministically **gate-green** loop record (from Item 3), and
2. an explicit **human promotion token** (`SFA_PROMOTION_TOKEN`) — an out-of-loop
   authority the automated builder cannot produce. An optional `authorization`
   record binds the token to the exact `loop_hash`.

If the gate is not green, if the loop record already claims promotion (the loop
may never self-promote), or if the token is missing/mismatched, promotion is
**refused** (`PromotionError`). Promotion is asymmetric — it can only fail, never
happen "by default." There is no code path that promotes without a token.

## Tagged states and the pinned anchor

A `State` is a tagged scaffold version: `tag`, `parent_tag`, `anchor_tag`,
`sequence`, `origin` (`root` / `promotion` / `rollback`), `state_hash` (a
bit-exact content hash of `payload`), and the `loop_hash` that produced it.

- `make_root_state(payload)` is the pinned **v-root** incumbent; its tag *is* the
  anchor.
- The **anchor is pinned at `v-root`** and never moves. Every state carries
  `anchor_tag == "v-root"`, so the ancestor-anchor comparison in the loop always
  keeps the original baseline in view even as the incumbent advances.

## Rollback restores bit-exact

`rollback(current, restore_to)` returns a new tagged rollback event whose
`payload` and `state_hash` equal `restore_to`'s exactly. `restores_bit_exact`
verifies the restored content hashes identically to the incumbent. Rollback is
append-only: it adds a new tag/sequence rather than mutating history (invariant 4).

## Append-only lineage + round trip

`Lineage` hash-chains each tagged state (`prev_hash`/`entry_hash`) like the
occurrence ledger. `promote_rollback_round_trip(root_payload, loop_record,
candidate_payload, human_token=…)` runs `root → promote → rollback`, seals the
three states and the lineage, and flags bit-exact restoration. It is a pure
function, so `replay_round_trip(...)` re-derives it byte-for-byte and re-checks
the bit-exact restore — the **promote → rollback → replay round-trip** acceptance
test.

## CLI / tests

```bash
python promotion_demo.py     # refusals + authorized round trip + replay
```

`tests/test_promotion.py` covers the refusal guards (no token, red gate,
self-promotion, wrong authorization), tagged-state anchoring, bit-exact rollback,
the hash-chained lineage, and the deterministic round-trip replay.

## What is and isn't here

The persisted meta-ledger that inscribes promotions/rejections across iterations,
and the circuit breakers (including a rollback triggered by a broken chain), are
Item 5. This item provides the tagged-state model, the human-token path, and the
replayable rollback they build on.
