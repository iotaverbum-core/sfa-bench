"""GroundLedger SDK tests. Run: python -m unittest discover -s product -t . -p 'test_*.py'"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from product.groundledger import api, export as export_mod
from product.sdk import GroundLedgerClient, GroundLedgerError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _split(submission: dict) -> dict:
    return {
        "answer_id": submission["answer_id"],
        "candidate": submission["candidate"],
        "evidence": submission["evidence"],
        "task_input": submission.get("task_input"),
    }


class EmbeddedSdkTests(unittest.TestCase):
    def setUp(self):
        self.client = GroundLedgerClient.embedded(
            data_root=tempfile.mkdtemp(), tenant="acme", rule_pack="insurance_v1",
            signing_key="sdk-secret",
        )

    def test_grounded_and_failed_verify(self):
        ok = self.client.verify(**_split(load_example("grounded_answer.json")))
        self.assertTrue(self.client.is_grounded(ok))
        bad = self.client.verify(**_split(load_example("fabricated_citation.json")))
        self.assertFalse(self.client.is_grounded(bad))
        self.assertEqual(bad["category"], "FABRICATED_ENTITY")

    def test_report_export_and_replay(self):
        for name in ("grounded_answer.json", "contradicts_evidence.json"):
            self.client.verify(**_split(load_example(name)))
        report = self.client.audit_report()
        self.assertEqual(report["answers_verified"], 2)
        self.assertEqual(report["grounded"], 1)

        bundle = self.client.audit_export()
        verdict = export_mod.verify_bundle(bundle, signing_key="sdk-secret")
        self.assertTrue(verdict["verified"], verdict["issues"])
        self.assertTrue(verdict["signature_checked"])

        self.assertTrue(self.client.replay()["attested"])


class HttpSdkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.httpd = api.serve(host="127.0.0.1", port=0, data_root=self.tmp,
                               api_keys={"k1": "tenant-a"})
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.client = GroundLedgerClient.http(
            base_url=f"http://127.0.0.1:{self.port}", api_key="k1", rule_pack="insurance_v1"
        )

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_roundtrip_over_http(self):
        bad = self.client.verify(**_split(load_example("fabricated_citation.json")))
        self.assertEqual(bad["category"], "FABRICATED_ENTITY")
        self.assertEqual(len(self.client.receipts()), 1)

        report = self.client.audit_report()
        self.assertEqual(report["not_grounded"], 1)
        self.assertTrue(self.client.replay()["attested"])

        bundle = self.client.audit_export()
        self.assertTrue(export_mod.verify_bundle(bundle)["verified"])

    def test_bad_api_key_raises(self):
        client = GroundLedgerClient.http(
            base_url=f"http://127.0.0.1:{self.port}", api_key="nope"
        )
        with self.assertRaises(GroundLedgerError):
            client.verify(**_split(load_example("grounded_answer.json")))


if __name__ == "__main__":
    unittest.main()
