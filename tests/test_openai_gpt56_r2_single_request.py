"""Regression tests for the canonical single-request R2 entrypoint."""
from __future__ import annotations

import unittest
from unittest import mock

import openai_gpt56_r2 as core
import openai_gpt56_r2_single_request as guarded
import openai_live_pilot as base


class R2SingleRequestEntrypointTests(unittest.TestCase):
    def test_offline_model_binding_makes_no_network_call(self):
        opener = mock.Mock(side_effect=AssertionError("network preflight"))
        value = guarded._confirm_model_without_provider_request(
            "not-inspected",
            core.MODEL,
            timeout=1.0,
            opener=opener,
        )
        opener.assert_not_called()
        self.assertEqual(value["id"], core.MODEL)
        self.assertFalse(value["provider_preflight_request_sent"])
        self.assertEqual(
            value["verification"],
            "request_bound_response_label_captured",
        )

    def test_offline_binding_rejects_any_other_model(self):
        with self.assertRaises(core.HarnessError) as caught:
            guarded._confirm_model_without_provider_request(
                "not-inspected",
                "gpt-5.6-luna",
                timeout=1.0,
            )
        self.assertEqual(caught.exception.code, "R2_MODEL_SUBSTITUTION")

    def test_entrypoint_patches_preflight_and_binds_both_scripts(self):
        original_preflight = base._confirm_model_available
        original_script = core.SCRIPT_REFERENCE
        original_modules = set(core.MODULE_REFERENCES)

        def delegated(argv):
            self.assertEqual(argv, ["status"])
            self.assertIs(
                base._confirm_model_available,
                guarded._confirm_model_without_provider_request,
            )
            self.assertEqual(
                core.SCRIPT_REFERENCE,
                guarded.ENTRYPOINT_REFERENCE,
            )
            self.assertIn(
                guarded.CORE_REFERENCE,
                core.MODULE_REFERENCES,
            )
            return 7

        with mock.patch.object(core, "main", side_effect=delegated):
            self.assertEqual(guarded.main(["status"]), 7)

        self.assertIs(base._confirm_model_available, original_preflight)
        self.assertEqual(core.SCRIPT_REFERENCE, original_script)
        self.assertEqual(core.MODULE_REFERENCES, original_modules)

    def test_no_historical_preflight_is_reachable_during_delegation(self):
        historical = mock.Mock(side_effect=AssertionError("historical preflight"))
        original_preflight = base._confirm_model_available
        base._confirm_model_available = historical
        try:
            def delegated(_argv):
                value = base._confirm_model_available(
                    "not-inspected",
                    core.MODEL,
                    timeout=1.0,
                )
                self.assertFalse(value["provider_preflight_request_sent"])
                return 0

            with mock.patch.object(core, "main", side_effect=delegated):
                self.assertEqual(guarded.main(["status"]), 0)
        finally:
            base._confirm_model_available = original_preflight
        historical.assert_not_called()


if __name__ == "__main__":
    unittest.main()
