"""Filesystem paths and canonical plan access for the frozen R2 harness.

This module is offline and grants no provider execution authority.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any

from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    require_object,
    strict_json_file,
    validate_timestamp,
    write_exclusive_json,
)
from sfa_bench.campaigns.r2_plan import (
    STUDY_ID,
    build_slot_plan,
    verify_slot_plan,
)

STATUS_SCHEMA = "sfa_bench.openai_gpt56_sol_memory_boundary_r2.status.v1"


def harness_root(repo_root: Path) -> Path:
    configured = os.environ.get("SFA_R2_HARNESS_ROOT")
    base = (
        Path(configured).absolute()
        if configured
        else repo_root / "out" / "r2_harness"
    )
    return base / STUDY_ID


def capture_root(repo_root: Path) -> Path:
    configured = os.environ.get("SFA_CAMPAIGN_CAPTURE_ROOT")
    return (
        Path(configured).absolute()
        if configured
        else repo_root / "out" / "campaign_runs"
    )


def slot_plan_path(repo_root: Path) -> Path:
    return harness_root(repo_root) / "slot-plan.json"


def block_authorization_path(repo_root: Path, block: int) -> Path:
    return (
        harness_root(repo_root)
        / "block-authorizations"
        / f"block-{block:03d}.json"
    )


def initialize_slot_plan(repo_root: Path) -> Path:
    path = write_exclusive_json(slot_plan_path(repo_root), build_slot_plan(repo_root))
    read_slot_plan(repo_root)
    return path


def read_slot_plan(repo_root: Path) -> dict[str, Any]:
    value = require_object(
        strict_json_file(slot_plan_path(repo_root), require_canonical=True),
        "$.slot_plan",
    )
    return verify_slot_plan(value, repo_root)


def slot_projection(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: slot[key]
        for key in (
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
        )
    }


def slots_for_block(plan: dict[str, Any], block: int) -> list[dict[str, Any]]:
    if (
        not isinstance(block, int)
        or isinstance(block, bool)
        or not 1 <= block <= 12
    ):
        raise CaptureError("INVALID_R2_BLOCK", "block must be 1 through 12")
    return [
        slot_projection(slot)
        for slot in plan["slots"]
        if slot["block"] == block
    ]


def current_timestamp(value: str | None = None) -> str:
    observed = value or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return validate_timestamp(observed, "$.issued_at")
