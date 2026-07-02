#!/usr/bin/env python3
"""SFA-Bench v1.1.0 replay / attestation.

Two layers are re-attested independently:

  A. Sealed artifacts: each artifact's content hash still matches; when the
     source case still exists, the case file hashes and verdict/family reproduce.

  B. Occurrence ledger: the hash chain is unbroken, so no entry was deleted,
     inserted, reordered, or edited.

Run:  python replay.py
"""
import json
import os
import sys

from sfa import artifact as artifact_mod
from sfa import case as case_mod
from sfa import families as fam_mod
from sfa import hashing
from sfa import ledger as ledger_mod
from sfa import verifier as verifier_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(ROOT, "cases")
ARTIFACTS_DIR = os.path.join(ROOT, "artifacts")
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")
FAMILIES_PATH = os.path.join(ROOT, "families.json")


def replay_artifact(art_path):
    with open(art_path, encoding="utf-8") as fh:
        art = json.load(fh)
    cid = art["case_id"]
    checks = []
    intact, recomputed = artifact_mod.verify_artifact_integrity(art)
    checks.append(("seal intact", intact, "" if intact else f"stored {str(art.get('artifact_hash'))[:12]} != {recomputed[:12]}"))

    case_dir = os.path.join(CASES_DIR, cid)
    if not os.path.isdir(case_dir):
        # Long-lived archives may outlive their original case directories. The
        # seal remains the hard integrity check for the record itself.
        checks.append(("case archived (seal still verifies record)", True, ""))
        return cid, art, checks

    inp, ev, cand, rules = case_mod.load_verification_inputs(case_dir)
    checks.append(("input unchanged", hashing.sha256_hex(inp) == art["input_hash"], ""))
    checks.append(("evidence unchanged", hashing.sha256_hex(ev) == art["evidence_hash"], ""))
    checks.append(("candidate unchanged", hashing.sha256_hex(cand) == art["candidate_hash"], ""))

    verdict = verifier_mod.verify(inp, ev, cand, rules)
    family = fam_mod.classify_family(verdict.category, cand, ev) if verdict.status == "FAIL" else None
    recorded_family = art.get("failure_family") or fam_mod.CATEGORY_TO_FAMILY.get(art.get("failure_category"), "uncategorized")
    stable = (
        verdict.status == "FAIL"
        and verdict.category == art.get("failure_category")
        and recorded_family == family
    )
    checks.append(("verdict + family stable", stable, "" if stable else f"now {verdict.status}/{verdict.category}/{family}"))
    return cid, art, checks


def main():
    fam_mod.load_taxonomy(FAMILIES_PATH)  # validates taxonomy

    print("SFA-Bench v1.1.0 replay / attestation")
    print("=" * 74)

    all_ok = True

    print("A. sealed artifacts")
    arts = []
    if os.path.isdir(ARTIFACTS_DIR):
        arts = sorted(p for p in os.listdir(ARTIFACTS_DIR) if p.endswith(".sealed.json"))
    if not arts:
        print("   (none yet - run python run_benchmark.py)")
    for name in arts:
        cid, _art, checks = replay_artifact(os.path.join(ARTIFACTS_DIR, name))
        ok = all(c[1] for c in checks)
        all_ok = all_ok and ok
        print(f"   {cid:<34} {'OK' if ok else 'TAMPERED'}")
        for label, good, detail in checks:
            if not good:
                print(f"        XX {label}{(' - ' + detail) if detail else ''}")

    print("B. occurrence ledger (hash chain)")
    chain_ok, errors, count = ledger_mod.verify_chain(LEDGER_PATH)
    all_ok = all_ok and chain_ok
    if count == 0:
        print("   (empty)")
    elif chain_ok:
        print(f"   {count} entries, chain unbroken  OK")
    else:
        print(f"   {count} entries, CHAIN BROKEN:")
        for idx, msg in errors[:10]:
            print(f"        XX entry {idx}: {msg}")

    print("=" * 74)
    print("ATTESTED: artifacts and history are unaltered." if all_ok else "ALERT: an artifact, case, or ledger entry has changed.")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
