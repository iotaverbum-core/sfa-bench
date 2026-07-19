"""Offline tests for the execution-only OpenAI Responses adapter."""
from __future__ import annotations

import io
import json
import os
import socket
import unittest
from unittest import mock
from urllib import error

from sfa_bench.campaigns.capture.adapters import LockedCaptureRequest
from sfa_bench.campaigns.capture.openai_responses import OpenAIResponsesAdapter


REQUEST_BYTES = b'{"model":"gpt-5.6","input":"locked"}'


def locked_request() -> LockedCaptureRequest:
    return LockedCaptureRequest(
        campaign_id="campaign-1",
        execution_id="execution-1",
        attempt_number=1,
        benchmark_lock_digest="a" * 64,
        request_bytes=REQUEST_BYTES,
        prompt_reference="campaigns/prompts/system.txt",
        case_reference="cases/case-1.json",
    )


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class OpenAIResponsesAdapterTests(unittest.TestCase):
    def test_exact_locked_bytes_are_sent_and_response_is_preserved(self):
        body = json.dumps(
            {"id": "resp_1", "model": "gpt-5.6", "usage": {"input_tokens": 7, "output_tokens": 3}}
        ).encode("utf-8")
        observed = {}

        def opener(request, *, timeout):
            observed["data"] = request.data
            observed["authorization"] = request.get_header("Authorization")
            observed["timeout"] = timeout
            return FakeResponse(
                body,
                headers={"Content-Type": "application/json", "x-request-id": "req_123"},
            )

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-not-real"}, clear=False):
            result = OpenAIResponsesAdapter(opener=opener, timeout_seconds=9).transport(locked_request())

        self.assertEqual(observed["data"], REQUEST_BYTES)
        self.assertEqual(observed["authorization"], "Bearer test-key-not-real")
        self.assertEqual(observed["timeout"], 9.0)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.response_bytes, body)
        self.assertEqual(result.metadata["provider_request_id"], "req_123")
        self.assertEqual(result.metadata["provider_model_label"], "gpt-5.6")
        self.assertEqual(result.metadata["usage_input_tokens"], 7)
        self.assertEqual(result.metadata["usage_output_tokens"], 3)
        self.assertNotIn("authorization", result.metadata)

    def test_missing_key_fails_without_calling_transport(self):
        opener = mock.Mock()
        with mock.patch.dict(os.environ, {}, clear=True):
            result = OpenAIResponsesAdapter(opener=opener).transport(locked_request())
        opener.assert_not_called()
        self.assertEqual(result.status, "transport_error")
        self.assertEqual(result.diagnostic_code, "OPENAI_API_KEY_MISSING")

    def test_http_error_body_is_preserved_as_partial_evidence(self):
        problem = b'{"error":{"message":"bad request"}}'

        def opener(request, *, timeout):
            raise error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {"Content-Type": "application/json", "x-request-id": "req_bad"},
                io.BytesIO(problem),
            )

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-not-real"}, clear=False):
            result = OpenAIResponsesAdapter(opener=opener).transport(locked_request())
        self.assertEqual(result.status, "transport_error")
        self.assertEqual(result.response_bytes, problem)
        self.assertEqual(result.metadata["http_status"], 400)
        self.assertEqual(result.metadata["provider_request_id"], "req_bad")
        self.assertEqual(result.diagnostic_code, "OPENAI_HTTP_ERROR")

    def test_timeout_and_network_error_are_redacted(self):
        for exception, status, code in (
            (socket.timeout(), "timeout", "OPENAI_TIMEOUT"),
            (error.URLError("offline"), "transport_error", "OPENAI_TRANSPORT_ERROR"),
        ):
            def opener(request, *, timeout, exception=exception):
                raise exception

            with self.subTest(code=code), mock.patch.dict(
                os.environ, {"OPENAI_API_KEY": "test-key-not-real"}, clear=False
            ):
                result = OpenAIResponsesAdapter(opener=opener).transport(locked_request())
            self.assertEqual(result.status, status)
            self.assertIsNone(result.response_bytes)
            self.assertEqual(result.metadata, {})
            self.assertEqual(result.diagnostic_code, code)


if __name__ == "__main__":
    unittest.main()
