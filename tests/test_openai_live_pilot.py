"""Offline tests for the guarded OpenAI live-pilot helper."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from urllib import error

import openai_live_pilot as pilot
from sfa_bench.campaigns.protocol import validate_campaign


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class OpenAILivePilotTests(unittest.TestCase):
    def test_model_preflight_requires_exact_identity_and_hides_key(self):
        observed = {}

        def opener(request, *, timeout):
            observed["url"] = request.full_url
            observed["authorization"] = request.get_header("Authorization")
            observed["timeout"] = timeout
            return FakeResponse(b'{"id":"gpt-5.6","object":"model","owned_by":"openai"}')

        result = pilot._confirm_model_available(
            "test-key-not-real",
            "gpt-5.6",
            timeout=7,
            opener=opener,
        )
        self.assertEqual(result, {"id": "gpt-5.6", "owned_by": "openai"})
        self.assertEqual(observed["authorization"], "Bearer test-key-not-real")
        self.assertEqual(observed["timeout"], 7)
        self.assertTrue(observed["url"].endswith("/v1/models/gpt-5.6"))
        self.assertNotIn("test-key-not-real", json.dumps(result))

    def test_model_preflight_refuses_unavailable_model_without_substitution(self):
        def opener(request, *, timeout):
            raise error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                {"Content-Type": "application/json"},
                io.BytesIO(b'{"error":{"message":"not found"}}'),
            )

        with self.assertRaises(pilot.PilotError) as caught:
            pilot._confirm_model_available(
                "test-key-not-real",
                "gpt-5.6",
                timeout=7,
                opener=opener,
            )
        self.assertEqual(caught.exception.code, "OPENAI_MODEL_NOT_AVAILABLE")

    def test_request_bytes_are_deterministic_blinded_and_nonstored(self):
        first = pilot._build_request("gpt-5.6", 1000)
        second = pilot._build_request("gpt-5.6", 1000)
        self.assertEqual(first, second)
        request = json.loads(first.decode("utf-8"))
        self.assertEqual(request["model"], "gpt-5.6")
        self.assertEqual(request["max_output_tokens"], 1000)
        self.assertIs(request["store"], False)
        self.assertIn("Return a single JSON object", request["instructions"])
        self.assertIn("case-001", request["input"])
        self.assertNotIn("memory_boundary_001", request["input"])
        self.assertNotIn("memory_state_boundary", request["input"])
        self.assertNotIn("scoring_rubric", request["input"])

    def test_generated_campaign_is_preregistered_and_valid(self):
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=pilot.ROOT,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        campaign = pilot._build_campaign("gpt-5.6", head)
        self.assertEqual(validate_campaign(campaign), [])
        self.assertEqual(campaign["status"], "preregistered")
        self.assertEqual(campaign["provider_model_identifier"], "gpt-5.6")
        self.assertEqual(campaign["candidate_snapshot_or_alias_status"], "mutable_alias")
        self.assertTrue(campaign["mutable_alias_use_declared"])
        self.assertEqual(campaign["run_count"], 1)
        self.assertEqual(campaign["tool_permissions"], ["none"])
        self.assertIn(
            "sfa_bench/campaigns/capture/openai_responses.py",
            campaign["benchmark_inputs"]["adapter_paths"],
        )

    def test_default_mode_prepares_without_provider_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture_root = Path(temporary) / "runs"
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-not-real"}, clear=False), mock.patch.object(
                pilot, "_capture_root", return_value=capture_root
            ), mock.patch.object(
                pilot,
                "_confirm_model_available",
                return_value={"id": "gpt-5.6", "owned_by": "openai"},
            ), mock.patch.object(
                pilot, "initialize_run"
            ) as initialize, mock.patch.object(
                pilot, "capture_attempt"
            ) as capture, mock.patch(
                "sys.stdout", new_callable=io.StringIO
            ) as stdout:
                code = pilot.main(
                    [
                        "--operator",
                        "declared-test-operator",
                        "--execution-id",
                        "offline-prepare-1",
                        "--now",
                        "2026-07-19T21:30:00+02:00",
                    ]
                )
            self.assertEqual(code, 0)
            initialize.assert_not_called()
            capture.assert_not_called()
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "prepared")
            self.assertIs(result["live_request_sent"], False)
            self.assertNotIn("test-key-not-real", stdout.getvalue())
            pack = capture_root / "_prepared-offline-prepare-1"
            self.assertTrue((pack / "campaign.json").is_file())
            self.assertTrue((pack / "benchmark-lock.json").is_file())
            self.assertTrue((pack / "execution-authorization.json").is_file())
            self.assertTrue((pack / "request.json").is_file())

    def test_execute_mode_dispatches_exactly_one_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture_root = Path(temporary) / "runs"
            run_dir = capture_root / pilot.CAMPAIGN_ID / "offline-execute-1"
            attempt = {
                "attempt_number": 1,
                "transport_status": "completed",
                "complete": True,
                "warnings": [],
            }
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-not-real"}, clear=False), mock.patch.object(
                pilot, "_capture_root", return_value=capture_root
            ), mock.patch.object(
                pilot,
                "_confirm_model_available",
                return_value={"id": "gpt-5.6", "owned_by": "openai"},
            ), mock.patch.object(
                pilot, "initialize_run", return_value=run_dir
            ) as initialize, mock.patch.object(
                pilot, "capture_attempt", return_value=attempt
            ) as capture, mock.patch(
                "sys.stdout", new_callable=io.StringIO
            ) as stdout:
                code = pilot.main(
                    [
                        "--operator",
                        "declared-test-operator",
                        "--execution-id",
                        "offline-execute-1",
                        "--now",
                        "2026-07-19T21:31:00+02:00",
                        "--execute",
                    ]
                )
            self.assertEqual(code, 0)
            initialize.assert_called_once()
            capture.assert_called_once()
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "captured")
            self.assertIs(result["live_request_sent"], True)
            self.assertEqual(result["attempt_number"], 1)
            self.assertNotIn("test-key-not-real", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
