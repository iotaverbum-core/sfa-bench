"""LLM-assisted extraction tests (recall upgrade; determinism preserved)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from product.groundledger import assisted, engine, replay, rulepacks
from product.groundledger.store import TenantStore
from product.sdk import GroundLedgerClient

# Deductible is in the evidence; rental reimbursement is NOT - the conservative
# rule extractor cannot see the rental claim, but it IS present in the text.
EVIDENCE = {
    "documents": [{"id": "clause_3a", "title": "Deductible", "text": "Deductible is $1,000 per claim."}],
    "facts": [{"id": "f", "subject": "deductible", "value": "$1,000", "aliases": ["deductible"]}],
}
TEXT = ("Your deductible is $1,000 per claim, per clause_3a. "
        "Your rental reimbursement is $50 per day.")


def rental_suggester(answer_text, evidence):
    """Deterministic stand-in for a model: nominates the rental claim."""
    return [{"subject": "rental_reimbursement", "value": "$50"}]


def fabricating_suggester(answer_text, evidence):
    """Nominates a claim that is NOT in the text - must be rejected."""
    return [{"subject": "earthquake_coverage", "value": "$5,000"}]


def _submission(proposal=None):
    sub = {"answer_id": "a1", "rule_pack": "insurance_v1", "answer_text": TEXT, "evidence": EVIDENCE}
    if proposal is not None:
        sub["extraction_proposal"] = proposal
    return sub


class AssistedExtractionTests(unittest.TestCase):
    def setUp(self):
        self.pack = rulepacks.load_rule_pack("insurance_v1")

    def test_rule_only_misses_the_unsupported_claim(self):
        receipt, _ = engine.verify_text_submission(_submission(), self.pack)
        self.assertEqual(receipt["status"], "PASS")          # rental claim not seen
        self.assertEqual(receipt["extraction"]["mode"], "rule")

    def test_assisted_catches_the_unsupported_claim(self):
        proposal = assisted.propose(TEXT, EVIDENCE, suggest=rental_suggester, allow_in_ci=True)
        receipt, stored = engine.verify_text_submission(_submission(proposal), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "UNSUPPORTED_CLAIM")
        self.assertIn({"subject": "rental_reimbursement", "value": "$50"},
                      stored["candidate"]["claims"])
        self.assertEqual(receipt["extraction"]["mode"], "llm-assisted")

    def test_model_cannot_fabricate_a_claim(self):
        proposal = assisted.propose(TEXT, EVIDENCE, suggest=fabricating_suggester, allow_in_ci=True)
        receipt, stored = engine.verify_text_submission(_submission(proposal), self.pack)
        subjects = {c["subject"] for c in stored["candidate"]["claims"]}
        self.assertNotIn("earthquake_coverage", subjects)    # not in text -> dropped
        self.assertEqual(receipt["status"], "PASS")

    def test_ci_guard_blocks_the_model_path(self):
        prev = os.environ.get("CI")
        os.environ["CI"] = "true"
        try:
            with self.assertRaises(assisted.AssistedExtractionError):
                assisted.propose(TEXT, EVIDENCE, suggest=rental_suggester)  # allow_in_ci defaults False
        finally:
            if prev is None:
                os.environ.pop("CI", None)
            else:
                os.environ["CI"] = prev

    def test_replay_reproduces_offline_and_detects_proposal_tamper(self):
        store = TenantStore(tempfile.mkdtemp(), "t")
        proposal = assisted.propose(TEXT, EVIDENCE, suggest=rental_suggester, allow_in_ci=True)
        receipt, stored = engine.verify_text_submission(_submission(proposal), self.pack)
        store.record(stored, receipt)
        # replay re-derives from the sealed proposal and never calls a model
        self.assertTrue(replay.attest(store)["attested"])

        path = Path(store.submissions_dir) / "a1.json"
        doctored = json.loads(path.read_text(encoding="utf-8"))
        doctored["extraction_proposal"] = []                 # strip the sealed proposal
        path.write_text(json.dumps(doctored), encoding="utf-8")
        result = replay.attest(store)
        self.assertFalse(result["attested"])
        self.assertIn("extraction_mismatch", {i["code"] for i in result["issues"]})


class AssistedSdkTests(unittest.TestCase):
    def test_embedded_verify_text_assisted(self):
        gl = GroundLedgerClient.embedded(
            data_root=tempfile.mkdtemp(), tenant="t", rule_pack="insurance_v1"
        )
        receipt = gl.verify_text_assisted(
            answer_id="a1", answer_text=TEXT, evidence=EVIDENCE,
            suggest=rental_suggester, allow_in_ci=True,
        )
        self.assertEqual(receipt["category"], "UNSUPPORTED_CLAIM")
        self.assertTrue(gl.replay()["attested"])


if __name__ == "__main__":
    unittest.main()
