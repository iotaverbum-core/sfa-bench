# AutoLab Lineage + Rollback (Item 5)

Item 5 is the promotion-history boundary. Item 4 can append a
`human_ratification` event; Item 5 requires that event to be explicitly
inscribed before it becomes the current promoted target. Rollback is the same
kind of append-only transition: a sealed human rollback record plus a matching
rollback token appends `rollback_inscribed` to the meta-ledger.

`autolab/lineage.py` is frozen-zone promotion-history policy (manifest
`fz-v0.5.0`). The loop cannot rewrite it without a frozen-zone amendment token.

## Promotion Inscription

`append_promotion_inscription(...)` takes a meta-ledger entry hash that must
refer to an existing `human_ratification` event. It refuses builder-completed
events, self-reported target refs, and rejected promotions. The inscribed record
binds:

- the `human_ratification` entry hash;
- the promoted `target_ref`;
- the target's canonical `target_key`;
- the previous current ref, when one exists;
- the ratification hash and reviewer metadata copied from the human record.

Only a `promotion_inscribed` event advances the derived lineage state. A builder
can still propose a target, but it cannot make that target current.

## Rollback

Rollback does not delete the promotion. It appends a new event:

```json
{
  "schema": "sfa.autolab.rollback.v0",
  "rollback_id": "rollback-lineage-demo-0001",
  "target_ref": { "type": "git_commit", "sha": "<promoted target>" },
  "target_key": "<sha256 of target_ref>",
  "restore_ref": { "type": "git_commit", "sha": "<reviewed restore ref>" },
  "restore_key": "<sha256 of restore_ref>",
  "human_reviewer": "human-reviewer",
  "reason": "Restore the last reviewed baseline.",
  "rollback_hash": "<sha256 of the record minus this field>"
}
```

`append_rollback(...)` recomputes the rollback seal, checks that the rollback
target is the current lineage target, and then requires a matching
`SFA_AUTOLAB_ROLLBACK_TOKEN` or explicit `rollback_token`. The demo uses
`rollback_id` as the token value. Rejected rollback attempts append nothing.

## Derived State

`derive_lineage_state(ledger_path)` verifies the Item 3 meta-ledger hash chain
and then replays only lineage events:

- `promotion_inscribed` sets the current target to the promoted `target_ref`;
- `rollback_inscribed` moves the current target to the rollback `restore_ref`;
- missing, edited, reordered, or deleted entries are caught by the meta-ledger
  verification before state is derived.

The state is deterministic and can be rederived from the ledger alone.

## CLI / Demo

```bash
python lineage_demo.py
```

The demo appends a human-ratified promotion, inscribes it as current, rejects a
rollback without the human token, then appends a token-authorized rollback and
rederives the restored current ref.

Tests live in `tests/test_autolab_lineage.py`.
