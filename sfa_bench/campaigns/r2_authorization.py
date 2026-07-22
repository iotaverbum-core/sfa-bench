"""Canonical per-block authority records for the frozen R2 study."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    assert_secret_free,
    ensure_no_reparse_ancestors,
    require_exact_fields,
    require_object,
    sha256_value,
    strict_json_file,
    validate_safe_id,
    validate_timestamp,
    write_exclusive_json,
)
from sfa_bench.campaigns.r2_harness_plan import (
    block_authorization_path,
    harness_root,
    slots_for_block,
)
from sfa_bench.campaigns.r2_plan import STUDY_ID
from sfa_bench.campaigns.r2_state import next_pending_slot, scan_slot_states

BLOCK_AUTHORIZATION_SCHEMA = (
    "sfa_bench.openai_gpt56_sol_memory_boundary_r2.block_authorization.v1"
)
FIELDS = frozenset(
    {
        "schema_version",
        "authorization_id",
        "issued_at",
        "study_id",
        "preregistration_reference",
        "preregistration_sha256",
        "slot_plan_sha256",
        "block",
        "authorized_slots",
        "operator_declaration",
        "rationale",
        "execution_policy",
        "authority_scope",
        "authorization_sha256",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_provider_requests_for_declared_slots",
        "automatic_judgment",
        "automatic_ratification",
        "model_endorsement",
        "promotion",
        "publication",
        "ranking",
        "release",
        "regulatory_or_legal_approval",
    }
)
EXECUTION_POLICY = {
    "fixed_order": True,
    "max_attempts_per_slot": 1,
    "provider_requests_per_slot": 1,
    "replacement_slots": False,
    "silent_model_substitution": False,
    "store": False,
    "tools": "none",
}


def _digest(value: dict[str, Any]) -> str:
    content = dict(value)
    content.pop("authorization_sha256", None)
    return sha256_value(content)


def build_block_authorization(
    repo_root: Path,
    *,
    plan: dict[str, Any],
    block: int,
    operator: str,
    rationale: str,
    issued_at: str,
) -> dict[str, Any]:
    next_slot = next_pending_slot(scan_slot_states(repo_root, plan))
    if next_slot is None:
        raise CaptureError("R2_ALREADY_COMPLETE", "all 48 slots are occupied")
    if next_slot["block"] != block:
        raise CaptureError(
            "R2_BLOCK_OUT_OF_ORDER",
            f"next authorizable block is {next_slot['block']}, not {block}",
        )
    if (
        not isinstance(operator, str)
        or not operator.strip()
        or len(operator.strip()) > 200
    ):
        raise CaptureError(
            "INVALID_OPERATOR",
            "operator identity must contain 1-200 characters",
        )
    if (
        not isinstance(rationale, str)
        or not rationale.strip()
        or len(rationale.strip()) > 2000
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_RATIONALE_REQUIRED",
            "authorization requires a 1-2000 character rationale",
        )
    validate_timestamp(issued_at, "$.issued_at")
    value: dict[str, Any] = {
        "schema_version": BLOCK_AUTHORIZATION_SCHEMA,
        "authorization_id": f"auth-gpt56-sol-r2-block-{block:03d}",
        "issued_at": issued_at,
        "study_id": STUDY_ID,
        "preregistration_reference": plan["preregistration_reference"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "slot_plan_sha256": plan["slot_plan_sha256"],
        "block": block,
        "authorized_slots": slots_for_block(plan, block),
        "operator_declaration": {
            "identity": operator.strip(),
            "authority_type": "declared_human_operator",
            "authorization_scope": "one_preregistered_block_only",
        },
        "rationale": rationale.strip(),
        "execution_policy": dict(EXECUTION_POLICY),
        "authority_scope": {
            "authorizes_provider_requests_for_declared_slots": True,
            "automatic_judgment": False,
            "automatic_ratification": False,
            "model_endorsement": False,
            "promotion": False,
            "publication": False,
            "ranking": False,
            "release": False,
            "regulatory_or_legal_approval": False,
        },
    }
    value["authorization_sha256"] = _digest(value)
    return verify_block_authorization(value, plan)


def verify_block_authorization(
    value: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    require_exact_fields(value, FIELDS)
    if (
        value.get("schema_version") != BLOCK_AUTHORIZATION_SCHEMA
        or value.get("study_id") != STUDY_ID
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_IDENTITY_MISMATCH",
            "authorization identity changed",
        )
    validate_safe_id(value.get("authorization_id"), "$.authorization_id")
    validate_timestamp(value.get("issued_at"), "$.issued_at")
    if value.get("authorization_sha256") != _digest(value):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_DIGEST_MISMATCH",
            "authorization was modified",
        )
    if (
        value.get("preregistration_reference")
        != plan["preregistration_reference"]
        or value.get("preregistration_sha256")
        != plan["preregistration_sha256"]
        or value.get("slot_plan_sha256") != plan["slot_plan_sha256"]
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_PLAN_MISMATCH",
            "authorization binds another plan",
        )
    block = value.get("block")
    if value.get("authorized_slots") != slots_for_block(plan, block):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_SLOT_MISMATCH",
            "authorization slot scope changed",
        )
    operator = require_object(
        value.get("operator_declaration"),
        "$.operator_declaration",
    )
    require_exact_fields(
        operator,
        {"identity", "authority_type", "authorization_scope"},
        "$.operator_declaration",
    )
    if (
        operator.get("authority_type") != "declared_human_operator"
        or operator.get("authorization_scope")
        != "one_preregistered_block_only"
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_SCOPE_MISMATCH",
            "operator scope changed",
        )
    identity = operator.get("identity")
    if (
        not isinstance(identity, str)
        or not identity.strip()
        or len(identity) > 200
    ):
        raise CaptureError(
            "INVALID_OPERATOR",
            "stored operator identity is invalid",
        )
    rationale = value.get("rationale")
    if (
        not isinstance(rationale, str)
        or not rationale.strip()
        or len(rationale) > 2000
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_RATIONALE_REQUIRED",
            "stored rationale is invalid",
        )
    if value.get("execution_policy") != EXECUTION_POLICY:
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_POLICY_MISMATCH",
            "execution policy changed",
        )
    authority = require_object(
        value.get("authority_scope"),
        "$.authority_scope",
    )
    require_exact_fields(
        authority,
        AUTHORITY_FIELDS,
        "$.authority_scope",
    )
    if (
        authority.get("authorizes_provider_requests_for_declared_slots")
        is not True
    ):
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_SCOPE_MISMATCH",
            "declared slots are not explicitly authorized",
        )
    for field in AUTHORITY_FIELDS - {
        "authorizes_provider_requests_for_declared_slots"
    }:
        if authority.get(field) is not False:
            raise CaptureError(
                "R2_BLOCK_AUTHORIZATION_AUTHORITY_OVERREACH",
                "authorization claims forbidden authority",
                f"$.authority_scope.{field}",
            )
    assert_secret_free(value)
    return value


def write_block_authorization(
    repo_root: Path,
    value: dict[str, Any],
    plan: dict[str, Any],
) -> Path:
    verify_block_authorization(value, plan)
    path = write_exclusive_json(
        block_authorization_path(repo_root, value["block"]),
        value,
    )
    stored = read_block_authorization(repo_root, path.absolute(), plan)
    if stored != value:
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_WRITE_MISMATCH",
            "stored authorization differs from the verified value",
            str(path),
        )
    return path


def read_block_authorization(
    repo_root: Path,
    path: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    candidate = path.absolute()
    ensure_no_reparse_ancestors(harness_root(repo_root), candidate)
    value = require_object(
        strict_json_file(candidate, require_canonical=True),
        "$.block_authorization",
    )
    verify_block_authorization(value, plan)
    expected = block_authorization_path(repo_root, value["block"]).absolute()
    if candidate != expected:
        raise CaptureError(
            "R2_BLOCK_AUTHORIZATION_PATH_MISMATCH",
            "canonical stored authorization path required",
            str(path),
        )
    return value
