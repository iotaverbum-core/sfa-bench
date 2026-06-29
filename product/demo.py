#!/usr/bin/env python3
"""GroundLedger Phase 1 demo - run: ./scripts/demo.sh  (or: python -m product.demo)

Tells the whole story offline, with no model calls and no network:

  1. Four insurance answers are verified against the evidence they used.
  2. One passes; three fail with named, severity-ranked findings.
  3. A customer-facing audit report (report.html) and a signed, self-verifying
     bundle (bundle.json) are written - the artifacts you show on a sales call.
  4. Someone quietly edits a sealed failure to look like a pass.
  5. Replay catches it: TAMPER DETECTED.
"""
from __future__ import annotations

import json
import shutil
from itertools import count
from pathlib import Path

from product.groundledger import engine, export as export_mod, replay, report as report_mod, rulepacks
from product.groundledger.store import TenantStore

EXAMPLES = Path(__file__).resolve().parent / "examples"
DATA_ROOT = Path(__file__).resolve().parent / "data" / "demo"
TENANT = "acme-insurance"
DEMO_SIGNING_KEY = "demo-pilot-key"
ORDER = [
    "grounded_answer.json",
    "fabricated_citation.json",
    "contradicts_evidence.json",
    "unsupported_claim.json",
]


def _fixed_clock():
    counter = count()
    return lambda: f"2026-01-01T00:00:{next(counter):02d}+00:00"


def main(out_dir: Path | str = DATA_ROOT) -> int:
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    store = TenantStore(out_dir, TENANT)
    rule_pack = rulepacks.load_rule_pack("insurance_v1")
    clock = _fixed_clock()

    print("GroundLedger demo - insurance policy assistant")
    print("=" * 64)
    print("Verifying four answers against the policy evidence they used:\n")

    for filename in ORDER:
        submission = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
        receipt = engine.verify_submission(submission, rule_pack, now=clock)
        store.record(submission, receipt)
        if receipt["status"] == "PASS":
            print(f"  [PASS] {receipt['answer_id']}: grounded in evidence")
        else:
            print(f"  [FAIL] {receipt['answer_id']}: {receipt['family']} - {receipt['explanation']}")

    # Build the customer-facing artifacts on the clean, untampered ledger.
    bundle = export_mod.build_export_bundle(store, signing_key=DEMO_SIGNING_KEY, now=_fixed_clock())
    report = bundle["report"]
    html_path = out_dir / "report.html"
    bundle_path = out_dir / "bundle.json"
    html_path.write_text(export_mod.render_html(bundle), encoding="utf-8")
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "-" * 64)
    print("Audit report (what you hand a buyer or regulator):\n")
    print(report_mod.render_text(report))

    print("\n" + "-" * 64)
    print("Customer-facing artifacts written:")
    print(f"  report : {html_path}   (open in a browser / print to PDF)")
    print(f"  bundle : {bundle_path}  (signed, verifies offline)")

    print("\n" + "-" * 64)
    print("Now an insider quietly edits a sealed failure to look like a pass...\n")
    tampered_path = store.receipts_dir / "ans_fabricated_002.json"
    forged = json.loads(tampered_path.read_text(encoding="utf-8"))
    forged.update({"status": "PASS", "category": None, "family": None, "violations": [],
                   "explanation": "candidate is consistent with evidence under all rules"})
    tampered_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")
    print("  edited ans_fabricated_002.json: FAIL -> PASS (without re-sealing)")

    attestation = replay.attest(store)
    print(f"\n  re-attestation: {'ATTESTED' if attestation['attested'] else 'TAMPER DETECTED'}")
    for issue in attestation["issues"]:
        print(f"    - [{issue['code']}] {issue.get('answer_id')}: {issue['detail']}")

    print("\n" + "=" * 64)
    if attestation["attested"]:
        print("Unexpected: tampering was not detected.")
        return 1
    print("Why this is a subscription, not a one-off script:")
    print("  - every answer your assistant ships gets a sealed, reproducible verdict;")
    print("  - the ledger is append-only, so failures can't be quietly deleted;")
    print("  - you can hand an auditor a report they verify themselves, any day.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
