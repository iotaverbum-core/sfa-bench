#!/usr/bin/env python3
"""SFA-Bench v1.1.0 historical reports.

Answers: how has this reasoning system changed over time?
Reads the ledger and artifacts. Writes nothing.

Run:  python report.py
"""
import json
import os
import sys

from sfa import families as fam_mod
from sfa import history as H
from sfa import ledger as ledger_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")
ARTIFACTS_DIR = os.path.join(ROOT, "artifacts")
FAMILIES_PATH = os.path.join(ROOT, "families.json")
CONFIG_PATH = os.path.join(ROOT, "history_config.json")


def _hr(title):
    print("\n" + title)
    print("-" * len(title))


def lineage_chains():
    if not os.path.isdir(ARTIFACTS_DIR):
        return []
    by_hash = {}
    for name in sorted(os.listdir(ARTIFACTS_DIR)):
        if not name.endswith(".sealed.json"):
            continue
        with open(os.path.join(ARTIFACTS_DIR, name), encoding="utf-8") as fh:
            art = json.load(fh)
        by_hash[art["artifact_hash"]] = art

    children = {h: [] for h in by_hash}
    roots = []
    for h, art in by_hash.items():
        parent = art.get("parent_artifact_id")
        if parent and parent in by_hash:
            children[parent].append(h)
        else:
            roots.append(h)

    chains = []

    def walk(h, acc):
        art = by_hash[h]
        fam = art.get("failure_family", art.get("failure_category"))
        acc = acc + [(fam, int(art.get("lineage_depth", 0)), h)]
        kids = sorted(children.get(h, []))
        if not kids:
            chains.append(acc)
        for k in kids:
            walk(k, acc)

    for root_hash in roots:
        if children.get(root_hash):
            walk(root_hash, [])
    return [c for c in chains if len(c) > 1]


def main():
    taxonomy, tax_version = fam_mod.load_taxonomy(FAMILIES_PATH)
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    entries = ledger_mod.read_ledger(LEDGER_PATH)

    print("SFA-Bench v1.1.0 - Failure History Report")
    print("=" * 74)
    if not entries:
        print("Ledger is empty. Run: python run_benchmark.py")
        print("For demo multi-year history, run: python seed_history.py")
        return 1

    periods = H.all_periods(entries)
    print(f"taxonomy {tax_version}   |   {len(entries)} occurrences   |   periods {periods[0]}..{periods[-1]}   |   families observed: {len(H.observed_families(entries))}")

    _hr("Family status (recurrence + extinction)")
    print(f"{'family':<28}{'status':<11}{'total':>6}{'first':>8}{'latest':>8}{'rate':>8}")
    for row in H.family_status_table(entries, taxonomy, config):
        print(f"{row['family']:<28}{row['status']:<11}{row['total_occurrences']:>6}{row['first_occurrence']:>8}{row['latest_occurrence']:>8}{row['recurrence_rate']:>8}")

    _hr("Top recurring failures")
    for row in H.top_recurring(entries, 5):
        print(f"  {row['total_occurrences']:>5}x  {row['family']}  ({row['first_occurrence']}..{row['latest_occurrence']})")

    _hr("Fastest growing failures")
    rows = H.fastest_growing(entries, 5)
    if not rows:
        print("  (no growth between the last two periods)")
    for row in rows:
        print(f"  +{row['delta']:>4}  {row['family']}  {row['prev']}->{row['latest']}  ({row['prev_period']}->{row['latest_period']})")

    _hr("Longest surviving failures")
    for row in H.longest_surviving(entries, 5):
        print(f"  {row['span_periods']:>3} periods  {row['family']}  ({row['first_occurrence']}..{row['latest_occurrence']})")

    _hr("Extinct failures")
    extinct = H.extinct_families(entries, taxonomy, config)
    if not extinct:
        print("  (none)")
    for row in extinct:
        print(f"  {row['family']}  last seen {row['latest_occurrence']}  ({row['total_occurrences']} total)")

    _hr("Newest failure families")
    for row in H.newest_families(entries, 5):
        print(f"  first seen {row['first_occurrence']}  {row['family']}")

    _hr("Lineage chains (evolution of a pathology)")
    chains = lineage_chains()
    if not chains:
        print("  (no multi-step lineage recorded)")
    for chain in chains:
        path = "  ->  ".join(f"{fam}@d{depth}" for fam, depth, _ in chain)
        print("  " + path)

    print("\n" + "=" * 74)
    print("A researcher can now answer: how has this system's reasoning changed over time?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
