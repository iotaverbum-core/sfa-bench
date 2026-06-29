#!/usr/bin/env python3
"""GroundLedger sellable demo - run: python -m product.demo

Tells the whole story offline, with no model calls and no network:

  1. Four insurance answers are verified against their evidence.
  2. One passes; three fail with named, categorized reasons.
  3. An audit report is produced with an independent attestation: ATTESTED.
  4. Someone quietly edits a sealed failure to look like a pass.
  5. Replay catches it: TAMPER DETECTED.

That last step is the point: the record cannot be silently rewritten.
"""
from __future__ import annotations

import json
import shutil
from itertools import count
from pathlib import Path

from product.groundledger import engine, replay, report as report_mod, rulepacks
from product.groundledger.store import TenantStore

EXAMPLES = Path(__file__).resolve().parent / "examples"
DATA_ROOT = Path(__file__).resolve().parent / "data" / "demo"
TENANT = "acme-insurance"
ORDER = [
    "grounded_answer.json",
    "fabricated_citation.json",
    "contradicts_evidence.json",
    "unsupported_claim.json",
]


def _fixed_clock():
    counter = count()
    return lambda: f"2026-01-01T00:00:{next(counter):02d}+00:00"


def main() -> int:
    if DATA_ROOT.exists():
        shutil.rmtree(DATA_ROOT)
    store = TenantStore(DATA_ROOT, TENANT)
    rule_pack = rulepacks.load_rule_pack("insurance_v1")
    clock = _fixed_clock()

    print("GroundLedger demo - insurance policy assistant")
    print("=" * 60)
    print("Verifying four answers against the policy evidence they used:\n")

    for filename in ORDER:
        submission = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
        receipt = engine.verify_submission(submission, rule_pack, now=clock)
        store.record(submission, receipt)
        mark = "PASS " if receipt["status"] == "PASS" else "FAIL "
        reason = "grounded in evidence" if receipt["status"] == "PASS" else (
            f"{receipt['family']} - {receipt['explanation']}"
        )
        print(f"  [{mark}] {receipt['answer_id']}: {reason}")

    print("\n" + "-" * 60)
    print("Audit report (the artifact you hand a buyer or regulator):\n")
    report = report_mod.build_report(store)
    print(report_mod.render_text(report))

    print("\n" + "-" * 60)
    print("Now an insider quietly edits a sealed failure to look like a pass...\n")
    tampered_path = store.receipts_dir / "ans_fabricated_002.json"
    forged = json.loads(tampered_path.read_text(encoding="utf-8"))
    forged["status"] = "PASS"
    forged["category"] = None
    forged["family"] = None
    forged["explanation"] = "candidate is consistent with evidence under all rules"
    forged["violations"] = []
    tampered_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")
    print(f"  edited {tampered_path.name}: FAIL -> PASS (without re-sealing)")

    print("\nRe-running independent attestation:\n")
    attestation = replay.attest(store)
    status = "ATTESTED" if attestation["attested"] else "TAMPER DETECTED"
    print(f"  result: {status}")
    for issue in attestation["issues"]:
        print(f"    - [{issue['code']}] {issue.get('answer_id')}: {issue['detail']}")

    print("\n" + "=" * 60)
    if attestation["attested"]:
        print("Unexpected: tampering was not detected.")
        return 1
    print("The forged pass was caught. The audit trail cannot be silently rewritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
