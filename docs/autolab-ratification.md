# AutoLab Human Ratification (Item 4)

Item 4 is the promotion boundary. A deterministic gate-green result is necessary
but not sufficient: a candidate may be promoted only when a human approval record
is sealed and a matching human token is supplied outside the loop.

`autolab/ratification.py` is frozen-zone promotion policy, added in manifest
`fz-v0.4.0` and still frozen in the current manifest. The loop cannot rewrite
it without a frozen-zone amendment token.

## Promotion Inputs

`evaluate_promotion(declaration, report, ratification, ratification_token=...)`
recomputes the Item 2 gate from the sealed declaration/report and then checks a
sealed ratification record:

```json
{
  "schema": "sfa.autolab.human_ratification.v0",
  "ratification_id": "ratify-demo-0001",
  "decision": "approve",
  "declaration_hash": "<bound declaration hash>",
  "report_hash": "<bound report hash>",
  "gate_decision_hash": "<hash of the recomputed gate decision>",
  "target_ref": { "type": "git_commit", "sha": "<candidate commit>" },
  "human_reviewer": "human-reviewer",
  "rationale": "Reviewed target ref and gate output.",
  "ratification_hash": "<sha256 of the record minus this field>"
}
```

The token is an out-of-loop human input. For the deterministic demo it is the
ratification id; production CI or a protected runner would supply it through
`SFA_AUTOLAB_RATIFICATION_TOKEN` or an explicit argument. The builder cannot set
or infer this token through report content.

## Rejection Paths

Promotion is rejected when:

- the deterministic gate is red;
- the human token is missing or does not match `ratification_id`;
- the human decision is not `approve`;
- the record binds a different declaration, report, or gate-decision hash;
- the ratification record has been edited after sealing.

The builder's rationale and self-reported booleans remain irrelevant because the
gate decision is recomputed from raw report numbers before promotion is
considered.

## Meta-ledger Event

`append_promotion(...)` appends `human_ratification` to the Item 3 meta-ledger
only after `evaluate_promotion` returns `promoted=true`. Rejected promotions do
not append anything. The meta-ledger hash chain continues to detect deletion,
insertion, reordering, or edits.

Item 5 consumes this event through `append_promotion_inscription(...)`: a
human-ratified target is not considered current lineage until the separate
`promotion_inscribed` event is appended.

## CLI / Demo

```bash
python ratification_demo.py
```

The demo shows three cases: gate-green without a token (rejected), gate-green
with the matching token (promoted), and gate-red with the token (rejected). It
also appends one successful `human_ratification` event to a temporary
meta-ledger.

Tests live in `tests/test_autolab_ratification.py`.
