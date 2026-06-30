"""Bulk-ingest tests (CSV/JSONL onboarding path)."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from product.groundledger import api, ingest
from product.sdk import GroundLedgerClient

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


class ParseTests(unittest.TestCase):
    def test_parse_jsonl_example(self):
        parsed = ingest.parse_source(EXAMPLES / "batch.jsonl")
        self.assertEqual(len(parsed), 4)
        self.assertTrue(all(err is None for _ref, _sub, err in parsed))

    def test_parse_csv_example(self):
        parsed = ingest.parse_source(EXAMPLES / "batch.csv")
        self.assertEqual(len(parsed), 2)
        subs = [sub for _ref, sub, err in parsed]
        self.assertIn("candidate", subs[0])      # structured row
        self.assertIn("answer_text", subs[1])     # free-text row
        self.assertEqual(subs[1]["rule_pack"], "fintech_v1")

    def test_unknown_extension_requires_format(self):
        # A .py file cannot have its format inferred -> must pass --format.
        with self.assertRaises(ValueError):
            ingest.parse_source(__file__)
        # ...but an explicit format parses it as text lines.
        parsed = ingest.parse_source(EXAMPLES / "batch.jsonl", fmt="jsonl")
        self.assertEqual(len(parsed), 4)


class IngestFileTests(unittest.TestCase):
    def test_jsonl_ingests_structured_and_text(self):
        tmp = Path(tempfile.mkdtemp())
        store, result = ingest.ingest_file(EXAMPLES / "batch.jsonl", tenant="t", data_root=tmp)
        self.assertEqual(result["ingested"], 4)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["summary"]["total"], 4)
        # batch_001 (structured) and batch_003 (free text) are grounded; the two
        # fabricated-citation answers fail.
        self.assertEqual(result["summary"]["passed"], 2)
        self.assertEqual(result["summary"]["failed"], 2)
        self.assertEqual(len(store.read_ledger()), 4)

    def test_csv_ingests(self):
        tmp = Path(tempfile.mkdtemp())
        _store, result = ingest.ingest_file(EXAMPLES / "batch.csv", tenant="t", data_root=tmp)
        self.assertEqual(result["ingested"], 2)
        self.assertEqual(result["errors"], [])

    def test_rerun_skips_existing(self):
        tmp = Path(tempfile.mkdtemp())
        ingest.ingest_file(EXAMPLES / "batch.jsonl", tenant="t", data_root=tmp)
        _store, again = ingest.ingest_file(EXAMPLES / "batch.jsonl", tenant="t", data_root=tmp)
        self.assertEqual(again["ingested"], 0)
        self.assertEqual(again["skipped"], 4)

    def test_duplicate_in_file_is_error(self):
        tmp = Path(tempfile.mkdtemp())
        line = json.dumps({
            "answer_id": "dup", "rule_pack": "insurance_v1",
            "candidate": {"conclusion": "x", "cited_evidence": [], "claims": []},
            "evidence": {"documents": [], "facts": []},
        })
        path = _write(tmp, "dup.jsonl", line + "\n" + line + "\n")
        _store, result = ingest.ingest_file(path, tenant="t", data_root=tmp / "d")
        self.assertEqual(result["ingested"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("duplicate", result["errors"][0]["error"])

    def test_malformed_row_is_captured_not_fatal(self):
        tmp = Path(tempfile.mkdtemp())
        good = json.dumps({
            "answer_id": "ok", "rule_pack": "insurance_v1",
            "candidate": {"conclusion": "x", "cited_evidence": [], "claims": []},
            "evidence": {"documents": [], "facts": []},
        })
        path = _write(tmp, "mixed.jsonl", good + "\n{not valid json\n")
        _store, result = ingest.ingest_file(path, tenant="t", data_root=tmp / "d")
        self.assertEqual(result["ingested"], 1)
        self.assertEqual(len(result["errors"]), 1)


class SdkIngestTests(unittest.TestCase):
    def test_embedded_ingest_file(self):
        gl = GroundLedgerClient.embedded(data_root=tempfile.mkdtemp(), tenant="t", rule_pack="insurance_v1")
        result = gl.ingest_file(str(EXAMPLES / "batch.jsonl"))
        self.assertEqual(result["ingested"], 4)
        self.assertTrue(gl.replay()["attested"])

    def test_http_ingest_records(self):
        httpd = api.serve(host="127.0.0.1", port=0, data_root=tempfile.mkdtemp(), api_keys={"k": "t"})
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            gl = GroundLedgerClient.http(base_url=f"http://127.0.0.1:{port}", api_key="k")
            records = [sub for _ref, sub, _err in ingest.parse_source(EXAMPLES / "batch.jsonl")]
            result = gl.ingest_records(records)
            self.assertEqual(result["ingested"], 4)
            report = gl.audit_report()
            self.assertEqual(report["answers_verified"], 4)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
