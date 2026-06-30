"""Reproducibility + tamper verification tests (the customer-trust path).

These assert the guarantees a skeptical stranger checks: the committed examples
re-derive to the committed manifest, the derivation is deterministic, and the
committed corrupted bundle is rejected.
"""
from __future__ import annotations

import json
import unittest

from product.groundledger import verification


class ReproducibilityTests(unittest.TestCase):
    def test_committed_fixtures_exist(self):
        self.assertTrue(verification.EXPECTED_MANIFEST.is_file(), "run: make verify-update")
        self.assertTrue(verification.TAMPERED_BUNDLE.is_file())

    def test_manifest_is_deterministic(self):
        self.assertEqual(verification.build_manifest(), verification.build_manifest())

    def test_rederived_manifest_matches_committed(self):
        expected = json.loads(verification.EXPECTED_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            verification.build_manifest(), expected,
            "re-derived output drifted from the committed manifest; "
            "if the change was intentional, run: python -m product.groundledger.verification --update",
        )

    def test_manifest_pins_tool_versions(self):
        manifest = verification.build_manifest()
        self.assertIn("groundledger", manifest["tool"])
        self.assertIn("verifier", manifest["tool"])
        self.assertEqual(manifest["rule_pack"]["id"], "insurance_v1")

    def test_full_verification_passes(self):
        result = verification.run_verification()
        self.assertTrue(result["ok"], result["issues"])

    def test_committed_tamper_fixture_is_rejected(self):
        from product.groundledger import export as export_mod

        tampered = json.loads(verification.TAMPERED_BUNDLE.read_text(encoding="utf-8"))
        verdict = export_mod.verify_bundle(tampered, signing_key=verification.SIGNING_KEY)
        self.assertFalse(verdict["verified"])
        self.assertIn("seal_broken", {i["code"] for i in verdict["issues"]})


if __name__ == "__main__":
    unittest.main()
