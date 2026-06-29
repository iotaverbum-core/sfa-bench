"""GroundLedger tests. Run: python -m unittest discover -s product -t . -p 'test_*.py'"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from itertools import count
from pathlib import Path

from product.groundledger import api, engine, ledger as ledger_mod, replay, report as report_mod, rulepacks
from product.groundledger.store import TenantStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def fixed_clock():
    counter = count()
    return lambda: f"2026-01-01T00:00:{next(counter):02d}+00:00"


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.pack = rulepacks.load_rule_pack("insurance_v1")

    def test_grounded_answer_passes(self):
        receipt = engine.verify_submission(load_example("grounded_answer.json"), self.pack)
        self.assertEqual(receipt["status"], "PASS")
        self.assertIsNone(receipt["family"])

    def test_fabricated_citation_is_categorized(self):
        receipt = engine.verify_submission(load_example("fabricated_citation.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "FABRICATED_ENTITY")
        self.assertEqual(receipt["family"], "fabricated_entity")

    def test_contradiction_is_categorized(self):
        receipt = engine.verify_submission(load_example("contradicts_evidence.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "CONTRADICTS_EVIDENCE")
        self.assertEqual(receipt["family"], "contradicts_evidence")

    def test_unsupported_claim_is_categorized(self):
        receipt = engine.verify_submission(load_example("unsupported_claim.json"), self.pack)
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["category"], "UNSUPPORTED_CLAIM")
        self.assertTrue(receipt["family"].startswith("unsupported"))

    def test_seal_is_deterministic(self):
        sub = load_example("grounded_answer.json")
        a = engine.verify_submission(sub, self.pack, now=fixed_clock())
        b = engine.verify_submission(sub, self.pack, now=fixed_clock())
        self.assertEqual(a["receipt_hash"], b["receipt_hash"])
        self.assertEqual(a["receipt_hash"], engine.seal_hash(a))


class LedgerAndReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = TenantStore(self.tmp, "t1")
        self.pack = rulepacks.load_rule_pack("insurance_v1")
        clock = fixed_clock()
        for name in ("grounded_answer.json", "fabricated_citation.json", "contradicts_evidence.json"):
            sub = load_example(name)
            receipt = engine.verify_submission(sub, self.pack, now=clock)
            self.store.record(sub, receipt)

    def test_chain_is_intact_and_attests(self):
        ok, errors, count_ = ledger_mod.verify_chain(str(self.store.ledger_path))
        self.assertTrue(ok, errors)
        self.assertEqual(count_, 3)
        result = replay.attest(self.store)
        self.assertTrue(result["attested"], result["issues"])

    def test_report_groundedness_rate(self):
        report = report_mod.build_report(self.store)
        self.assertEqual(report["answers_verified"], 3)
        self.assertEqual(report["grounded"], 1)
        self.assertAlmostEqual(report["groundedness_rate"], round(1 / 3, 4))
        self.assertTrue(report["attestation"]["attested"])

    def test_replay_detects_receipt_tamper(self):
        path = self.store.receipts_dir / "ans_fabricated_002.json"
        forged = json.loads(path.read_text(encoding="utf-8"))
        forged["status"] = "PASS"
        path.write_text(json.dumps(forged), encoding="utf-8")
        result = replay.attest(self.store)
        self.assertFalse(result["attested"])
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("seal_broken", codes)

    def test_replay_detects_submission_tamper(self):
        path = self.store.submissions_dir / "ans_contradicts_003.json"
        sub = json.loads(path.read_text(encoding="utf-8"))
        sub["candidate"]["claims"][0]["value"] = "$1,000"  # forge the answer to match evidence
        path.write_text(json.dumps(sub), encoding="utf-8")
        result = replay.attest(self.store)
        self.assertFalse(result["attested"])
        codes = {i["code"] for i in result["issues"]}
        self.assertIn("verdict_mismatch", codes)

    def test_ledger_line_edit_breaks_chain(self):
        lines = self.store.ledger_path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["status"] = "TAMPERED"  # any change without re-hashing must break the chain
        lines[0] = json.dumps(entry, sort_keys=True)
        self.store.ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, errors, _ = ledger_mod.verify_chain(str(self.store.ledger_path))
        self.assertFalse(ok)
        self.assertTrue(errors)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.httpd = api.serve(
            host="127.0.0.1", port=0, data_root=self.tmp, api_keys={"k1": "tenant-a"}
        )
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _request(self, method, path, body=None, key="k1"):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["X-API-Key"] = key
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    def test_verify_then_report_roundtrip(self):
        status, data = self._request("POST", "/v1/verify", load_example("fabricated_citation.json"))
        self.assertEqual(status, 200)
        self.assertEqual(data["receipt"]["category"], "FABRICATED_ENTITY")

        status, report = self._request("GET", "/v1/audit-report")
        self.assertEqual(status, 200)
        self.assertEqual(report["answers_verified"], 1)
        self.assertEqual(report["not_grounded"], 1)
        self.assertTrue(report["attestation"]["attested"])

    def test_missing_api_key_is_rejected(self):
        status, _ = self._request("GET", "/v1/receipts", key=None)
        self.assertEqual(status, 401)

    def test_healthz_is_open(self):
        status, data = self._request("GET", "/healthz", key=None)
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
