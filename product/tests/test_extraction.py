"""Free-text extraction tests. Run: python -m unittest discover -s product -t . -p 'test_*.py'"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from product.groundledger import api, engine, extraction, replay, rulepacks
from product.groundledger.store import TenantStore
from product.sdk import GroundLedgerClient

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


EVIDENCE = {
    "documents": [{"id": "clause_3a", "title": "Deductible", "text": "Deductible is $1,000."}],
    "facts": [{"id": "f", "subject": "deductible", "value": "$1,000"}],
}
CONFIG = {"citation_patterns": ["clause_[A-Za-z0-9]+", "\\[([^\\]]+)\\]"], "value_window": 70}


class ExtractionUnitTests(unittest.TestCase):
    def test_real_and_fabricated_citations(self):
        result = extraction.extract_candidate(
            "Per clause_3a and clause_9z, your deductible applies.", EVIDENCE, config=CONFIG
        )
        self.assertEqual(result["candidate"]["cited_evidence"], ["clause_3a", "clause_9z"])
        by_token = {t["token"]: t["in_evidence"] for t in result["trace"]["citations"]}
        self.assertTrue(by_token["clause_3a"])
        self.assertFalse(by_token["clause_9z"])

    def test_currency_contradiction_detected(self):
        result = extraction.extract_candidate("Your deductible is $500.", EVIDENCE, config=CONFIG)
        self.assertEqual(result["candidate"]["claims"], [{"subject": "deductible", "value": "$500"}])

    def test_grounded_value_matches_evidence(self):
        result = extraction.extract_candidate("Your deductible is $1,000.", EVIDENCE, config=CONFIG)
        self.assertEqual(result["candidate"]["claims"], [{"subject": "deductible", "value": "$1,000"}])

    def test_conservative_on_uncovered_subject(self):
        # Evidence has no "rental" fact, so the extractor does not invent a claim.
        result = extraction.extract_candidate(
            "Rental reimbursement is $50/day.", EVIDENCE, config=CONFIG
        )
        self.assertEqual(result["candidate"]["claims"], [])

    def test_deterministic(self):
        text = "Your deductible is $500 per clause_3a."
        a = extraction.extract_candidate(text, EVIDENCE, config=CONFIG)["provenance"]["candidate_hash"]
        b = extraction.extract_candidate(text, EVIDENCE, config=CONFIG)["provenance"]["candidate_hash"]
        self.assertEqual(a, b)


class EngineTextTests(unittest.TestCase):
    def setUp(self):
        self.pack = rulepacks.load_rule_pack("insurance_v1")

    def test_grounded_text_passes(self):
        receipt, stored = engine.verify_text_submission(load_example("text_grounded.json"), self.pack)
        self.assertEqual(receipt["status"], "PASS")
        self.assertIn("extraction", receipt)
        self.assertEqual(receipt["extraction"]["candidate_hash"], receipt["candidate_hash"])
        self.assertIn("candidate", stored)
        self.assertIn("answer_text", stored)

    def test_fabricated_text_is_flagged(self):
        receipt, _ = engine.verify_text_submission(load_example("text_fabricated.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "FABRICATED_ENTITY")


class ReplayTextTests(unittest.TestCase):
    def setUp(self):
        self.store = TenantStore(tempfile.mkdtemp(), "txt")
        pack = rulepacks.load_rule_pack("insurance_v1")
        for name in ("text_grounded.json", "text_fabricated.json"):
            receipt, stored = engine.verify_text_submission(load_example(name), pack)
            self.store.record(stored, receipt)

    def test_clean_text_ledger_attests(self):
        self.assertTrue(replay.attest(self.store)["attested"])

    def test_edited_answer_text_is_caught(self):
        path = self.store.submissions_dir / "txt_fabricated_002.json"
        sub = json.loads(path.read_text(encoding="utf-8"))
        sub["answer_text"] = "Your deductible is $1,000 per clause_3a."  # whitewashed prose
        path.write_text(json.dumps(sub), encoding="utf-8")
        result = replay.attest(self.store)
        self.assertFalse(result["attested"])
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("extraction_text_mismatch", codes)

    def test_edited_stored_candidate_is_caught(self):
        path = self.store.submissions_dir / "txt_grounded_001.json"
        sub = json.loads(path.read_text(encoding="utf-8"))
        sub["candidate"]["claims"] = []  # strip the claims that were extracted
        path.write_text(json.dumps(sub), encoding="utf-8")
        result = replay.attest(self.store)
        self.assertFalse(result["attested"])
        self.assertIn("verdict_mismatch", {i["code"] for i in result["issues"]})


class ApiAndSdkTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.httpd = api.serve(host="127.0.0.1", port=0, data_root=self.tmp, api_keys={"k": "t"})
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_embedded_sdk_verify_text(self):
        gl = GroundLedgerClient.embedded(data_root=tempfile.mkdtemp(), tenant="t", rule_pack="insurance_v1")
        sub = load_example("text_fabricated.json")
        receipt = gl.verify_text(answer_id=sub["answer_id"], answer_text=sub["answer_text"],
                                 evidence=sub["evidence"], task_input=sub["task_input"])
        self.assertEqual(receipt["category"], "FABRICATED_ENTITY")
        self.assertIn("extraction", receipt)
        self.assertTrue(gl.replay()["attested"])

    def test_http_sdk_verify_text_and_report(self):
        gl = GroundLedgerClient.http(base_url=f"http://127.0.0.1:{self.port}", api_key="k")
        sub = load_example("text_grounded.json")
        receipt = gl.verify_text(answer_id=sub["answer_id"], answer_text=sub["answer_text"],
                                 evidence=sub["evidence"], task_input=sub["task_input"])
        self.assertEqual(receipt["status"], "PASS")
        report = gl.audit_report()
        self.assertEqual(report["answers_verified"], 1)
        self.assertTrue(gl.replay()["attested"])


if __name__ == "__main__":
    unittest.main()
