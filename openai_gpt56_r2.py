#!/usr/bin/env python3
"""Control and execute the preregistered 48-slot GPT-5.6 Sol R2 study.

The initialize, status, and authorize-block commands are offline and
credential-free. A generation occurs only through execute-next with a
canonical block authorization and explicit --execute. Each slot is fixed,
single-attempt, and non-replaceable. This command never judges, ratifies,
ranks, promotes, publishes, or releases evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import openai_live_pilot as base
from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    canonical_bytes,
)
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.protocol import validate_campaign
from sfa_bench.campaigns.r2_authorization import (
    build_block_authorization,
    read_block_authorization,
    write_block_authorization,
)
from sfa_bench.campaigns.r2_harness_plan import (
    current_timestamp,
    initialize_slot_plan,
    read_slot_plan,
)
from sfa_bench.campaigns.r2_plan import (
    MODEL,
    PREREGISTRATION_REFERENCE,
    STUDY_ID,
    SYSTEM_PROMPT_REFERENCE,
    build_condition_prompt,
)
from sfa_bench.campaigns.r2_state import (
    next_pending_slot,
    scan_slot_states,
    status_document,
)

ROOT = Path(__file__).resolve().parent
SCRIPT_REFERENCE = "openai_gpt56_r2.py"
MODULE_REFERENCES = {
    "sfa_bench/campaigns/r2_plan.py",
    "sfa_bench/campaigns/r2_harness_plan.py",
    "sfa_bench/campaigns/r2_state.py",
    "sfa_bench/campaigns/r2_authorization.py",
}
COMMAND_NAME = "openai-gpt56-sol-r2"
_ORIGINAL_BUILD_CAMPAIGN = base._build_campaign
_ORIGINAL_BUILD_REQUEST = base._build_request
_ORIGINAL_EMIT = base._emit
_ORIGINAL_SEAL_AUTHORIZATION = base.seal_authorization
_ACTIVE_SLOT: dict[str, Any] | None = None
_ACTIVE_BLOCK_AUTHORIZATION: dict[str, Any] | None = None
_ACTIVE_PLAN: dict[str, Any] | None = None


class HarnessError(base.PilotError):
    pass


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(canonical_bytes(value).decode("utf-8") + "\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="subcommand", required=True)

    commands.add_parser(
        "initialize",
        help="write the immutable 48-slot plan without provider access",
    )

    status = commands.add_parser(
        "status",
        help="derive R2 progress without provider access",
    )
    status.add_argument(
        "--full",
        action="store_true",
        help="include all slot records",
    )

    authorize = commands.add_parser(
        "authorize-block",
        help="record explicit authority for the next four-slot block",
    )
    authorize.add_argument(
        "--operator",
        required=True,
        help="declared human operator identity",
    )
    authorize.add_argument(
        "--block",
        required=True,
        type=int,
        help="next preregistered block number",
    )
    authorize.add_argument(
        "--rationale",
        required=True,
        help="explicit rationale for authorizing this block",
    )
    authorize.add_argument(
        "--now",
        help="timezone-qualified ISO timestamp; defaults to local current time",
    )

    execute = commands.add_parser(
        "execute-next",
        help="execute only the next slot in an authorized block",
    )
    execute.add_argument(
        "--operator",
        required=True,
        help="declared human operator identity",
    )
    execute.add_argument(
        "--block-authorization",
        required=True,
        help="canonical stored block authorization path",
    )
    execute.add_argument(
        "--max-output-tokens",
        type=int,
        default=base.DEFAULT_MAX_OUTPUT_TOKENS,
    )
    execute.add_argument("--timeout", type=float, default=120.0)
    execute.add_argument(
        "--now",
        help="timezone-qualified ISO timestamp; defaults to local current time",
    )
    execute.add_argument(
        "--execute",
        action="store_true",
        help="send the single authorized provider generation",
    )
    return parser.parse_args(argv)


def _active() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if (
        _ACTIVE_SLOT is None
        or _ACTIVE_BLOCK_AUTHORIZATION is None
        or _ACTIVE_PLAN is None
    ):
        raise HarnessError(
            "R2_CONTEXT_MISSING",
            "active R2 slot context is unavailable",
        )
    return _ACTIVE_SLOT, _ACTIVE_BLOCK_AUTHORIZATION, _ACTIVE_PLAN


def _build_campaign(model: str, repository_commit: str) -> dict[str, Any]:
    slot, block_authorization, _plan = _active()
    if model != slot["model"] or model != MODEL:
        raise HarnessError(
            "R2_MODEL_SUBSTITUTION",
            "requested model differs from the next preregistered slot",
        )
    previous_campaign_id = base.CAMPAIGN_ID
    try:
        base.CAMPAIGN_ID = slot["campaign_id"]
        campaign = _ORIGINAL_BUILD_CAMPAIGN(model, repository_commit)
    finally:
        base.CAMPAIGN_ID = previous_campaign_id

    campaign["campaign_title"] = (
        "OpenAI GPT-5.6 Sol Permitted-State Preservation R2: "
        f"{slot['condition_id']}"
    )
    campaign["research_question"] = (
        "How do public-state representation and an explicit retention reminder "
        "affect preservation of permitted identity state, particularly "
        "customer_id, without increasing forbidden-state use?"
    )
    campaign["run_count"] = 12
    campaign["run_classification"] = "pilot"
    campaign["retry_policy"]["max_attempts"] = 1
    campaign["retry_policy"]["retry_conditions"] = []
    campaign["declared_limitations"] = list(
        campaign["declared_limitations"]
    ) + [
        "This execution belongs to a preregistered balanced 2x2 mechanism study created after R1.",
        "No R1 execution is included in the R2 estimates.",
        f"The exact preregistered condition is {slot['condition_id']}.",
        "The provider identifier is a mutable alias, not an immutable snapshot or provider identity attestation.",
        "Condition effects are task-specific and cannot support a general model-performance claim.",
        "The campaign protocol schema retains its historical pilot run-classification label; the controlling R2 preregistration defines the study classification.",
        "Block authorization is a declared human action and does not authenticate real-world identity or legal authority.",
    ]
    inputs = campaign["benchmark_inputs"]
    inputs["evidence_paths"] = sorted(
        set(inputs["evidence_paths"])
        | {
            PREREGISTRATION_REFERENCE,
            "sfa_bench/campaigns/r2_plan.py",
        }
    )
    inputs["schema_paths"] = sorted(
        set(inputs["schema_paths"])
        | set(REQUIRED_ALPHA2_BINDINGS)
        | {SCRIPT_REFERENCE}
        | MODULE_REFERENCES
    )
    inputs["declared_commands"] = [
        f"py -3 {SCRIPT_REFERENCE} execute-next "
        "--operator <declared-operator> "
        "--block-authorization <canonical-block-authorization.json> "
        "--execute"
    ]
    execution_plan = campaign["execution_plan"]
    execution_plan["campaign_id"] = slot["campaign_id"]
    execution_plan["planned_repetitions"] = 12
    execution_plan["run_classification"] = "pilot"
    execution_plan["output_path"] = (
        f"out/campaign_runs/{slot['campaign_id']}"
    )
    execution_plan["retry_rules"]["max_attempts"] = 1
    execution_plan["retry_rules"]["retry_conditions"] = []
    campaign.pop("benchmark_lock", None)

    issues = validate_campaign(campaign)
    if issues:
        raise HarnessError(
            "CAMPAIGN_VALIDATION_FAILED",
            json.dumps(issues, sort_keys=True, separators=(",", ":")),
        )
    if block_authorization["block"] != slot["block"]:
        raise HarnessError(
            "R2_BLOCK_AUTHORIZATION_SLOT_MISMATCH",
            "active block authorization does not cover this slot",
        )
    return campaign


def _build_request(model: str, max_output_tokens: int) -> bytes:
    slot, _block_authorization, plan = _active()
    if model != slot["model"] or model != MODEL:
        raise HarnessError(
            "R2_MODEL_SUBSTITUTION",
            "request model differs from the next preregistered slot",
        )
    prompt = build_condition_prompt(slot["condition_id"], ROOT)
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if prompt_sha256 != slot["prompt_sha256"]:
        raise HarnessError(
            "R2_CONDITION_PROMPT_MISMATCH",
            "generated condition prompt differs from the frozen slot plan",
        )
    if (
        plan["condition_prompt_sha256"].get(slot["condition_id"])
        != prompt_sha256
    ):
        raise HarnessError(
            "R2_CONDITION_PROMPT_PLAN_MISMATCH",
            "condition prompt differs from the frozen plan binding",
        )
    instructions = (
        ROOT / SYSTEM_PROMPT_REFERENCE
    ).read_text(encoding="utf-8")
    return canonical_bytes(
        {
            "input": prompt,
            "instructions": instructions,
            "max_output_tokens": max_output_tokens,
            "model": model,
            "store": False,
        }
    )


def _seal_execution_authorization(
    content: dict[str, Any],
) -> dict[str, Any]:
    slot, block_authorization, _plan = _active()
    if (
        content.get("execution_id") != slot["execution_id"]
        or content.get("campaign_id") != slot["campaign_id"]
    ):
        raise HarnessError(
            "R2_EXECUTION_AUTHORIZATION_MISMATCH",
            "execution authorization binds another slot",
        )
    token = (
        base64.b32encode(
            bytes.fromhex(block_authorization["authorization_sha256"])
        )
        .decode("ascii")
        .rstrip("=")
        .lower()
    )
    document = dict(content)
    document["authorization_id"] = (
        f"r2b{slot['block']:03d}s{slot['global_slot']:03d}-{token}"
    )
    return _ORIGINAL_SEAL_AUTHORIZATION(document)


def _emit_live(value: dict[str, Any]) -> None:
    slot, block_authorization, plan = _active()
    document = dict(value)
    if document.get("command") == "openai-live-pilot":
        document["command"] = COMMAND_NAME
    document.update(
        {
            "study_id": STUDY_ID,
            "slot_plan_sha256": plan["slot_plan_sha256"],
            "block_authorization_sha256": (
                block_authorization["authorization_sha256"]
            ),
            "block": slot["block"],
            "global_slot": slot["global_slot"],
            "position": slot["position"],
            "condition_id": slot["condition_id"],
            "representation": slot["representation"],
            "retention_reminder": slot["retention_reminder"],
            "within_condition_sequence": (
                slot["within_condition_sequence"]
            ),
            "condition_prompt_sha256": slot["prompt_sha256"],
            "model_endorsement": False,
            "ranking": False,
            "promotion": False,
            "publication": False,
            "release": False,
        }
    )
    _ORIGINAL_EMIT(document)


def _initialize() -> int:
    path = initialize_slot_plan(ROOT)
    plan = read_slot_plan(ROOT)
    _emit(
        {
            "command": COMMAND_NAME,
            "subcommand": "initialize",
            "status": "ok",
            "study_id": STUDY_ID,
            "slot_count": 48,
            "block_count": 12,
            "slot_plan_sha256": plan["slot_plan_sha256"],
            "output": str(path),
            "provider_request_sent": False,
        }
    )
    return 0


def _status(full: bool) -> int:
    plan = read_slot_plan(ROOT)
    document = status_document(ROOT, plan)
    if not full:
        document.pop("slots", None)
    document.update(
        {
            "command": COMMAND_NAME,
            "subcommand": "status",
            "status": "ok",
        }
    )
    _emit(document)
    return 0


def _authorize(args: argparse.Namespace) -> int:
    plan = read_slot_plan(ROOT)
    authorization = build_block_authorization(
        ROOT,
        plan=plan,
        block=args.block,
        operator=args.operator,
        rationale=args.rationale,
        issued_at=current_timestamp(args.now),
    )
    path = write_block_authorization(
        ROOT,
        authorization,
        plan,
    )
    stored = read_block_authorization(ROOT, path.absolute(), plan)
    if stored != authorization:
        raise HarnessError(
            "R2_BLOCK_AUTHORIZATION_WRITE_MISMATCH",
            "stored authorization differs from the verified value",
        )
    _emit(
        {
            "command": COMMAND_NAME,
            "subcommand": "authorize-block",
            "status": "ok",
            "study_id": STUDY_ID,
            "block": stored["block"],
            "authorized_slot_ids": [
                item["slot_id"] for item in stored["authorized_slots"]
            ],
            "authorization_sha256": stored["authorization_sha256"],
            "output": str(path),
            "provider_requests_authorized": 4,
            "provider_request_sent": False,
            "automatic_judgment": False,
            "automatic_ratification": False,
            "ranking": False,
            "promotion": False,
            "publication": False,
            "release": False,
        }
    )
    return 0


def _execute(args: argparse.Namespace) -> int:
    global _ACTIVE_SLOT, _ACTIVE_BLOCK_AUTHORIZATION, _ACTIVE_PLAN
    if args.execute is not True:
        raise HarnessError(
            "R2_EXECUTION_REQUIRED",
            "execute-next sends no provider generation unless explicit "
            "--execute is supplied",
        )
    plan = read_slot_plan(ROOT)
    states = scan_slot_states(ROOT, plan)
    slot = next_pending_slot(states)
    if slot is None:
        raise HarnessError(
            "R2_ALREADY_COMPLETE",
            "all 48 preregistered slots are occupied",
        )
    authorization_path = Path(args.block_authorization).absolute()
    authorization = read_block_authorization(
        ROOT,
        authorization_path,
        plan,
    )
    if authorization["block"] != slot["block"]:
        raise HarnessError(
            "R2_BLOCK_OUT_OF_ORDER",
            f"next slot belongs to block {slot['block']}, not authorized "
            f"block {authorization['block']}",
        )
    if (
        args.operator.strip()
        != authorization["operator_declaration"]["identity"]
    ):
        raise HarnessError(
            "R2_OPERATOR_MISMATCH",
            "executing operator differs from the block authorization "
            "declaration",
        )
    if not any(
        item["execution_id"] == slot["execution_id"]
        for item in authorization["authorized_slots"]
    ):
        raise HarnessError(
            "R2_BLOCK_AUTHORIZATION_SLOT_MISMATCH",
            "block authorization does not include the next exact execution ID",
        )

    _ACTIVE_SLOT = slot
    _ACTIVE_BLOCK_AUTHORIZATION = authorization
    _ACTIVE_PLAN = plan
    previous_builder = base._build_campaign
    previous_request_builder = base._build_request
    previous_emit = base._emit
    previous_seal = base.seal_authorization
    try:
        base._build_campaign = _build_campaign
        base._build_request = _build_request
        base._emit = _emit_live
        base.seal_authorization = _seal_execution_authorization
        forwarded = [
            "--operator",
            args.operator.strip(),
            "--model",
            slot["model"],
            "--execution-id",
            slot["execution_id"],
            "--max-output-tokens",
            str(args.max_output_tokens),
            "--timeout",
            str(args.timeout),
            "--execute",
        ]
        if args.now:
            forwarded.extend(["--now", args.now])
        return base.main(forwarded)
    finally:
        base._build_campaign = previous_builder
        base._build_request = previous_request_builder
        base._emit = previous_emit
        base.seal_authorization = previous_seal
        _ACTIVE_SLOT = None
        _ACTIVE_BLOCK_AUTHORIZATION = None
        _ACTIVE_PLAN = None


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.subcommand == "initialize":
            return _initialize()
        if args.subcommand == "status":
            return _status(args.full)
        if args.subcommand == "authorize-block":
            return _authorize(args)
        if args.subcommand == "execute-next":
            return _execute(args)
        raise HarnessError(
            "UNKNOWN_R2_COMMAND",
            "unsupported R2 harness command",
        )
    except (HarnessError, CaptureError) as exc:
        issue = (
            exc.to_dict()
            if isinstance(exc, CaptureError)
            else {"code": exc.code, "path": "$", "message": exc.message}
        )
        _emit(
            {
                "command": COMMAND_NAME,
                "status": "error",
                "issue": issue,
                "provider_request_sent": False,
            }
        )
        return 2
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _emit(
            {
                "command": COMMAND_NAME,
                "status": "error",
                "issue": {
                    "code": "R2_HARNESS_ERROR",
                    "path": "$",
                    "message": str(exc),
                },
                "provider_request_sent": False,
            }
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
