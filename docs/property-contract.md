# Property-Based Verifier Contract (Gold-Absent Tasks)

The core SFA verifier decides accept/reject by comparing a candidate against
**gold** evidence facts. Some tasks have no gold answer to store — yet their
correctness is still a **decidable property** of the candidate and the sealed task
structure. The property contract is that gold-absent verdict path: a versioned,
sealed set of decidable properties whose **deterministic conjunction** is the
verdict.

It is a sibling of the fixed verifier, not a change to it (`sfa/verifier.py` is
untouched). It is part of the research core, not the GroundLedger product layer.

## Why gold-absent

For a gold-bearing task you store the answer and compare. For a gold-absent task
you cannot — but you can still decide correctness from properties that do not
require knowing a stored answer:

- Is the candidate **well-formed**? (schema validity)
- Does it cite only things that **exist**? (citation grounding)
- Is it **self-consistent**? (internal consistency)
- Does it **preserve a stated invariant** of the task? (invariant preservation)

The correctness criterion lives in the **property definitions**, which are sealed
and versioned. Per the gold-isolation invariant generalised to gold-absent tasks:
the property definitions are sealed and the verdict logic never leaks into a
proposer prompt.

## Decidable property families

| Family | Decides |
| --- | --- |
| `schema_validity` | required fields are present and correctly typed |
| `citation_grounding` | every cited id exists in the evaluation context |
| `internal_consistency` | no subject is asserted as two different values |
| `invariant_preservation` | a named domain invariant holds |

Shipped invariants for `invariant_preservation`:

- `temporal_recency` — the reported value equals the value of the **latest update**
  episode in the sealed timeline. This decides the deferred-consequence family
  *without a gold label*: correctness is derived from the task's own timeline
  structure.
- `value_admissibility` — the reported value is one that actually appears in the
  timeline (the answer is not fabricated).

Each property is a pure, deterministic predicate `(candidate, context, params) ->
(holds, detail)`. No LLM output participates in any verdict.

## Contract and verdict

`build_contract` produces a versioned, sealed contract:

```json
{
  "schema": "sfa.property_contract.v0",
  "contract_version": "sfa.property_contract.v0",
  "contract_id": "dc_inventory_k1_r00_contract",
  "task_family": "deferred_consequence",
  "conjunction": "all",
  "properties": [
    {"id": "schema",      "family": "schema_validity",        "params": {"required": {"claims": "list"}}},
    {"id": "consistency", "family": "internal_consistency",   "params": {"...": "..."}},
    {"id": "admissible",  "family": "invariant_preservation", "params": {"invariant": "value_admissibility", "...": "..."}},
    {"id": "recency",     "family": "invariant_preservation", "params": {"invariant": "temporal_recency", "...": "..."}}
  ],
  "contract_hash": "..."
}
```

`evaluate(contract, candidate, context)` runs every property and returns a sealed
verdict. The **conjunction is `all`**: the verdict is `PASS` iff every property
holds; otherwise `FAIL` with the list of `failed_properties`. Both the contract
and each verdict are hashed, so the same contract + candidate + context yields a
byte-identical verdict.

## Wiring the deferred-consequence family (item 2)

The deferred-consequence task family gains a gold-absent scoring path alongside
its gold map:

- `property_context(case)` builds the verifier-side structured **timeline**
  (premise value at `T`, update value at `T+u`) from the sealed case data. This is
  never part of the proposer view.
- `property_contract(case)` builds the sealed contract (`schema`, `consistency`,
  `admissible`, `recency`).
- `score_candidate_by_contract(case, candidate)` evaluates it.

The `temporal_recency` property decides correctness from the timeline — no stored
gold answer:

| Candidate | Verdict | Failed properties |
| --- | --- | --- |
| propagated answer (`v1`) | **PASS** | — |
| stale answer (`v0`) | FAIL | `recency` |
| fabricated value | FAIL | `admissible`, `recency` |
| self-contradictory | FAIL | `consistency`, `recency` |
| malformed (`claims` not a list) | FAIL | `schema`, `consistency`, `admissible`, `recency` |

These verdicts are pinned by the offline invariant suite, which also confirms
deterministic conjunction, byte-identical sealing, and coverage of all four
decidable property families.

## CLI

```bash
python property_contract.py
```

The demo builds the deferred-consequence contract, evaluates the correct answer
and each characteristic failure, and self-checks determinism and the expected
gold-absent accept/reject — entirely offline, with no model call.
