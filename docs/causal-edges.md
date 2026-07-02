# Causal-Edge Taxonomy (Schema v2)

The failure taxonomy in `families.json` has always been a parent/child **tree**:
each family has one parent, and ancestry/depth/descendants are derived from it.
Schema v2 adds a second, independent structure on top: a **typed directed causal
overlay** of edges `A → B` between failure families, so the taxonomy can express
*"failure A tends to lead to failure B,"* not only *"B is a kind of A."*

This is part of the research core, not the GroundLedger product layer.

## Schema versions and backward compatibility

`families.json` now declares a `taxonomy_schema_version`:

- `sfa.taxonomy_schema.v1` — families only (the historical shape). A v1 file has no
  `edges` key.
- `sfa.taxonomy_schema.v2` — families **plus** an `edges` list.

The loader is backward compatible: a v1 file (no `edges`) loads as an empty edge
set, and a file with no `taxonomy_schema_version` is treated as v1. Existing
artifacts, the ledger, and the fingerprint demo are unaffected — the family-set
(`taxonomy_version`) is unchanged and edges never alter classification.

### Migration

`families.migrate_to_v2(data, edges=None)` upgrades a v1 taxonomy dict to v2 by
setting the schema version and attaching edges. It is idempotent (re-migrating a v2
file preserves its edges) and never alters families. It validates the result, so a
migration that would introduce an unknown endpoint, self-loop, duplicate, or cycle
fails loudly.

## Edge shape and validation

Each edge is a typed directed relation:

```json
{ "from": "unsupported_claim", "to": "contradicts_evidence", "type": "escalates_to" }
```

At load time the `Taxonomy` validates the overlay:

- every `from`/`to` must be a known family;
- no self-loops (`from == to`);
- no duplicate edges;
- the directed edge graph must be a **DAG** — a cycle raises `ValueError`.

The parent/child tree and the causal overlay are independent graphs; the DAG check
applies only to the causal edges.

### Current edges

```
unsupported_claim  --escalates_to-->  contradicts_evidence  --causes-->  deferred_consequence_stale
```

- `unsupported_claim → contradicts_evidence` (`escalates_to`): an unsupported claim
  can harden into a direct contradiction of the evidence.
- `contradicts_evidence → deferred_consequence_stale` (`causes`): the item-2
  deferred-consequence stale failure is verified *as* a contradiction of the
  propagated fact, so the general contradiction mode is its upstream cause.

## Query API

`Taxonomy` (schema v2) exposes:

- `edges()` — the sorted list of `{from, to, type}` edges.
- `causes(family)` — direct upstream `(source, type)` pairs (who points at this).
- `effects(family)` — direct downstream `(target, type)` pairs (what this points at).
- `edge_type(a, b)` — the type of edge `a → b`, or `None`.
- `has_edges()` — whether any causal edges are declared.

## Upstream/downstream recurrence linkage report

`sfa/causal_report.py` joins the causal overlay with occurrence-ledger recurrence.
For each edge `A → B` it computes the recurrence-decline of `A` and `B` (each
aggregated over the family **and its taxonomy descendants**, reusing the
[recurrence-decline metric](recurrence-decline.md)) and reports whether the
downstream family declines as the upstream family is addressed.

Over the illustrative fixture `examples/causal/causal_ledger.jsonl` (epochs
`2024/2025/2026`):

| Family (with descendants) | series | decline | upstream → downstream |
| --- | --- | --- | --- |
| `unsupported_claim` | `3, 2, 0` | 1.00 (eliminated) | — → `contradicts_evidence` |
| `contradicts_evidence` | `4, 2, 1` | 0.75 | `unsupported_claim` → `deferred_consequence_stale` |
| `deferred_consequence_stale` | `2, 1, 1` | 0.50 | `contradicts_evidence` → — |

| Edge | upstream decline | downstream decline | tracks |
| --- | --- | --- | --- |
| `unsupported_claim → contradicts_evidence` | 1.00 | 0.75 | yes |
| `contradicts_evidence → deferred_consequence_stale` | 0.75 | 0.50 | yes |

Downstream recurrence declines as its upstream cause is addressed — a continual-
learning signal that follows the causal structure. The report is sealed with a
`report_hash` and is a pure, deterministic function of the taxonomy and the ledger.

## CLI

```bash
python causal_report.py                              # score the causal fixture + self-check
python causal_report.py --ledger history/occurrences.jsonl
```

The default run loads the v2 taxonomy, links it with the causal fixture ledger, and
prints per-family recurrence with upstream/downstream neighbours and per-edge
linkage — offline, with no model call.
