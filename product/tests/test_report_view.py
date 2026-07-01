"""Browser report-view UI tests (server-rendered HTML)."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from product.groundledger import api

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class ReportViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.httpd = api.serve(host="127.0.0.1", port=0, data_root=self.tmp, api_keys={"k1": "t"})
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _get(self, path, key_header=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"X-API-Key": key_header} if key_header else {}
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        ctype = resp.getheader("Content-Type")
        conn.close()
        return resp.status, ctype, body

    def _post(self, path, payload, key="k1"):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, body=json.dumps(payload),
                     headers={"X-API-Key": key, "Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()

    def test_index_page_is_open_html(self):
        status, ctype, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("GroundLedger", body)
        self.assertIn("<form", body)  # key entry form

    def test_report_view_requires_key(self):
        status, ctype, body = self._get("/v1/report.html")
        self.assertEqual(status, 401)
        self.assertIn("text/html", ctype)
        self.assertIn("API key required", body)

    def test_report_view_via_query_key_renders_findings(self):
        self._post("/v1/verify", load_example("fabricated_citation.json"))
        # non-engineer opens a link in a browser: key in the query string, no header
        status, ctype, body = self._get("/v1/report.html?key=k1")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("GroundLedger Audit Report", body)
        self.assertIn("Fabricated citation", body)
        self.assertIn("VERIFIED", body)

    def test_report_view_via_header_key(self):
        self._post("/v1/verify", load_example("grounded_answer.json"))
        status, _ctype, body = self._get("/v1/report.html", key_header="k1")
        self.assertEqual(status, 200)
        self.assertIn("GroundLedger Audit Report", body)

    def test_report_view_empty_tenant_renders(self):
        status, _ctype, body = self._get("/v1/report.html?key=k1")
        self.assertEqual(status, 200)
        self.assertIn("GroundLedger Audit Report", body)


if __name__ == "__main__":
    unittest.main()
