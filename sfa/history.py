"""History engine: derived views over the append-only occurrence ledger.

This module never writes. Every report is a deterministic function of the ledger,
taxonomy, and history_config.json. Running it twice on the same ledger gives the
same answer, which keeps the history auditable.
"""
from collections import defaultdict


def period_of(observed_at, granularity="year"):
    if granularity == "year":
        return observed_at[:4]
    if granularity == "month":
        return observed_at[:7]
    if granularity == "day":
        return observed_at[:10]
    raise ValueError(f"unknown period granularity: {granularity!r}")


def _period_key(period):
    return period  # ISO prefixes sort lexically


def all_periods(entries):
    return sorted({e["period"] for e in entries}, key=_period_key)


def latest_period(entries):
    periods = all_periods(entries)
    return periods[-1] if periods else None


def family_timeline(entries, family=None):
    tl = defaultdict(int)
    for e in entries:
        if family is None or e["family"] == family:
            tl[e["period"]] += 1
    return dict(tl)


def timeline_with_descendants(entries, taxonomy, family):
    fams = {family} | set(taxonomy.descendants(family))
    tl = defaultdict(int)
    for e in entries:
        if e["family"] in fams:
            tl[e["period"]] += 1
    return dict(tl)


def observed_families(entries):
    return sorted({e["family"] for e in entries})


def _span(first, latest):
    try:
        return int(latest[:4]) - int(first[:4]) + 1
    except ValueError:
        return 1


def recurrence(entries, family):
    occ = [e for e in entries if e["family"] == family]
    if not occ:
        return None
    periods = sorted({e["period"] for e in occ}, key=_period_key)
    first, latest = periods[0], periods[-1]
    span = _span(first, latest)
    return {
        "family": family,
        "total_occurrences": len(occ),
        "first_occurrence": first,
        "latest_occurrence": latest,
        "active_periods": len(periods),
        "span_periods": span,
        "recurrence_rate": round(len(occ) / span, 3) if span else float(len(occ)),
    }


def extinction_status(entries, taxonomy, family, config):
    periods = all_periods(entries)
    if not periods:
        return "unknown"
    timeline = family_timeline(entries, family)
    if not timeline:
        return "absent"

    silent = config.get("extinction", {}).get("silent_periods_for_extinct", 1)
    window = config.get("extinction", {}).get("decline_window", 3)
    tail = periods[-silent:] if silent > 0 else []
    occurred_in_tail = any(timeline.get(p, 0) > 0 for p in tail)
    if not occurred_in_tail:
        return "extinct"

    recent = periods[-window:]
    counts = [timeline.get(p, 0) for p in recent]
    if len(counts) >= 2 and all(counts[i] > counts[i + 1] for i in range(len(counts) - 1)) and counts[-1] > 0:
        return "declining"
    return "active"


def top_recurring(entries, n=10):
    rows = [recurrence(entries, f) for f in observed_families(entries)]
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: (-r["total_occurrences"], r["family"]))
    return rows[:n]


def fastest_growing(entries, n=10):
    periods = all_periods(entries)
    if len(periods) < 2:
        return []
    prev_p, last_p = periods[-2], periods[-1]
    rows = []
    for f in observed_families(entries):
        tl = family_timeline(entries, f)
        delta = tl.get(last_p, 0) - tl.get(prev_p, 0)
        if delta > 0:
            rows.append({
                "family": f,
                "delta": delta,
                "prev": tl.get(prev_p, 0),
                "latest": tl.get(last_p, 0),
                "prev_period": prev_p,
                "latest_period": last_p,
            })
    rows.sort(key=lambda r: (-r["delta"], r["family"]))
    return rows[:n]


def longest_surviving(entries, n=10):
    rows = [recurrence(entries, f) for f in observed_families(entries)]
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: (-r["span_periods"], -r["total_occurrences"], r["family"]))
    return rows[:n]


def extinct_families(entries, taxonomy, config):
    rows = []
    for f in observed_families(entries):
        if extinction_status(entries, taxonomy, f, config) == "extinct":
            rec = recurrence(entries, f)
            if rec:
                rows.append(rec)
    rows.sort(key=lambda r: (r["latest_occurrence"], r["family"]))
    return rows


def newest_families(entries, n=10):
    rows = [recurrence(entries, f) for f in observed_families(entries)]
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: (r["first_occurrence"], r["family"]), reverse=True)
    return rows[:n]


def family_status_table(entries, taxonomy, config):
    rows = []
    for f in observed_families(entries):
        rec = recurrence(entries, f)
        if not rec:
            continue
        rec = dict(rec)
        rec["status"] = extinction_status(entries, taxonomy, f, config)
        rec["depth"] = taxonomy.depth(f) if taxonomy.known(f) else 0
        rows.append(rec)
    rows.sort(key=lambda r: r["family"])
    return rows
