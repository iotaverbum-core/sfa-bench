#!/usr/bin/env python3
"""SFA-Bench Property-Based Verifier Contract CLI (gold-absent tasks).

Demonstrates the gold-absent verdict path: a versioned, sealed contract of
decidable properties whose deterministic conjunction is the verdict. Wires the
deferred-consequence task family - the contract decides accept/reject with no
stored gold answer, entirely offline and with no model call.

  python property_contract.py            # deferred-consequence contract demo + self-check
"""
from __future__ import annotations

import sys

from sfa import deferred_consequence as dc
from sfa import property_contract as pc


def _demo_case():
    pack = dc.generate_pack({"seed": dc.DEFAULT_SEED, "per_cell": 1})
    return pack["cases"][0]


def main(argv: list[str] | None = None) -> int:
    print("SFA-Bench v1.1.0 Property-Based Verifier Contract")
    print("=" * 58)

    case = _demo_case()
    subject = case["subject"]
    correct = case["scoring"]["correct_value"]
    stale = case["scoring"]["stale_value"]

    contract = dc.property_contract(case)
    print(f"task family: {contract['task_family']}   contract version: {contract['contract_version']}")
    print(f"properties: {[p['id'] + ':' + p['family'] for p in contract['properties']]}")
    print(f"conjunction: {contract['conjunction']}   contract_hash: {contract['contract_hash']}")
    print()

    scenarios = [
        ("propagated answer (v1)", {"claims": [{"subject": subject, "value": correct}]}),
        ("stale answer (v0)", {"claims": [{"subject": subject, "value": stale}]}),
        ("fabricated value", {"claims": [{"subject": subject, "value": "__never_seen__"}]}),
        ("self-contradictory",
         {"claims": [{"subject": subject, "value": correct}, {"subject": subject, "value": stale}]}),
        ("malformed (claims not a list)", {"claims": "not-a-list"}),
    ]
    print(f"{'candidate':<32} {'verdict':<6} failed properties")
    verdicts = []
    for label, candidate in scenarios:
        verdict = dc.score_candidate_by_contract(case, candidate)
        verdicts.append((label, candidate, verdict))
        failed = ", ".join(verdict["failed_properties"]) or "-"
        print(f"{label:<32} {verdict['status']:<6} {failed}")

    # Self-check: determinism + expected accept/reject via the gold-absent contract.
    deterministic = all(
        dc.score_candidate_by_contract(case, candidate)["verdict_hash"] == verdict["verdict_hash"]
        for _label, candidate, verdict in verdicts
    )
    expected_ok = (
        verdicts[0][2]["status"] == "PASS"
        and all(v["status"] == "FAIL" for _l, _c, v in verdicts[1:])
        and verdicts[1][2]["failed_properties"] == ["recency"]
    )
    families_covered = set(pc.PROPERTY_FAMILIES) <= (
        {p["family"] for p in contract["properties"]} | {"citation_grounding"}
    )

    print()
    print(f"determinism: {'PASS' if deterministic else 'FAIL'}")
    print(f"gold-absent accept/reject as expected: {'PASS' if expected_ok else 'FAIL'}")
    print(f"decidable property families available: {', '.join(pc.PROPERTY_FAMILIES)}")

    print("=" * 58)
    ok = deterministic and expected_ok and families_covered
    print(f"final status: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
