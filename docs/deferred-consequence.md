# Deferred-Consequence Task Family

The deferred-consequence family is a research-core probe for a specific reasoning
failure: **failing to propagate an update through a deferred consequence**. It is
the HOP3-03-class case — an episode establishes a premise whose consequence binds
only later, an update changes the premise in between, and the correct answer at
the horizon requires carrying the change forward.

This document describes the logical core, the surface skins, horizon
parameterisation, the sealed case format, deterministic scoring, and how the
family is registered for fingerprint support. It is part of the research
instrument, not the GroundLedger product layer.

## The logical core

Every case shares one invariant structure over a tracked quantity `X` (the
*consequence variable*):

1. **Premise at `T`.** `X = v0`.
2. **Update at `T+u`** (`1 ≤ u ≤ k`). `X := v1`, with `v1 ≠ v0`.
3. **Distractors** fill the remaining offsets `1..k` and never touch `X`.
4. **Query at `T+k`.** "What is the current value of `X`?"

Because the update at `T+u` (with `u ≤ k`) is the last event that binds `X`, the
correct answer at the horizon is the propagated value **`v1`**. The
**characteristic failure** is preserving the stale premise value **`v0`** — the
model reads the premise, misses or fails to carry the update, and answers `v0`.

## Surface skins

The same core is rendered over four rotating skins, so a proposer cannot succeed
by memorising surface wording. Skins alternate between a numeric value domain and
a categorical/status domain:

| Skin | Subject | Domain |
| --- | --- | --- |
| `inventory` | `units_in_stock` | numeric |
| `ledger_balance` | `balance` | numeric |
| `access_policy` | `access_level` | status (`read_only`…`suspended`) |
| `document_status` | `review_status` | status (`draft`…`archived`) |

Numeric skins draw `v0 ∈ [100, 900]` and a signed delta `∈ [1, 99]`, so `v1` is a
distinct positive value. Status skins pick two distinct pool members. All draws
are deterministic (see below).

## Horizon `k`

The horizon is parameterised; the default pack covers `k ∈ {1, 3, 5}`:

- `k = 1` — premise at `T`, a single binding update at `T+1`, query at `T+1`.
- `k = 3` — premise, one update at some `T+u` (`u ∈ {1,2,3}`), two distractors.
- `k = 5` — premise, one update, four distractors.

Larger `k` widens the gap the update must be carried across and adds distractor
pressure, while the correct answer stays `v1`.

## Determinism

All content — reference codes, `v0`/`v1`, the update offset `u`, and skin
selection — is derived from a single integer `seed` via SHA-256 of the case
coordinates `(skin, k, replicate)`. No `random` module and no wall-clock time
enter a case, so `generate_pack(config)` is a pure function of its config and
seals byte-for-byte across machines. Each case carries a `case_hash`; the pack
chains cases (`prev_hash` → `chain_hash`) and seals a `pack_hash`. `replay(pack)`
re-derives the pack from its sealed config and confirms the `pack_hash` and
`cases_root_hash` are byte-identical. A determinism check is enforced by the
offline invariant suite.

## Sealed case format

Each case separates the proposer-facing view from the verifier-side scoring
bundle:

```json
{
  "schema": "sfa.deferred_consequence_case.v0",
  "case_id": "dc_inventory_k1_r00",
  "task_family": "deferred_consequence",
  "skin": "inventory",
  "horizon_k": 1,
  "update_offset": 1,
  "subject": "units_in_stock",
  "reference": "6761",
  "proposer_view": {
    "task": "Read the episodes in order and report the current value ...",
    "episodes": [
      {"offset": 0, "episode": "T",   "kind": "premise", "text": "... 867 units ..."},
      {"offset": 1, "episode": "T+1", "kind": "update",  "text": "... 786 units ..."}
    ],
    "query": "After all episodes above, how many units_in_stock ...?",
    "answer_subject": "units_in_stock"
  },
  "scoring": {
    "input": {"case_id": "dc_inventory_k1_r00", "question": "..."},
    "scoring_evidence": {"facts": [{"id": "x1", "subject": "units_in_stock", "value": 786}],
                         "task_family": "deferred_consequence"},
    "rules": { "...": "claims_match_evidence on facts" },
    "correct_value": 786,
    "stale_value": 867
  },
  "case_hash": "..."
}
```

### Gold isolation

`proposer_view(case)` returns only `task`, `episodes`, `query`, and
`answer_subject` — never the labelled scoring fact, the rules, or the
correct/stale values as answers. The gold-bearing `scoring_evidence` (the
propagated final value) lives in the verifier-side `scoring` bundle and is never
handed to a proposer.

The update episode *does* narrate the new value in prose — that is the task
input, from which the answer must be **derived**. What is isolated is the
*verdict logic*: the labelled ground-truth fact and the correct/stale mapping.
`proposer_view_is_gold_isolated(case)` enforces that no structured scoring
material (`facts`, `scoring_evidence`, `rules`, `claims`, `correct_value`,
`stale_value`) leaks into the proposer view.

## Deterministic scoring (zero LLM)

Scoring reuses the fixed SFA verifier. A candidate is
`{"claims": [{"subject": subject, "value": answer}]}`, scored by
`verifier.verify(input, scoring_evidence, candidate, rules)` under a single
`claims_match_evidence` rule:

- **Propagated answer** (`value = v1`) → matches the scoring fact → **PASS**.
- **Stale answer** (`value = v0`) → contradicts the scoring fact →
  **FAIL / `CONTRADICTS_EVIDENCE`**.

No LLM output participates in the verdict; the verdict is a pure deterministic
function of the sealed inputs. This is the same proposer/verifier separation the
rest of the research core enforces — a proposer (or live model) may produce the
candidate, but only the verifier decides accept/reject.

## Fingerprint support and family registration

The characteristic failure is registered in the failure taxonomy
(`families.json`) as two additive leaves:

```
deferred_consequence            (root)
└── deferred_consequence_stale  (the characteristic stale-value failure)
```

`classify_family` refines a `CONTRADICTS_EVIDENCE` verdict to
`deferred_consequence_stale` **only** when the scoring evidence is marked
`task_family == "deferred_consequence"`. This is a backward-compatible extension:
evidence without that marker classifies exactly as before, so existing artifacts,
ledger entries, and the fingerprint demo re-derive byte-for-byte unchanged. The
families are added additively; the taxonomy family-set is a superset of the prior
one, and formal taxonomy schema versioning/migration is handled separately.

`stale_occurrences(pack)` scores the stale candidate for every case and emits
occurrence records carrying `family = "deferred_consequence_stale"`, ready for the
fingerprint and recurrence-tracking machinery.

## CLI

```bash
python deferred_consequence.py                       # generate + determinism + scoring demo
python deferred_consequence.py --seed 20260301 --per-cell 2 --out pack.json
python deferred_consequence.py replay pack.json      # offline deterministic replay
```

The default run generates the `{1,3,5} × 4-skin` pack, checks determinism and
replay, and demonstrates that every propagated answer passes and every stale
answer fails as `deferred_consequence_stale` — entirely offline, with no model
call.
