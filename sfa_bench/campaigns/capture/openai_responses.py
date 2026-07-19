"""Execution-only OpenAI Responses API transport adapter.

The adapter transmits the exact request bytes already bound by an SFA-Bench
execution authorization. It does not construct prompts, retry automatically,
judge outputs, ratify evidence, or mutate benchmark policy.
"""
from __future__ import annotations

import json
import os
import socket
from typing import Any, Callable
from urllib import error, request as urllib_request

from .adapters import LockedCaptureRequest, TransportResult
from .canonical import CaptureError

OPENAI_ADAPTER_ID = "openai-responses-api"
OPENAI_ADAPTER_VERSION = "sfa_bench.openai_responses_adapter.v1"
OPENAI_ADAPTER_PATH = "sfa_bench/campaigns/capture/openai_responses.py"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
DEFAULT_TIMEOUT_SECONDS = 120.0


def _safe_header(headers: Any, name: str) -> str | None:
    value = headers.get(name) if headers is not None else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:256] if value else None


def _usage_metadata(response_bytes: bytes) -> dict[str, int]:
    try:
        body = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(body, dict) or not isinstance(body.get("usage"), dict):
        return {}
    usage = body["usage"]
    result: dict[str, int] = {}
    for source, target in (
        ("input_tokens", "usage_input_tokens"),
        ("output_tokens", "usage_output_tokens"),
    ):
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[target] = value
    return result


def _model_metadata(response_bytes: bytes) -> str | None:
    try:
        body = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    value = body.get("model") if isinstance(body, dict) else None
    return value[:256] if isinstance(value, str) and value else None


class OpenAIResponsesAdapter:
    """Narrow stdlib-only transport for the OpenAI Responses API."""

    adapter_id = OPENAI_ADAPTER_ID
    adapter_version = OPENAI_ADAPTER_VERSION
    implementation_path = OPENAI_ADAPTER_PATH

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Callable[..., Any] = urllib_request.urlopen,
    ) -> None:
        if endpoint != DEFAULT_ENDPOINT:
            raise CaptureError("OPENAI_ENDPOINT_NOT_ALLOWED", "only the official Responses endpoint is allowed")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise CaptureError("INVALID_OPENAI_TIMEOUT", "timeout must be a positive number")
        self.api_key_env = api_key_env
        self.endpoint = endpoint
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener

    def transport(self, locked: LockedCaptureRequest) -> TransportResult:
        if not isinstance(locked, LockedCaptureRequest):
            raise CaptureError("UNLOCKED_ADAPTER_REQUEST", "adapter accepts only LockedCaptureRequest")
        api_key = os.environ.get(self.api_key_env)
        if not isinstance(api_key, str) or not api_key.strip():
            return TransportResult("transport_error", None, {}, "OPENAI_API_KEY_MISSING")

        outbound = urllib_request.Request(
            self.endpoint,
            data=locked.request_bytes,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(outbound, timeout=self.timeout_seconds) as response:
                response_bytes = response.read()
                status = int(getattr(response, "status", 200))
                metadata: dict[str, Any] = {
                    "content_type": _safe_header(response.headers, "Content-Type") or "application/json",
                    "http_status": status,
                }
                provider_request_id = _safe_header(response.headers, "x-request-id")
                if provider_request_id:
                    metadata["provider_request_id"] = provider_request_id
                model = _model_metadata(response_bytes)
                if model:
                    metadata["provider_model_label"] = model
                metadata.update(_usage_metadata(response_bytes))
                if 200 <= status < 300:
                    return TransportResult("completed", response_bytes, metadata)
                return TransportResult("transport_error", response_bytes, metadata, "OPENAI_HTTP_ERROR")
        except error.HTTPError as exc:
            response_bytes = exc.read()
            metadata = {
                "content_type": _safe_header(exc.headers, "Content-Type") or "application/json",
                "http_status": int(exc.code),
            }
            provider_request_id = _safe_header(exc.headers, "x-request-id")
            if provider_request_id:
                metadata["provider_request_id"] = provider_request_id
            return TransportResult("transport_error", response_bytes, metadata, "OPENAI_HTTP_ERROR")
        except (TimeoutError, socket.timeout):
            return TransportResult("timeout", None, {}, "OPENAI_TIMEOUT")
        except (error.URLError, OSError):
            return TransportResult("transport_error", None, {}, "OPENAI_TRANSPORT_ERROR")
