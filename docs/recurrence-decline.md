# Recurrence-Decline Metric (Continual-Learning Score)

The recurrence-decline metric asks a continual-learning question of the
append-only occurrence ledger: **does each failure fingerprint recur less over
time?** A system that truly learns from a sealed failure — surfaces it, matures a
lesson, and applies that lesson — should drive the fingerprint's recurrence rate
down across successive epochs and eventually to zero. This module turns that into
a deterministic score.

It is a **pure function of the hash-chained ledger** and the taxonomy identity
already sealed into each entry. It never writes, never calls a model, and never
consults a verdict beyond what the ledger recorded. It is part of the research
core, not the GroundLedger product layer.

## Inputs

- **Epoch** — the ledger's own time bucket, `entry["period"]` (already part of the
  sealed hash chain). Epochs sort lexically, so ISO date prefixes order by time.
- **Fingerprint** — a recurring-failure identity. The default is the failure
  `family`; any callable `key(entry) -> str` can be supplied (for example, to key
  by `(model_id, family)`).

The metric only trusts an intact chain: `compute_from_path` attests the ledger
with `ledger.verify_chain` first and raises `RecurrenceMetricError` on any
deletion, insertion, reorder, or edit before scoring.

## The metric

For each fingerprint `f`, over the global ordered epoch axis
`E = [e_0, …, e_{m-1}]`, the **recurrence series** is

```
r_f = [ c_f(e_0), c_f(e_1), …, c_f(e_{m-1}) ]
```

where `c_f(e)` counts occurrences of `f` in epoch `e`. Epochs where `f` is absent
are `0`, which is what makes a decline *to zero* observable.

Let `first` be the index of the first epoch where `f` appears, and take the tail
`W = r_f[first:]` with `peak = max(W)` and `final = W[-1]`. The **decline score**
is

```
decline_score(f) = (peak - final) / peak            ∈ [0, 1]
```

- `1.0` — the fingerprint was driven from its worst epoch down to zero by the
  final epoch (**eliminated**).
- `0.0` — the fingerprint is still at its peak in the final epoch (no learning).

Two flags characterise the trajectory shape:

- `eliminated` — `final == 0` (the fingerprint did not recur in the last epoch).
- `monotone_post_peak` — the series is non-increasing from its peak onward. A
  fingerprint that goes quiet and then **comes back** is non-monotone, and its
  `final > 0` keeps its decline score low.

### Aggregates

- `continual_learning_score` — the mean decline score across fingerprints.
- `occurrence_weighted_score` — the peak-weighted mean, emphasising the worst
  (highest-peak) offenders.
- `eliminated_fingerprints` — the sorted list of fingerprints with `final == 0`.

The report is sealed with a `metric_hash` over its canonical JSON, so the same
ledger always produces the same score, byte-for-byte.

> The metric is meaningful for ledgers spanning at least two epochs; with a single
> epoch every decline score is `0` by construction (nothing can decline yet).

## Worked example (the synthetic fixture)

`examples/recurrence/synthetic_ledger.jsonl` is an illustrative 17-entry ledger
(a valid hash chain) spanning epochs `2024`, `2025`, `2026`:

| Fingerprint | series | peak | final | decline | eliminated | monotone |
| --- | --- | --- | --- | --- | --- | --- |
| `contradicts_evidence` | `3, 1, 0` | 3 | 0 | **1.000** | yes | yes |
| `fabricated_entity` | `0, 2, 1` | 2 | 1 | 0.500 | no | yes |
| `missing_required_field` | `2, 0, 2` | 2 | 2 | 0.000 | no | no |
| `unsupported_number` | `1, 2, 3` | 3 | 3 | 0.000 | no | yes |

- `contradicts_evidence` climbs then is fully eliminated → decline `1.0`.
- `fabricated_entity` appears late and halves → decline `0.5`.
- `missing_required_field` recurs after a silent epoch → decline `0.0`, not
  monotone.
- `unsupported_number` grows → decline `0.0` (no reduction from peak).

Aggregates: `continual_learning_score = mean(1.0, 0.5, 0.0, 0.0) = 0.375`;
`occurrence_weighted_score = (1.0·3 + 0.5·2 + 0.0·2 + 0.0·3) / (3+2+2+3) = 0.4`;
`eliminated_fingerprints = ["contradicts_evidence"]`.

These exact values are pinned by the offline invariant suite as the metric's unit
test, which also confirms byte-identical recomputation and that a tampered ledger
chain is refused.

## CLI

```bash
python recurrence_metric.py                       # score the synthetic fixture + self-check
python recurrence_metric.py --ledger history/occurrences.jsonl
python recurrence_metric.py --ledger my.jsonl --no-verify
```

The default run scores the committed fixture, prints the per-fingerprint series
and aggregate scores, and self-checks determinism and the expected values —
entirely offline, with no model call.
