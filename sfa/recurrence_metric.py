"""Recurrence-rate decline metric (continual-learning score).

A system that genuinely learns from its failures should show a *declining*
recurrence rate for each failure fingerprint over successive ledger epochs: once a
failure is observed and its lesson matured, that fingerprint should recur less and
eventually stop. This module turns that intuition into a deterministic score.

It is a **pure function of the append-only, hash-chained occurrence ledger** and
the taxonomy identity carried in each entry. It never writes, never calls a model,
and never consults a verdict beyond what the ledger already sealed. Running it
twice on the same ledger yields a byte-identical report and ``metric_hash``.

Definitions
-----------
* **Epoch** - the ledger's own time bucket, ``entry["period"]`` (already sealed
  into the hash chain). Epochs are ordered lexically (ISO prefixes sort by time).
* **Fingerprint** - a recurring-failure identity. The default is the failure
  ``family``; any callable ``key(entry) -> str`` may be supplied instead.
* **Recurrence series** - for each fingerprint ``f`` over the global ordered epoch
  axis ``E = [e_0, ..., e_{m-1}]``, the vector ``r_f = [c_f(e_0), ..., c_f(e_{m-1})]``
  where ``c_f(e)`` counts occurrences of ``f`` in epoch ``e`` (absent epochs are 0,
  which is what makes decline to zero measurable).
* **Decline score** - over the tail ``W = r_f[first:]`` starting at the first epoch
  where ``f`` appears, with ``peak = max(W)`` and ``final = W[-1]``::

      decline_score(f) = (peak - final) / peak            in [0, 1]

  ``1.0`` means the fingerprint was driven from its worst epoch down to zero by the
  final epoch (eliminated); ``0.0`` means it is still at its peak (no learning). A
  fingerprint that recurs after going quiet has ``final > 0`` and is flagged
  non-monotone.
* **Continual-learning score** - the mean decline score across fingerprints, plus a
  peak-weighted variant that emphasises the worst offenders.

The metric is meaningful only for ledgers spanning at least two epochs; with a
single epoch every decline score is ``0`` by construction.
"""
from __future__ import annotations

from typing import Any, Callable

from . import ledger as ledger_mod
from .hashing import sha256_hex

METRIC_SCHEMA = "sfa.recurrence_decline.v0"


class RecurrenceMetricError(ValueError):
    """Raised when the metric cannot be computed (e.g., a broken ledger chain)."""


def _epoch_of(entry: dict[str, Any]) -> str:
    return str(entry.get("period"))


def family_key(entry: dict[str, Any]) -> str:
    """Default fingerprint: the failure family carried by the ledger entry."""
    return str(entry.get("family"))


def epoch_axis(entries: list[dict[str, Any]]) -> list[str]:
    return sorted({_epoch_of(e) for e in entries})


def recurrence_series(
    entries: list[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], str] = family_key,
) -> tuple[list[str], dict[str, list[int]]]:
    """Return (ordered epochs, {fingerprint: per-epoch occurrence counts})."""
    epochs = epoch_axis(entries)
    index = {epoch: i for i, epoch in enumerate(epochs)}
    series: dict[str, list[int]] = {}
    for entry in entries:
        fingerprint = key(entry)
        row = series.setdefault(fingerprint, [0] * len(epochs))
        row[index[_epoch_of(entry)]] += 1
    return epochs, series


def _decline_of(row: list[int]) -> dict[str, Any] | None:
    active = [i for i, count in enumerate(row) if count > 0]
    if not active:
        return None
    first = active[0]
    window = row[first:]
    peak = max(window)
    final = window[-1]
    decline_score = (peak - final) / peak if peak > 0 else 0.0
    peak_index = window.index(peak)
    post_peak = window[peak_index:]
    monotone = all(post_peak[i] >= post_peak[i + 1] for i in range(len(post_peak) - 1))
    return {
        "recurrence_series": list(row),
        "first_epoch_index": first,
        "peak_rate": peak,
        "final_rate": final,
        "total_occurrences": sum(row),
        "decline_score": round(decline_score, 6),
        "eliminated": final == 0,
        "monotone_post_peak": monotone,
    }


def compute_recurrence_decline(
    entries: list[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], str] = family_key,
) -> dict[str, Any]:
    """Compute the sealed recurrence-decline report (pure function of the entries)."""
    epochs, series = recurrence_series(entries, key=key)
    per_fingerprint: dict[str, Any] = {}
    for fingerprint in sorted(series):
        decline = _decline_of(series[fingerprint])
        if decline is not None:
            per_fingerprint[fingerprint] = decline

    scores = [d["decline_score"] for d in per_fingerprint.values()]
    weights = [d["peak_rate"] for d in per_fingerprint.values()]
    mean_score = round(sum(scores) / len(scores), 6) if scores else 0.0
    weight_total = sum(weights)
    weighted_score = (
        round(sum(s * w for s, w in zip(scores, weights)) / weight_total, 6)
        if weight_total
        else 0.0
    )

    report = {
        "schema": METRIC_SCHEMA,
        "epochs": epochs,
        "epoch_count": len(epochs),
        "total_occurrences": len(entries),
        "fingerprint_count": len(per_fingerprint),
        "fingerprints": per_fingerprint,
        "continual_learning_score": mean_score,
        "occurrence_weighted_score": weighted_score,
        "eliminated_fingerprints": sorted(
            f for f, d in per_fingerprint.items() if d["eliminated"]
        ),
    }
    report["metric_hash"] = sha256_hex({k: v for k, v in report.items() if k != "metric_hash"})
    return report


def compute_from_path(
    ledger_path: str,
    *,
    key: Callable[[dict[str, Any]], str] = family_key,
    verify: bool = True,
) -> dict[str, Any]:
    """Load a ledger, optionally attest its hash chain, and compute the metric.

    With ``verify=True`` (the default) a broken or tampered chain raises rather
    than silently scoring corrupted history - the metric only trusts an intact
    hash-chained ledger.
    """
    if verify:
        ok, errors, _count = ledger_mod.verify_chain(ledger_path)
        if not ok:
            detail = "; ".join(f"entry {index}: {message}" for index, message in errors)
            raise RecurrenceMetricError(f"ledger chain is not intact: {detail}")
    entries = ledger_mod.read_ledger(ledger_path)
    return compute_recurrence_decline(entries, key=key)
