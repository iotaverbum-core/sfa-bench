"""Healthcare rule-pack tests. Run: python -m unittest discover -s product -t . -p 'test_*.py'"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.groundledger import engine, rulepacks
from product.sdk import GroundLedgerClient

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class HealthcarePackTests(unittest.TestCase):
    def setUp(self):
        self.pack = rulepacks.load_rule_pack("healthcare_v1")

    def test_pack_is_listed_with_the_others(self):
        ids = {p["rule_pack_id"] for p in rulepacks.list_rule_packs()}
        self.assertTrue({"insurance_v1", "fintech_v1", "healthcare_v1"}.issubset(ids))

    def test_structured_grounded_passes(self):
        receipt = engine.verify_submission(load_example("healthcare_grounded.json"), self.pack)
        self.assertEqual(receipt["status"], "PASS")

    def test_structured_contradiction_flagged(self):
        receipt = engine.verify_submission(load_example("healthcare_contradicts.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "CONTRADICTS_EVIDENCE")

    def test_free_text_fabricated_citation_flagged(self):
        receipt, stored = engine.verify_text_submission(
            load_example("text_healthcare_fabricated.json"), self.pack
        )
        self.assertEqual(receipt["category"], "FABRICATED_ENTITY")
        # the extractor still read the contradicted copay from the prose
        self.assertIn(
            {"subject": "copay_primary_care", "value": "$10"}, stored["candidate"]["claims"]
        )

    def test_embedded_sdk_with_healthcare_pack(self):
        gl = GroundLedgerClient.embedded(
            data_root=tempfile.mkdtemp(), tenant="payer", rule_pack="healthcare_v1"
        )
        sub = load_example("healthcare_contradicts.json")
        receipt = gl.verify(
            answer_id=sub["answer_id"], candidate=sub["candidate"],
            evidence=sub["evidence"], task_input=sub["task_input"],
        )
        self.assertEqual(receipt["category"], "CONTRADICTS_EVIDENCE")
        self.assertTrue(gl.replay()["attested"])


if __name__ == "__main__":
    unittest.main()
