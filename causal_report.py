#!/usr/bin/env python3
"""SFA-Bench Causal Linkage Report CLI.

Reads the taxonomy's typed directed causal edges (families.json schema v2) and
joins them with occurrence-ledger recurrence to show upstream/downstream linkage:
for a causal edge A -> B, as the upstream family A is addressed, does the
downstream family B recur less? Deterministic and offline; no model call.

  python causal_report.py                              # score the causal fixture + self-check
  python causal_report.py --ledger history/occurrences.jsonl
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sfa import causal_report as causal
from sfa import families as fam_mod
from sfa import ledger as ledger_mod

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "examples" / "causal" / "causal_ledger.jsonl"

_EXPECTED_HASH = "753d3d4ca0103ccafa8bd03eb0eb6ea882d8ad305194d3948db5a4ec8e34b925"


def _fmt_series(series):
    return ",".join(str(c) for c in series)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", help="occurrence ledger to link (defaults to the causal fixture)")
    args = parser.parse_args(argv)

    print("SFA-Bench v2.0.0-alpha.1 Causal Linkage Report")
    print("=" * 58)

    taxonomy, version = fam_mod.load_taxonomy(ROOT / "families.json")
    print(f"taxonomy: {version}   schema: {taxonomy.schema_version}   causal edges: {len(taxonomy.edges())}")

    ledger_path = args.ledger or str(FIXTURE)
    is_fixture = args.ledger is None
    ok, _errors, _count = ledger_mod.verify_chain(ledger_path)
    if not ok:
        print(f"ledger chain not intact: {ledger_path}")
        print("=" * 58)
        print("final status: FAIL")
        return 2
    entries = ledger_mod.read_ledger(ledger_path)
    report = causal.compute_linkage(taxonomy, entries)

    print(f"epochs: {report['epochs']}")
    print()
    print("## Family recurrence (family + descendants)")
    print(f"{'family':<28} {'series':<12} {'decline':>8} {'eliminated':>11}  upstream -> downstream")
    for family in sorted(report["families"]):
        row = report["families"][family]
        up = ", ".join(u["family"] for u in row["upstream"]) or "-"
        down = ", ".join(d["family"] for d in row["downstream"]) or "-"
        decline = "-" if row["decline_score"] is None else f"{row['decline_score']:.3f}"
        print(f"{family:<28} {_fmt_series(row['recurrence_series']):<12} {decline:>8} "
              f"{str(row['eliminated']):>11}  {up} -> {down}")

    print()
    print("## Causal edge linkage")
    for edge in report["edges"]:
        up = "-" if edge["upstream_decline"] is None else f"{edge['upstream_decline']:.3f}"
        down = "-" if edge["downstream_decline"] is None else f"{edge['downstream_decline']:.3f}"
        print(f"  {edge['from']} --{edge['type']}--> {edge['to']}: "
              f"upstream decline {up}, downstream decline {down}, "
              f"tracks={edge['downstream_declines_with_upstream']}")
    print()
    print(f"report_hash: {report['report_hash']}")

    ok_status = True
    if is_fixture:
        again = causal.compute_linkage(taxonomy, entries)
        deterministic = again["report_hash"] == report["report_hash"]
        expected = report["report_hash"] == _EXPECTED_HASH
        print(f"determinism: {'PASS' if deterministic else 'FAIL'}")
        print(f"expected fixture report_hash: {'PASS' if expected else 'FAIL'}")
        ok_status = deterministic and expected

    print("=" * 58)
    print(f"final status: {'PASS' if ok_status else 'FAIL'}")
    return 0 if ok_status else 1


if __name__ == "__main__":
    sys.exit(main())
