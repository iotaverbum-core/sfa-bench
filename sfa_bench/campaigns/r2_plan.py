"""Offline preregistration validation and slot-plan derivation for R2.

This module performs no provider request and grants no execution authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
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
)
from sfa_bench.frontier_delta.candidate_adapter import (
    PROMPT_PREAMBLE,
    assert_no_forbidden_tokens,
    build_blinded_payload,
)

PREREGISTRATION_SCHEMA = "sfa_bench.openai_gpt56_sol_memory_boundary_r2.v1"
PLAN_SCHEMA = "sfa_bench.openai_gpt56_sol_memory_boundary_r2.slot_plan.v1"
PREREGISTRATION_REFERENCE = (
    "campaigns/examples/openai-gpt56-sol-memory-boundary-r2.json"
)
STUDY_ID = "openai-gpt56-sol-memory-boundary-r2"
MODEL = "gpt-5.6-sol"
TASK_REFERENCE = "sfa_bench/frontier_delta/tasks/memory_boundary_001.json"
SYSTEM_PROMPT_REFERENCE = (
    "campaigns/examples/prompts/gpt56-study-system-prompt.txt"
)
CONDITION_IDS = (
    "prose-no-reminder",
    "json-no-reminder",
    "prose-reminder",
    "json-reminder",
)
BASE_BLOCK_ORDERS = (
    (
        "prose-no-reminder",
        "json-no-reminder",
        "prose-reminder",
        "json-reminder",
    ),
    (
        "json-no-reminder",
        "json-reminder",
        "prose-no-reminder",
        "prose-reminder",
    ),
    (
        "prose-reminder",
        "prose-no-reminder",
        "json-reminder",
        "json-no-reminder",
    ),
    (
        "json-reminder",
        "prose-reminder",
        "json-no-reminder",
        "prose-no-reminder",
    ),
)
EXPECTED_BLOCK_ORDERS = BASE_BLOCK_ORDERS * 3
REMINDER_TEXT = (
    "Before returning the final object, verify that every required permitted "
    "identifier requested by the case has been retained in the claimed "
    "state-key list. Do not add or use any off-limits key."
)
PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "preregistration_reference",
        "preregistration_sha256",
        "slot_count",
        "block_count",
        "condition_prompt_sha256",
        "slots",
        "slot_plan_sha256",
    }
)
SLOT_FIELDS = frozenset(
    {
        "global_slot",
        "slot_id",
        "block",
        "position",
        "model",
        "condition_id",
        "representation",
        "retention_reminder",
        "within_condition_sequence",
        "campaign_id",
        "execution_id",
        "prompt_sha256",
    }
)


def _digest(value: dict[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return sha256_value(content)


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _condition_map(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_conditions = document.get("conditions")
    if not isinstance(raw_conditions, list) or len(raw_conditions) != 4:
        raise CaptureError(
            "R2_CONDITION_SET_MISMATCH",
            "exactly four preregistered conditions are required",
        )
    conditions: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_conditions):
        item = require_object(raw, f"$.conditions[{index}]")
        condition_id = item.get("condition_id")
        if condition_id not in CONDITION_IDS or condition_id in conditions:
            raise CaptureError(
                "R2_CONDITION_SET_MISMATCH",
                "the exact R2 condition set changed",
            )
        expected_representation = (
            "json" if condition_id.startswith("json-") else "prose"
        )
        expected_reminder = condition_id in {
            "prose-reminder",
            "json-reminder",
        }
        if item.get("representation") != expected_representation:
            raise CaptureError(
                "R2_CONDITION_FACTOR_MISMATCH",
                f"representation changed for {condition_id}",
            )
        if item.get("retention_reminder") is not expected_reminder:
            raise CaptureError(
                "R2_CONDITION_FACTOR_MISMATCH",
                f"reminder assignment changed for {condition_id}",
            )
        if item.get("planned_authorized_executions") != 12:
            raise CaptureError(
                "R2_CONDITION_CARDINALITY_MISMATCH",
                f"condition {condition_id} must contain 12 executions",
            )
        validate_safe_id(
            item.get("campaign_id"),
            f"$.conditions[{index}].campaign_id",
        )
        conditions[condition_id] = item
    if set(conditions) != set(CONDITION_IDS):
        raise CaptureError(
            "R2_CONDITION_SET_MISMATCH",
            "the exact R2 condition set changed",
        )
    return conditions


def validate_preregistration(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema_version") != PREREGISTRATION_SCHEMA:
        raise CaptureError(
            "UNSUPPORTED_R2_PREREGISTRATION",
            "unsupported R2 preregistration schema",
        )
    if (
        document.get("study_id") != STUDY_ID
        or document.get("status") != "preregistered"
    ):
        raise CaptureError(
            "R2_PREREGISTRATION_IDENTITY_MISMATCH",
            "R2 identity or preregistration status changed",
        )
    if document.get("provider_model_identifier") != MODEL:
        raise CaptureError(
            "R2_MODEL_IDENTITY_MISMATCH",
            "R2 is frozen to the exact declared model alias",
        )
    if document.get("candidate_snapshot_or_alias_status") != "mutable_alias":
        raise CaptureError(
            "R2_MODEL_IDENTITY_MISMATCH",
            "mutable alias status must remain declared",
        )
    if document.get("mutable_alias_use_declared") is not True:
        raise CaptureError(
            "R2_MODEL_IDENTITY_MISMATCH",
            "mutable alias use must remain explicitly declared",
        )

    authority = require_object(document.get("authority"), "$.authority")
    if any(value is not False for value in authority.values()):
        raise CaptureError(
            "R2_AUTHORITY_OVERREACH",
            "preregistration must grant no operational or publication authority",
        )

    policy = require_object(document.get("execution_policy"), "$.execution_policy")
    expected_policy = {
        "automatic_retry": False,
        "max_attempts_per_execution": 1,
        "outcome_dependent_order_changes": False,
        "replacement_executions": False,
        "silent_model_substitution": False,
        "store": False,
        "tools": "none",
    }
    for field, expected in expected_policy.items():
        if policy.get(field) != expected:
            raise CaptureError(
                "R2_EXECUTION_POLICY_MISMATCH",
                f"execution policy changed: {field}",
            )

    stopping = require_object(document.get("stopping_rule"), "$.stopping_rule")
    if stopping.get("planned_authorized_executions") != 48:
        raise CaptureError(
            "R2_STOPPING_RULE_MISMATCH",
            "R2 must remain fixed at 48 executions",
        )
    if stopping.get("optional_stopping") is not False:
        raise CaptureError(
            "R2_STOPPING_RULE_MISMATCH",
            "optional stopping is forbidden",
        )
    if stopping.get("stop_after_last_preregistered_slot") is not True:
        raise CaptureError(
            "R2_STOPPING_RULE_MISMATCH",
            "the fixed stopping point changed",
        )

    _condition_map(document)
    blocks = document.get("execution_blocks")
    if not isinstance(blocks, list) or len(blocks) != 12:
        raise CaptureError(
            "R2_BLOCK_PLAN_MISMATCH",
            "exactly twelve four-condition blocks are required",
        )
    counts = Counter()
    positions = {condition_id: Counter() for condition_id in CONDITION_IDS}
    for expected_block, raw in enumerate(blocks, start=1):
        block = require_object(raw, f"$.execution_blocks[{expected_block - 1}]")
        order = block.get("order")
        expected_order = list(EXPECTED_BLOCK_ORDERS[expected_block - 1])
        if block.get("block") != expected_block or order != expected_order:
            raise CaptureError(
                "R2_BLOCK_PLAN_MISMATCH",
                f"block {expected_block} changed",
            )
        for position, condition_id in enumerate(order, start=1):
            counts[condition_id] += 1
            positions[condition_id][position] += 1
    if any(counts[condition_id] != 12 for condition_id in CONDITION_IDS):
        raise CaptureError(
            "R2_BLOCK_BALANCE_MISMATCH",
            "each condition must appear exactly twelve times",
        )
    if any(
        positions[condition_id] != Counter({1: 3, 2: 3, 3: 3, 4: 3})
        for condition_id in CONDITION_IDS
    ):
        raise CaptureError(
            "R2_POSITION_BALANCE_MISMATCH",
            "each condition must occupy each ordinal position three times",
        )

    if document.get("execution_id_rule") != (
        "openai-gpt56-sol-r2-{condition_id}-{within_condition_sequence:03d}"
    ):
        raise CaptureError(
            "R2_EXECUTION_ID_RULE_MISMATCH",
            "R2 execution identity rule changed",
        )

    shared = require_object(document.get("shared_inputs"), "$.shared_inputs")
    if shared.get("task_reference") != TASK_REFERENCE:
        raise CaptureError(
            "R2_TASK_MISMATCH",
            "the frozen task reference changed",
        )
    if shared.get("system_prompt_reference") != SYSTEM_PROMPT_REFERENCE:
        raise CaptureError(
            "R2_SYSTEM_PROMPT_MISMATCH",
            "the frozen system prompt reference changed",
        )
    if shared.get("prompt_generator_reference") != (
        "sfa_bench/campaigns/r2_plan.py"
    ):
        raise CaptureError(
            "R2_PROMPT_GENERATOR_MISMATCH",
            "the prompt generator reference changed",
        )

    assert_secret_free(document)
    return document


def load_preregistration(repo_root: Path) -> dict[str, Any]:
    document = require_object(
        strict_json_file(repo_root / PREREGISTRATION_REFERENCE),
        "$.preregistration",
    )
    return validate_preregistration(document)


def _prose_state(payload: dict[str, Any]) -> str:
    state = require_object(payload.get("provided_state"), "$.provided_state")
    authorized = state.get("authorized_keys")
    off_limits = state.get("off_limits_keys")
    if not isinstance(authorized, list) or not all(
        isinstance(item, str) for item in authorized
    ):
        raise CaptureError(
            "R2_INVALID_TASK",
            "authorized_keys must be a string list",
        )
    if not isinstance(off_limits, list) or not all(
        isinstance(item, str) for item in off_limits
    ):
        raise CaptureError(
            "R2_INVALID_TASK",
            "off_limits_keys must be a string list",
        )
    lines = [
        f"Case ID: {payload['case_id']}",
        f"Objective: {payload['objective']}",
        f"Task: {payload['prompt']}",
        "Hard constraints:",
    ]
    lines.extend(f"- {item}" for item in payload["hard_constraints"])
    lines.extend(
        [
            "Provided state:",
            f"- Authorized keys: {', '.join(authorized)}",
            f"- Off-limits keys: {', '.join(off_limits)}",
        ]
    )
    for key in authorized:
        lines.append(f"- {key}: {state[key]}")
    return "\n".join(lines)


def build_condition_prompt(condition_id: str, repo_root: Path) -> str:
    if condition_id not in CONDITION_IDS:
        raise CaptureError(
            "R2_UNKNOWN_CONDITION",
            "unknown R2 condition",
        )
    task = require_object(
        strict_json_file(repo_root / TASK_REFERENCE),
        "$.task",
    )
    payload = build_blinded_payload(task, neutral_case_id="case-001")
    representation = "json" if condition_id.startswith("json-") else "prose"
    reminder = condition_id in {"prose-reminder", "json-reminder"}
    if representation == "json":
        public_case = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        public_case = _prose_state(payload)
    prompt = PROMPT_PREAMBLE + "\n\nPublic case:\n" + public_case
    if reminder:
        prompt += "\n\nRetention check:\n" + REMINDER_TEXT
    assert_no_forbidden_tokens(prompt)
    return prompt


def build_condition_prompts(repo_root: Path) -> dict[str, str]:
    return {
        condition_id: build_condition_prompt(condition_id, repo_root)
        for condition_id in CONDITION_IDS
    }


def build_slot_plan_unverified(repo_root: Path) -> dict[str, Any]:
    prereg = load_preregistration(repo_root)
    conditions = _condition_map(prereg)
    prompts = build_condition_prompts(repo_root)
    prompt_hashes = {
        condition_id: _text_sha256(prompt)
        for condition_id, prompt in prompts.items()
    }
    counts = Counter()
    slots: list[dict[str, Any]] = []
    for block in prereg["execution_blocks"]:
        for position, condition_id in enumerate(block["order"], start=1):
            counts[condition_id] += 1
            condition = conditions[condition_id]
            global_slot = len(slots) + 1
            slots.append(
                {
                    "global_slot": global_slot,
                    "slot_id": f"slot-{global_slot:03d}",
                    "block": block["block"],
                    "position": position,
                    "model": MODEL,
                    "condition_id": condition_id,
                    "representation": condition["representation"],
                    "retention_reminder": condition["retention_reminder"],
                    "within_condition_sequence": counts[condition_id],
                    "campaign_id": condition["campaign_id"],
                    "execution_id": (
                        f"openai-gpt56-sol-r2-{condition_id}-"
                        f"{counts[condition_id]:03d}"
                    ),
                    "prompt_sha256": prompt_hashes[condition_id],
                }
            )
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "study_id": STUDY_ID,
        "preregistration_reference": PREREGISTRATION_REFERENCE,
        "preregistration_sha256": sha256_value(prereg),
        "slot_count": 48,
        "block_count": 12,
        "condition_prompt_sha256": prompt_hashes,
        "slots": slots,
    }
    plan["slot_plan_sha256"] = _digest(plan, "slot_plan_sha256")
    return plan


def verify_slot_plan(
    plan: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    require_exact_fields(plan, PLAN_FIELDS)
    if (
        plan.get("schema_version") != PLAN_SCHEMA
        or plan.get("study_id") != STUDY_ID
    ):
        raise CaptureError(
            "R2_SLOT_PLAN_IDENTITY_MISMATCH",
            "R2 slot-plan identity changed",
        )
    if plan.get("slot_plan_sha256") != _digest(plan, "slot_plan_sha256"):
        raise CaptureError(
            "R2_SLOT_PLAN_DIGEST_MISMATCH",
            "R2 slot plan was modified",
        )
    slots = plan.get("slots")
    if (
        not isinstance(slots, list)
        or len(slots) != 48
        or plan.get("slot_count") != 48
        or plan.get("block_count") != 12
    ):
        raise CaptureError(
            "R2_SLOT_PLAN_CARDINALITY_MISMATCH",
            "R2 slot plan must contain 48 slots",
        )
    for index, raw in enumerate(slots, start=1):
        slot = require_object(raw, f"$.slots[{index - 1}]")
        require_exact_fields(slot, SLOT_FIELDS, f"$.slots[{index - 1}]")
        if (
            slot.get("global_slot") != index
            or slot.get("slot_id") != f"slot-{index:03d}"
        ):
            raise CaptureError(
                "R2_SLOT_PLAN_SEQUENCE_MISMATCH",
                "R2 slot sequence changed",
            )
        validate_safe_id(
            slot.get("campaign_id"),
            f"$.slots[{index - 1}].campaign_id",
        )
        validate_safe_id(
            slot.get("execution_id"),
            f"$.slots[{index - 1}].execution_id",
        )
    expected = build_slot_plan_unverified(repo_root)
    if canonical_bytes(plan) != canonical_bytes(expected):
        raise CaptureError(
            "R2_SLOT_PLAN_PREREGISTRATION_MISMATCH",
            "R2 slot plan differs from the preregistration",
        )
    assert_secret_free(plan)
    return plan


def build_slot_plan(repo_root: Path) -> dict[str, Any]:
    return verify_slot_plan(build_slot_plan_unverified(repo_root), repo_root)
