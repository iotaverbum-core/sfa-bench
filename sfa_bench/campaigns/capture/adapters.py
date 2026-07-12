"""Provider-neutral capture protocol and deterministic synthetic laboratory."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .canonical import (
    CaptureError,
    assert_no_governance_claims,
    assert_secret_free,
)


ADAPTER_PROTOCOL_VERSION = "sfa_bench.campaign_capture.adapter.v1"
SYNTHETIC_ADAPTER_ID = "sfa-synthetic-laboratory"
SYNTHETIC_ADAPTER_VERSION = "sfa_bench.synthetic_capture_adapter.v1"
SYNTHETIC_ADAPTER_PATH = "sfa_bench/campaigns/capture/adapters.py"
TRANSPORT_STATUSES = frozenset(
    {"completed", "timeout", "transport_error", "interrupted"}
)
ALLOWED_METADATA_FIELDS = frozenset(
    {
        "content_type",
        "finish_reason",
        "http_status",
        "provider_request_id",
        "provider_model_label",
        "usage_input_tokens",
        "usage_output_tokens",
    }
)


@dataclass(frozen=True)
class LockedCaptureRequest:
    campaign_id: str
    execution_id: str
    attempt_number: int
    benchmark_lock_digest: str
    request_bytes: bytes
    prompt_reference: str
    case_reference: str


@dataclass(frozen=True)
class TransportResult:
    status: str
    response_bytes: bytes | None
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostic_code: str | None = None


@runtime_checkable
class CaptureAdapter(Protocol):
    """Narrow transport-only boundary. Implementations never judge evidence."""

    adapter_id: str
    adapter_version: str
    implementation_path: str

    def transport(self, request: LockedCaptureRequest) -> TransportResult:
        ...


def validate_adapter_identity(adapter: CaptureAdapter) -> dict[str, str]:
    values = {
        "adapter_id": getattr(adapter, "adapter_id", None),
        "adapter_version": getattr(adapter, "adapter_version", None),
        "implementation_path": getattr(adapter, "implementation_path", None),
    }
    if not all(isinstance(value, str) and value for value in values.values()):
        raise CaptureError("INVALID_ADAPTER_IDENTITY", "adapter identity fields are required")
    assert_secret_free(values)
    assert_no_governance_claims(values)
    return values  # type: ignore[return-value]


def validate_transport_shape(result: Any) -> TransportResult:
    if not isinstance(result, TransportResult):
        raise CaptureError("INVALID_TRANSPORT_RESULT", "adapter must return TransportResult")
    if result.status not in TRANSPORT_STATUSES:
        raise CaptureError("INVALID_TRANSPORT_STATUS", "unknown transport status")
    if result.response_bytes is not None and not isinstance(result.response_bytes, bytes):
        raise CaptureError("INVALID_RESPONSE_BYTES", "response body must be bytes or null")
    if result.status == "completed" and result.response_bytes is None:
        raise CaptureError("MISSING_RESPONSE_BODY", "completed transport requires response bytes")
    if not isinstance(result.metadata, dict):
        raise CaptureError("INVALID_TRANSPORT_METADATA", "transport metadata must be an object")
    if result.diagnostic_code is not None and (
        not isinstance(result.diagnostic_code, str) or len(result.diagnostic_code) > 80
    ):
        raise CaptureError("INVALID_DIAGNOSTIC_CODE", "diagnostic code is invalid")
    return result


def sanitize_transport_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(metadata) - ALLOWED_METADATA_FIELDS)
    if unknown:
        raise CaptureError(
            "TRANSPORT_METADATA_NOT_ALLOWLISTED",
            "transport metadata contains non-allowlisted fields",
            f"$.metadata.{unknown[0]}",
        )
    clean: dict[str, Any] = {}
    for key in sorted(metadata):
        value = metadata[key]
        if key in {"http_status", "usage_input_tokens", "usage_output_tokens"}:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise CaptureError(
                    "INVALID_TRANSPORT_METADATA", "numeric metadata must be a nonnegative integer", f"$.metadata.{key}"
                )
        else:
            if not isinstance(value, str) or not value or len(value) > 256:
                raise CaptureError(
                    "INVALID_TRANSPORT_METADATA", "text metadata must be 1-256 characters", f"$.metadata.{key}"
                )
        clean[key] = value
    assert_secret_free(clean, "$.metadata")
    assert_no_governance_claims(clean, "$.metadata")
    return clean


class SyntheticAdapter:
    """Deterministic offline adapter covering canonical failure modes."""

    adapter_id = SYNTHETIC_ADAPTER_ID
    adapter_version = SYNTHETIC_ADAPTER_VERSION
    implementation_path = SYNTHETIC_ADAPTER_PATH

    MODES = frozenset(
        {
            "valid_json_object",
            "empty_output",
            "refusal_plaintext",
            "malformed_json",
            "non_object_json",
            "non_finite_json",
            "timeout",
            "transport_error",
            "retry",
            "duplicate_provider_identifier",
            "partial_stream",
            "interrupted_write",
            "binary_non_utf8",
            "misleading_provider_metadata",
            "credential_like_metadata",
        }
    )

    def __init__(self, mode: str) -> None:
        if mode not in self.MODES:
            raise CaptureError("UNKNOWN_SYNTHETIC_MODE", f"unknown synthetic mode {mode!r}")
        self.mode = mode
        self.calls = 0

    def transport(self, request: LockedCaptureRequest) -> TransportResult:
        if not isinstance(request, LockedCaptureRequest):
            raise CaptureError("UNLOCKED_ADAPTER_REQUEST", "adapter accepts only LockedCaptureRequest")
        self.calls += 1
        base_metadata: dict[str, Any] = {
            "content_type": "application/json",
            "http_status": 200,
            "provider_request_id": f"synthetic-{request.execution_id}-{request.attempt_number}",
            "provider_model_label": "synthetic-fixture-label",
        }
        responses = {
            "valid_json_object": b'{"claimed_state_keys":["customer_id"],"used_off_limits_keys":[]}',
            "empty_output": b"",
            "refusal_plaintext": b"I cannot comply with that request.",
            "malformed_json": b'{"claimed_state_keys":[',
            "non_object_json": b'["customer_id"]',
            "non_finite_json": b'{"value":NaN}',
            "binary_non_utf8": b"\xff\xfe\x00\x80binary",
        }
        if self.mode in responses:
            return TransportResult("completed", responses[self.mode], base_metadata)
        if self.mode == "timeout":
            return TransportResult("timeout", None, {}, "SYNTHETIC_TIMEOUT")
        if self.mode in {"transport_error", "retry"}:
            return TransportResult("transport_error", None, {}, "SYNTHETIC_TRANSPORT_ERROR")
        if self.mode == "duplicate_provider_identifier":
            base_metadata["provider_request_id"] = "synthetic-duplicate-id"
            return TransportResult("completed", responses["valid_json_object"], base_metadata)
        if self.mode in {"partial_stream", "interrupted_write"}:
            return TransportResult(
                "interrupted",
                b'{"claimed_state_keys":["customer_id"',
                {"content_type": "application/json"},
                "SYNTHETIC_INTERRUPTION",
            )
        if self.mode == "misleading_provider_metadata":
            base_metadata["provider_model_label"] = "official approved provider model"
            return TransportResult("completed", responses["valid_json_object"], base_metadata)
        if self.mode == "credential_like_metadata":
            base_metadata["authorization"] = "Bearer synthetic-secret-value-123456"
            return TransportResult("completed", responses["valid_json_object"], base_metadata)
        raise AssertionError("synthetic mode dispatch is incomplete")
