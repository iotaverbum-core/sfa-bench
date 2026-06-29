#!/usr/bin/env python3
"""Minimal integration example - run: python -m product.sdk.example

This is the whole integration a design partner writes: wrap each answer your RAG
assistant produces, hand GroundLedger the citations + the evidence it used, and
gate or log on the verdict. Everything is sealed into a tamper-evident ledger you
can export later. No server required (embedded transport).
"""
from __future__ import annotations

import tempfile

from product.sdk import GroundLedgerClient


def main() -> int:
    gl = GroundLedgerClient.embedded(
        data_root=tempfile.mkdtemp(), tenant="acme-insurance", rule_pack="insurance_v1"
    )

    # In production these three pieces come straight from your RAG pipeline.
    evidence = {
        "documents": [
            {"id": "clause_3a", "title": "Deductible", "text": "The deductible is $1,000 per claim."},
        ],
        "facts": [
            {"id": "f_deductible", "subject": "deductible", "value": "$1,000"},
        ],
    }
    good = {
        "conclusion": "Your deductible is $1,000 per claim.",
        "cited_evidence": ["clause_3a"],
        "claims": [{"subject": "deductible", "value": "$1,000"}],
    }
    bad = {
        "conclusion": "Your deductible is only $500, see clause 9z.",
        "cited_evidence": ["clause_9z"],
        "claims": [{"subject": "deductible", "value": "$500"}],
    }

    for answer_id, answer in (("ans_1", good), ("ans_2", bad)):
        receipt = gl.verify(answer_id=answer_id, candidate=answer, evidence=evidence)
        if gl.is_grounded(receipt):
            print(f"{answer_id}: grounded - safe to show")
        else:
            print(f"{answer_id}: BLOCKED ({receipt['family']}) - {receipt['explanation']}")

    report = gl.audit_report()
    print(f"\nGroundedness rate: {report['groundedness_rate'] * 100:.0f}% "
          f"({report['grounded']}/{report['answers_verified']})  "
          f"attestation: {'ATTESTED' if report['attestation']['attested'] else 'TAMPER'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
