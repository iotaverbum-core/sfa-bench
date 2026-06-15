#!/usr/bin/env python3
"""SFA-Bench v0.1 -> v0.2 migration.

Migration is additive and non-destructive. v0.1 artifacts are NOT rewritten; the
history engine can read them natively. Migration only backfills the occurrence
ledger so legacy failures enter the temporal history using each artifact's own
sealed_at timestamp.

Run:  python migrate.py
"""
import json
import os
import sys

from sfa import families as fam_mod
from sfa import history as history_mod
from sfa import ledger as ledger_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = os.path.join(ROOT, "artifacts")
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")
CONFIG_PATH = os.path.join(ROOT, "history_config.json")


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    granularity = config.get("period_granularity", "year")
    existing = ledger_mod.read_ledger(LEDGER_PATH)
    already = {(e.get("artifact_hash"), e.get("observed_at")) for e in existing}

    if not os.path.isdir(ARTIFACTS_DIR):
        print("No artifacts/ to migrate.")
        return 0

    migrated = skipped = 0
    for name in sorted(os.listdir(ARTIFACTS_DIR)):
        if not name.endswith(".sealed.json"):
            continue
        with open(os.path.join(ARTIFACTS_DIR, name), encoding="utf-8") as fh:
            art = json.load(fh)
        if not str(art.get("schema", "")).endswith("v0.1"):
            continue
        observed_at = art.get("sealed_at", "1970-01-01T00:00:00+00:00")
        key = (art.get("artifact_hash"), observed_at)
        if key in already:
            skipped += 1
            continue
        family = art.get("failure_family") or fam_mod.CATEGORY_TO_FAMILY.get(art.get("failure_category"), "uncategorized")
        ledger_mod.append_occurrence(
            LEDGER_PATH,
            artifact_hash=art["artifact_hash"],
            case_id=art["case_id"],
            category=art.get("failure_category"),
            family=family,
            observed_at=observed_at,
            period=history_mod.period_of(observed_at, granularity),
            run_id="MIGRATION-v01",
            synthetic=False,
        )
        migrated += 1

    print(f"migrated {migrated} legacy v0.1 artifact(s) into the ledger; skipped {skipped} already present.")
    print("v0.1 artifacts were not modified. Run: python report.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
