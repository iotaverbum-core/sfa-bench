"""Causal linkage report over the taxonomy's typed causal-edge overlay.

The taxonomy (schema v2) carries typed directed causal edges A -> B between failure
families, on top of the parent/child tree. This report joins that structure with
occurrence-ledger recurrence so a researcher can ask: for a causal edge A -> B, as
the upstream family A is addressed, does the downstream family B recur less?

It is a deterministic, read-only function of the taxonomy and the hash-chained
ledger - it never writes, never calls a model. Recurrence is aggregated per family
*including its taxonomy descendants* (so a parent family rolls up its children),
then scored with the recurrence-decline metric. Part of the research core.
"""
from __future__ import annotations

from typing import Any

from . import recurrence_metric as rmetric
from .hashing import sha256_hex

REPORT_SCHEMA = "sfa.causal_linkage.v0"


def family_series(entries: list[dict[str, Any]], taxonomy, family: str, epochs: list[str]) -> list[int]:
    """Per-epoch occurrence counts for a family and all its taxonomy descendants."""
    included = {family} | set(taxonomy.descendants(family))
    index = {epoch: i for i, epoch in enumerate(epochs)}
    row = [0] * len(epochs)
    for entry in entries:
        if entry.get("family") in included:
            row[index[str(entry.get("period"))]] += 1
    return row


def _decline_score(row: list[int]) -> float | None:
    decline = rmetric.decline_of(row)
    return decline["decline_score"] if decline else None


def compute_linkage(taxonomy, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the sealed causal-linkage report for a taxonomy + occurrence ledger."""
    epochs = rmetric.epoch_axis(entries)

    endpoints: set[str] = set()
    for edge in taxonomy.edges():
        endpoints.add(edge["from"])
        endpoints.add(edge["to"])

    families: dict[str, Any] = {}
    for family in sorted(endpoints):
        row = family_series(entries, taxonomy, family, epochs)
        decline = rmetric.decline_of(row)
        families[family] = {
            "recurrence_series": row,
            "decline_score": decline["decline_score"] if decline else None,
            "eliminated": bool(decline["eliminated"]) if decline else False,
            "upstream": [{"family": src, "type": etype} for src, etype in taxonomy.causes(family)],
            "downstream": [{"family": dst, "type": etype} for dst, etype in taxonomy.effects(family)],
        }

    edge_rows = []
    for edge in taxonomy.edges():
        upstream = families[edge["from"]]
        downstream = families[edge["to"]]
        up_score = upstream["decline_score"]
        down_score = downstream["decline_score"]
        edge_rows.append({
            "from": edge["from"],
            "to": edge["to"],
            "type": edge["type"],
            "upstream_series": upstream["recurrence_series"],
            "downstream_series": downstream["recurrence_series"],
            "upstream_decline": up_score,
            "downstream_decline": down_score,
            # Both upstream and downstream recurrence fell from their peaks.
            "downstream_declines_with_upstream": bool(
                up_score is not None and down_score is not None
                and up_score > 0 and down_score > 0
            ),
        })

    report = {
        "schema": REPORT_SCHEMA,
        "taxonomy_schema_version": getattr(taxonomy, "schema_version", None),
        "epochs": epochs,
        "families": families,
        "edges": edge_rows,
    }
    report["report_hash"] = sha256_hex({k: v for k, v in report.items() if k != "report_hash"})
    return report
