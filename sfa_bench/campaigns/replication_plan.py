"""Fixed slot-plan derivation for the GPT-5.6 repeated-execution replication."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    assert_secret_free,
    canonical_bytes,
    require_exact_fields,
    require_object,
    sha256_value,
    strict_json_file,
    validate_safe_id,
    validate_timestamp,
    write_exclusive_json,
)

PLAN_SCHEMA = "sfa_bench.openai_gpt56_replication.slot_plan.v1"
PREREGISTRATION_SCHEMA = "sfa_bench.openai_gpt56_memory_boundary_replication.v1"
PREREGISTRATION_REFERENCE = "campaigns/examples/openai-gpt56-memory-boundary-replication-r1.json"
REPLICATION_ID = "openai-gpt56-memory-boundary-replication-r1"
MODEL_ORDER = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
MODEL_TO_TIER = {model: model.rsplit("-", 1)[-1] for model in MODEL_ORDER}
PLAN_FIELDS = frozenset({
    "schema_version", "replication_id", "preregistration_reference",
    "preregistration_sha256", "slot_count", "block_count", "slots",
    "slot_plan_sha256",
})
SLOT_FIELDS = frozenset({
    "global_slot", "slot_id", "block", "position", "model", "tier",
    "within_tier_sequence", "campaign_id", "execution_id",
})


def _digest(value: dict[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return sha256_value(content)


def harness_root(repo_root: Path) -> Path:
    configured = os.environ.get("SFA_REPLICATION_HARNESS_ROOT")
    base = Path(configured).absolute() if configured else repo_root / "out" / "replication_harness"
    return base / REPLICATION_ID


def capture_root(repo_root: Path) -> Path:
    configured = os.environ.get("SFA_CAMPAIGN_CAPTURE_ROOT")
    return Path(configured).absolute() if configured else repo_root / "out" / "campaign_runs"


def slot_plan_path(repo_root: Path) -> Path:
    return harness_root(repo_root) / "slot-plan.json"


def block_authorization_path(repo_root: Path, block: int) -> Path:
    return harness_root(repo_root) / "block-authorizations" / f"block-{block:03d}.json"


def validate_preregistration(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != PREREGISTRATION_SCHEMA:
        raise CaptureError("UNSUPPORTED_REPLICATION_PREREGISTRATION", "unsupported replication preregistration schema")
    if document.get("replication_id") != REPLICATION_ID or document.get("status") != "preregistered":
        raise CaptureError("REPLICATION_PREREGISTRATION_IDENTITY_MISMATCH", "replication identity or status changed")
    policy = require_object(document.get("execution_policy"), "$.execution_policy")
    expected = {
        "automatic_retry": False,
        "max_attempts_per_execution": 1,
        "outcome_dependent_order_changes": False,
        "replacement_executions": False,
        "silent_model_substitution": False,
        "store": False,
        "tools": "none",
    }
    for field, value in expected.items():
        if policy.get(field) != value:
            raise CaptureError("REPLICATION_EXECUTION_POLICY_MISMATCH", f"execution policy changed: {field}")
    stopping = require_object(document.get("stopping_rule"), "$.stopping_rule")
    if stopping.get("planned_authorized_executions") != 30 or stopping.get("optional_stopping") is not False:
        raise CaptureError("REPLICATION_STOPPING_RULE_MISMATCH", "stopping rule must remain fixed at 30 slots")
    models = document.get("models")
    if not isinstance(models, list) or len(models) != 3:
        raise CaptureError("REPLICATION_MODEL_SET_MISMATCH", "exactly three model declarations are required")
    declared: dict[str, dict[str, Any]] = {}
    for raw in models:
        item = require_object(raw, "$.models[]")
        model = item.get("provider_model_identifier")
        if model not in MODEL_ORDER or model in declared:
            raise CaptureError("REPLICATION_MODEL_SET_MISMATCH", "exact model aliases changed")
        if item.get("planned_authorized_executions") != 10 or item.get("mutable_alias_use_declared") is not True:
            raise CaptureError("REPLICATION_MODEL_PLAN_MISMATCH", f"model plan changed for {model}")
        validate_safe_id(item.get("campaign_id"), "$.models[].campaign_id")
        declared[model] = item
    if set(declared) != set(MODEL_ORDER):
        raise CaptureError("REPLICATION_MODEL_SET_MISMATCH", "exact model aliases changed")
    blocks = document.get("execution_blocks")
    if not isinstance(blocks, list) or len(blocks) != 10:
        raise CaptureError("REPLICATION_BLOCK_PLAN_MISMATCH", "ten blocks are required")
    counts = {model: 0 for model in MODEL_ORDER}
    for expected_block, raw in enumerate(blocks, start=1):
        block = require_object(raw, f"$.execution_blocks[{expected_block - 1}]")
        order = block.get("order")
        if block.get("block") != expected_block or not isinstance(order, list) or len(order) != 3 or set(order) != set(MODEL_ORDER):
            raise CaptureError("REPLICATION_BLOCK_PLAN_MISMATCH", f"block {expected_block} changed")
        for model in order:
            counts[model] += 1
    if any(value != 10 for value in counts.values()):
        raise CaptureError("REPLICATION_BLOCK_BALANCE_MISMATCH", "each model must appear ten times")
    if document.get("execution_id_rule") != "openai-gpt56-{tier}-replication-r1-{within_tier_sequence:03d}":
        raise CaptureError("REPLICATION_EXECUTION_ID_RULE_MISMATCH", "execution ID rule changed")
    return document


def load_preregistration(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PREREGISTRATION_REFERENCE
    return validate_preregistration(require_object(strict_json_file(path), "$.preregistration"))


def build_slot_plan_unverified(repo_root: Path) -> dict[str, Any]:
    prereg = load_preregistration(repo_root)
    campaigns = {item["provider_model_identifier"]: item["campaign_id"] for item in prereg["models"]}
    counts = {model: 0 for model in MODEL_ORDER}
    slots: list[dict[str, Any]] = []
    for block in prereg["execution_blocks"]:
        for position, model in enumerate(block["order"], start=1):
            counts[model] += 1
            tier = MODEL_TO_TIER[model]
            global_slot = len(slots) + 1
            slots.append({
                "global_slot": global_slot,
                "slot_id": f"slot-{global_slot:03d}",
                "block": block["block"],
                "position": position,
                "model": model,
                "tier": tier,
                "within_tier_sequence": counts[model],
                "campaign_id": campaigns[model],
                "execution_id": f"openai-gpt56-{tier}-replication-r1-{counts[model]:03d}",
            })
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "replication_id": REPLICATION_ID,
        "preregistration_reference": PREREGISTRATION_REFERENCE,
        "preregistration_sha256": sha256_value(prereg),
        "slot_count": 30,
        "block_count": 10,
        "slots": slots,
    }
    plan["slot_plan_sha256"] = _digest(plan, "slot_plan_sha256")
    return plan


def verify_slot_plan(plan: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    require_exact_fields(plan, PLAN_FIELDS)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("replication_id") != REPLICATION_ID:
        raise CaptureError("SLOT_PLAN_IDENTITY_MISMATCH", "slot plan identity changed")
    if plan.get("slot_plan_sha256") != _digest(plan, "slot_plan_sha256"):
        raise CaptureError("SLOT_PLAN_DIGEST_MISMATCH", "slot plan was modified")
    slots = plan.get("slots")
    if not isinstance(slots, list) or len(slots) != 30 or plan.get("slot_count") != 30 or plan.get("block_count") != 10:
        raise CaptureError("SLOT_PLAN_CARDINALITY_MISMATCH", "slot plan must contain 30 slots")
    for index, raw in enumerate(slots, start=1):
        slot = require_object(raw, f"$.slots[{index - 1}]")
        require_exact_fields(slot, SLOT_FIELDS, f"$.slots[{index - 1}]")
        if slot.get("global_slot") != index or slot.get("slot_id") != f"slot-{index:03d}":
            raise CaptureError("SLOT_PLAN_SEQUENCE_MISMATCH", "slot sequence changed")
        validate_safe_id(slot.get("campaign_id"), f"$.slots[{index - 1}].campaign_id")
        validate_safe_id(slot.get("execution_id"), f"$.slots[{index - 1}].execution_id")
    if canonical_bytes(plan) != canonical_bytes(build_slot_plan_unverified(repo_root)):
        raise CaptureError("SLOT_PLAN_PREREGISTRATION_MISMATCH", "slot plan differs from the preregistration")
    assert_secret_free(plan)
    return plan


def build_slot_plan(repo_root: Path) -> dict[str, Any]:
    return verify_slot_plan(build_slot_plan_unverified(repo_root), repo_root)


def initialize_slot_plan(repo_root: Path) -> Path:
    return write_exclusive_json(slot_plan_path(repo_root), build_slot_plan(repo_root))


def read_slot_plan(repo_root: Path) -> dict[str, Any]:
    value = require_object(strict_json_file(slot_plan_path(repo_root), require_canonical=True), "$.slot_plan")
    return verify_slot_plan(value, repo_root)


def slot_projection(slot: dict[str, Any]) -> dict[str, Any]:
    return {key: slot[key] for key in (
        "global_slot", "slot_id", "block", "position", "model", "tier",
        "within_tier_sequence", "campaign_id", "execution_id",
    )}


def slots_for_block(plan: dict[str, Any], block: int) -> list[dict[str, Any]]:
    if not isinstance(block, int) or isinstance(block, bool) or not 1 <= block <= 10:
        raise CaptureError("INVALID_REPLICATION_BLOCK", "block must be 1 through 10")
    return [slot_projection(slot) for slot in plan["slots"] if slot["block"] == block]


def current_timestamp(value: str | None = None) -> str:
    observed = value or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return validate_timestamp(observed, "$.issued_at")
