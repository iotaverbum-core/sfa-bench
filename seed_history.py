#!/usr/bin/env python3
"""Seed an EXAMPLE multi-year failure history.

Everything written here is marked synthetic=true and run_id='SEED-*'. This is
demonstration data, not a model run. It is idempotent: if SEED entries already
exist, it does nothing.

It seeds:
  1. Family-level occurrences across 2026-2029 showing growth, decline, and
     extinction.
  2. A 3-step lineage chain showing one pathology evolving across versions.

Run:  python seed_history.py
"""
import json
import os
import sys

from sfa import artifact as artifact_mod
from sfa import hashing
from sfa import ledger as ledger_mod
from sfa import verifier as verifier_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = os.path.join(ROOT, "artifacts")
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")

SYNTHETIC = {
    "unsupported_attribution": {"2026": 8, "2027": 5, "2028": 2, "2029": 0},
    "unsupported_number": {"2026": 6, "2027": 4, "2028": 2, "2029": 1},
    "unsupported_citation": {"2026": 1, "2027": 3, "2028": 6, "2029": 10},
    "contradicts_evidence": {"2026": 3, "2027": 3, "2028": 3, "2029": 3},
    "unsupported_date": {"2026": 0, "2027": 4, "2028": 0, "2029": 0},
    "fabricated_entity": {"2026": 0, "2027": 0, "2028": 0, "2029": 4},
}

LINEAGE = [
    ("lineage_demo_01", "unsupported_attribution", "UNSUPPORTED_CLAIM", "2026-06-01"),
    ("lineage_demo_02", "unsupported_citation", "UNSUPPORTED_CLAIM", "2027-06-01"),
    ("lineage_demo_03", "contradicts_evidence", "CONTRADICTS_EVIDENCE", "2028-06-01"),
]


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def main():
    if any(str(e.get("run_id", "")).startswith("SEED") for e in ledger_mod.read_ledger(LEDGER_PATH)):
        print("Already seeded (SEED entries present). Nothing to do.")
        return 0

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    logged = 0

    for family, by_year in SYNTHETIC.items():
        for year in sorted(by_year):
            for i in range(by_year[year]):
                ah = hashing.sha256_hex(f"synthetic:{family}:{year}:{i}")
                ledger_mod.append_occurrence(
                    LEDGER_PATH,
                    artifact_hash=ah,
                    case_id=f"synthetic-{family}",
                    category="(synthetic)",
                    family=family,
                    observed_at=f"{year}-01-01T00:00:00+00:00",
                    period=year,
                    run_id=f"SEED-{year}",
                    synthetic=True,
                )
                logged += 1

    parent = None
    depth = 0
    for cid, family, category, day in LINEAGE:
        inp = {"case_id": cid, "question": "example lineage step"}
        ev = {"facts": [{"id": "f1", "subject": "x", "value": 1}]}
        cand = {"conclusion": "example", "cited_evidence": ["f1"], "claims": [{"subject": "y", "value": 1}]}
        art = artifact_mod.seal_failure(
            cid,
            inp,
            ev,
            cand,
            verifier_mod.VERIFIER_VERSION,
            category,
            family,
            f"lineage demo step for {family}",
            parent_artifact_id=parent,
            lineage_depth=depth,
            sealed_at=f"{day}T00:00:00+00:00",
        )
        _write_json(os.path.join(ARTIFACTS_DIR, cid + ".sealed.json"), art)
        ledger_mod.append_occurrence(
            LEDGER_PATH,
            artifact_hash=art["artifact_hash"],
            case_id=cid,
            category=category,
            family=family,
            observed_at=f"{day}T00:00:00+00:00",
            period=day[:4],
            run_id="SEED-lineage",
            synthetic=True,
        )
        parent = art["artifact_hash"]
        depth += 1
        logged += 1

    print(f"seeded {logged} example occurrences (2026-2029) + a 3-step lineage chain.")
    print("All marked synthetic=true. Run: python report.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
