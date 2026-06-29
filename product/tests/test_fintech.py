"""Fintech rule-pack tests. Run: python -m unittest discover -s product -t . -p 'test_*.py'"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from product.groundledger import api, engine, rulepacks
from product.sdk import GroundLedgerClient

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class FintechPackTests(unittest.TestCase):
    def setUp(self):
        self.pack = rulepacks.load_rule_pack("fintech_v1")

    def test_pack_loads_and_is_listed_alongside_insurance(self):
        ids = {p["rule_pack_id"] for p in rulepacks.list_rule_packs()}
        self.assertIn("fintech_v1", ids)
        self.assertIn("insurance_v1", ids)

    def test_structured_grounded_passes(self):
        receipt = engine.verify_submission(load_example("fintech_grounded.json"), self.pack)
        self.assertEqual(receipt["status"], "PASS")

    def test_structured_contradiction_flagged(self):
        receipt = engine.verify_submission(load_example("fintech_contradicts.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "CONTRADICTS_EVIDENCE")

    def test_free_text_fabricated_citation_flagged(self):
        receipt, stored = engine.verify_text_submission(
            load_example("text_fintech_fabricated.json"), self.pack
        )
        self.assertEqual(receipt["category"], "FABRICATED_ENTITY")
        # the extractor still read the contradicted APR from the prose
        self.assertIn(
            {"subject": "purchase_apr", "value": "19.99%"}, stored["candidate"]["claims"]
        )


class FintechViaSdkAndApiTests(unittest.TestCase):
    def test_embedded_sdk_with_fintech_pack(self):
        gl = GroundLedgerClient.embedded(
            data_root=tempfile.mkdtemp(), tenant="bank", rule_pack="fintech_v1"
        )
        sub = load_example("fintech_contradicts.json")
        receipt = gl.verify(
            answer_id=sub["answer_id"], candidate=sub["candidate"],
            evidence=sub["evidence"], task_input=sub["task_input"],
        )
        self.assertEqual(receipt["category"], "CONTRADICTS_EVIDENCE")
        self.assertTrue(gl.replay()["attested"])

    def test_rule_packs_endpoint_lists_both(self):
        httpd = api.serve(host="127.0.0.1", port=0, data_root=tempfile.mkdtemp(),
                          api_keys={"k": "t"})
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            gl = GroundLedgerClient.http(base_url=f"http://127.0.0.1:{port}", api_key="k")
            ids = {p["rule_pack_id"] for p in gl._t._request("GET", "/v1/rule-packs")["rule_packs"]}
        finally:
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual({"insurance_v1", "fintech_v1"}, ids)


if __name__ == "__main__":
    unittest.main()
