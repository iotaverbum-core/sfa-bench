"""Phase 1 demo / productised-report tests.

These protect the product promise a founder sells on: the report is
customer-readable (plain-language summary + severity-ranked findings +
recommended actions), the demo produces shareable artifacts, and the audit
trail stays tamper-evident.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from itertools import count
from pathlib import Path

from product import demo
from product.groundledger import engine, export as export_mod, findings, report as report_mod, rulepacks
from product.groundledger.store import TenantStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def fixed_clock():
    counter = count()
    return lambda: f"2026-01-01T00:00:{next(counter):02d}+00:00"


class FindingsTests(unittest.TestCase):
    def test_known_families_map_to_severity(self):
        self.assertEqual(findings.describe("FABRICATED_ENTITY", "fabricated_entity")["severity"], "critical")
        self.assertEqual(findings.describe("CONTRADICTS_EVIDENCE", "contradicts_evidence")["severity"], "critical")
        self.assertEqual(findings.describe("MISSING_REQUIRED_FIELD", "missing_required_field")["severity"], "medium")

    def test_unsupported_refinements_fall_back(self):
        described = findings.describe("UNSUPPORTED_CLAIM", "unsupported_number")
        self.assertEqual(described["severity"], "high")
        self.assertEqual(described["title"], "Unsupported claim")

    def test_unknown_uses_default(self):
        described = findings.describe(None, None)
        self.assertIn("recommended_action", described)


class ProductisedReportTests(unittest.TestCase):
    def setUp(self):
        self.store = TenantStore(tempfile.mkdtemp(), "acme")
        pack = rulepacks.load_rule_pack("insurance_v1")
        clock = fixed_clock()
        for name in ("grounded_answer.json", "fabricated_citation.json", "contradicts_evidence.json"):
            sub = load_example(name)
            self.store.record(sub, engine.verify_submission(sub, pack, now=clock))

    def test_report_has_plain_language_and_findings(self):
        report = report_mod.build_report(self.store, now=fixed_clock())
        self.assertIn("grounded in the provided evidence", report["summary"])
        self.assertEqual(len(report["findings"]), 2)
        first = report["findings"][0]
        for key in ("severity", "title", "why_it_matters", "recommended_action", "detected"):
            self.assertIn(key, first)
        # critical findings sort ahead of high
        self.assertEqual(first["severity"], "critical")
        self.assertEqual(report["severity_counts"].get("critical"), 2)

    def test_findings_carry_question_and_answer_context(self):
        report = report_mod.build_report(self.store, now=fixed_clock())
        fab = next(f for f in report["findings"] if f["family"] == "fabricated_entity")
        self.assertTrue(fab["question"])
        self.assertTrue(fab["assistant_answer"])

    def test_html_is_customer_readable(self):
        bundle = export_mod.build_export_bundle(self.store, now=fixed_clock())
        html = export_mod.render_html(bundle)
        for token in ("GroundLedger Audit Report", "grounded", "Recommended action",
                      "Why it matters", "VERIFIED", "sev-critical"):
            self.assertIn(token, html)

    def test_backward_compatible_keys_present(self):
        report = report_mod.build_report(self.store, now=fixed_clock())
        for key in ("answers_verified", "grounded", "not_grounded", "groundedness_rate", "attestation"):
            self.assertIn(key, report)


class DemoArtifactTests(unittest.TestCase):
    def test_demo_writes_verifiable_artifacts(self):
        out = Path(tempfile.mkdtemp()) / "demo"
        with contextlib.redirect_stdout(io.StringIO()):
            code = demo.main(out_dir=out)
        self.assertEqual(code, 0)  # tamper at the end is expected and reported, not failed

        html_path = out / "report.html"
        bundle_path = out / "bundle.json"
        self.assertTrue(html_path.is_file())
        self.assertTrue(bundle_path.is_file())
        self.assertIn("GroundLedger Audit Report", html_path.read_text(encoding="utf-8"))

        # The bundle was written on the clean ledger, so it still verifies.
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        result = export_mod.verify_bundle(bundle, signing_key=demo.DEMO_SIGNING_KEY)
        self.assertTrue(result["verified"], result["issues"])
        self.assertEqual(result["entries_checked"], 4)


if __name__ == "__main__":
    unittest.main()
