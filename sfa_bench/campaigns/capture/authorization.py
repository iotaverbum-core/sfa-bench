"""Execution-only authorization artifact validation.

Validation proves artifact binding. It does not prove the submitter's real-world
identity, legal authority, consent, entitlement, or provider approval.
"""
from __future__ import annotations

from typing import Any

from .adapters import CaptureAdapter, validate_adapter_identity
from .canonical import (
    CaptureError,
    assert_secret_free,
    require_exact_fields,
    sha256_bytes,
    sha256_value,
    validate_safe_id,
    validate_timestamp,
)
from .context import require_bound_reference


AUTHORIZATION_SCHEMA = "sfa_bench.campaign_capture.execution_authorization.v1"
AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "authorization_id",
        "campaign_id",
        "benchmark_lock_digest",
        "benchmark_commit",
        "verifier_commit",
        "release_identifier",
        "execution_id",
        "adapter",
        "request",
        "retry_policy",
        "operator_declaration",
        "issued_at",
        "ratification_status",
        "automatic_actions",
        "authorization_digest",
    }
)


def authorization_content(authorization: dict[str, Any]) -> dict[str, Any]:
    content = dict(authorization)
    content.pop("authorization_digest", None)
    return content


def authorization_digest(authorization: dict[str, Any]) -> str:
    return sha256_value(authorization_content(authorization))


def seal_authorization(content: dict[str, Any]) -> dict[str, Any]:
    """Seal caller-supplied content without asserting that its operator is human."""
    artifact = dict(content)
    artifact["authorization_digest"] = authorization_digest(artifact)
    return artifact


def validate_authorization(
    authorization: Any,
    *,
    campaign: dict[str, Any],
    lock: dict[str, Any],
    request_bytes: bytes,
    adapter: CaptureAdapter,
) -> dict[str, Any]:
    if not isinstance(authorization, dict):
        raise CaptureError("MALFORMED_AUTHORIZATION", "authorization must be an object")
    require_exact_fields(authorization, AUTHORIZATION_FIELDS)
    if authorization["schema_version"] != AUTHORIZATION_SCHEMA:
        raise CaptureError("UNSUPPORTED_AUTHORIZATION_SCHEMA", "unsupported authorization schema")
    validate_safe_id(authorization["authorization_id"], "$.authorization_id")
    validate_safe_id(authorization["execution_id"], "$.execution_id")
    validate_timestamp(authorization["issued_at"], "$.issued_at")
    expected_scalars = {
        "campaign_id": campaign["campaign_id"],
        "benchmark_lock_digest": lock["lock_digest"],
        "benchmark_commit": lock["repository_commit"],
        "verifier_commit": lock["verifier_commit"],
        "release_identifier": lock["release_identifier"],
    }
    for field, expected in expected_scalars.items():
        if authorization[field] != expected:
            raise CaptureError(
                "AUTHORIZATION_SCOPE_MISMATCH",
                f"authorization {field} does not match governed context",
                f"$.{field}",
            )
    adapter_identity = validate_adapter_identity(adapter)
    adapter_block = authorization["adapter"]
    if not isinstance(adapter_block, dict):
        raise CaptureError("INVALID_AUTHORIZATION_ADAPTER", "adapter scope must be an object")
    require_exact_fields(adapter_block, {"adapter_id", "adapter_version", "implementation_path"}, "$.adapter")
    if adapter_block != adapter_identity:
        raise CaptureError(
            "AUTHORIZATION_SCOPE_MISMATCH",
            "authorization does not permit this adapter identity",
            "$.adapter",
        )
    require_bound_reference(lock, adapter_block["implementation_path"], "$.adapter.implementation_path")
    request = authorization["request"]
    if not isinstance(request, dict):
        raise CaptureError("INVALID_AUTHORIZATION_REQUEST", "request scope must be an object")
    require_exact_fields(
        request,
        {"sha256", "byte_length", "prompt_reference", "case_reference"},
        "$.request",
    )
    if request["sha256"] != sha256_bytes(request_bytes) or request["byte_length"] != len(request_bytes):
        raise CaptureError(
            "AUTHORIZATION_SCOPE_MISMATCH",
            "authorization does not bind the exact outbound request bytes",
            "$.request",
        )
    require_bound_reference(lock, request["prompt_reference"], "$.request.prompt_reference")
    require_bound_reference(lock, request["case_reference"], "$.request.case_reference")
    retry = authorization["retry_policy"]
    if not isinstance(retry, dict):
        raise CaptureError("INVALID_AUTHORIZATION_RETRY", "retry policy must be an object")
    require_exact_fields(retry, {"max_attempts", "allowed_reasons"}, "$.retry_policy")
    campaign_retry = campaign["retry_policy"]
    if (
        retry["max_attempts"] != campaign_retry["max_attempts"]
        or retry["allowed_reasons"] != campaign_retry["retry_conditions"]
    ):
        raise CaptureError(
            "RETRY_POLICY_MISMATCH",
            "authorization retry policy differs from preregistration",
            "$.retry_policy",
        )
    if not isinstance(retry["max_attempts"], int) or isinstance(retry["max_attempts"], bool) or retry["max_attempts"] < 1:
        raise CaptureError("INVALID_AUTHORIZATION_RETRY", "max attempts must be positive")
    if not isinstance(retry["allowed_reasons"], list) or not all(
        isinstance(item, str) and item for item in retry["allowed_reasons"]
    ):
        raise CaptureError("INVALID_AUTHORIZATION_RETRY", "allowed reasons must be strings")
    operator = authorization["operator_declaration"]
    if not isinstance(operator, dict):
        raise CaptureError("INVALID_OPERATOR_DECLARATION", "operator declaration must be an object")
    require_exact_fields(
        operator,
        {"identity", "authority_type", "authorization_scope"},
        "$.operator_declaration",
    )
    if not isinstance(operator["identity"], str) or not operator["identity"].strip() or len(operator["identity"]) > 200:
        raise CaptureError("INVALID_OPERATOR_DECLARATION", "declared operator identity is invalid")
    if operator["authority_type"] != "declared_human_operator" or operator["authorization_scope"] != "execution_only":
        raise CaptureError(
            "AUTHORIZATION_SCOPE_MISMATCH",
            "operator declaration must be human-declared and execution-only",
            "$.operator_declaration",
        )
    if authorization["ratification_status"] != "unratified":
        raise CaptureError("AUTHORIZATION_CANNOT_RATIFY", "execution authorization cannot ratify evidence")
    automatic = authorization["automatic_actions"]
    if not isinstance(automatic, dict):
        raise CaptureError("INVALID_AUTOMATIC_ACTIONS", "automatic actions must be an object")
    require_exact_fields(automatic, {"ratify", "promote", "publish", "release"}, "$.automatic_actions")
    if any(value is not False for value in automatic.values()):
        raise CaptureError(
            "AUTOMATIC_GOVERNANCE_FORBIDDEN",
            "ratification, promotion, publication, and release must remain human-only",
            "$.automatic_actions",
        )
    assert_secret_free(authorization)
    if authorization["authorization_digest"] != authorization_digest(authorization):
        raise CaptureError("AUTHORIZATION_DIGEST_MISMATCH", "authorization seal is invalid")
    return {
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["authorization_digest"],
        "execution_id": authorization["execution_id"],
        "scope": "execution_only",
        "operator_identity_provenance": "operator_declared",
        "ratification_status": "unratified",
    }
