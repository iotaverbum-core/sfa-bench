#!/usr/bin/env python3
"""Control and execute the preregistered 30-slot GPT-5.6 replication campaign.

The initialize, status, and authorize-block commands are offline and credential-free.
A provider generation occurs only through execute-next with both a canonical block
authorization and explicit --execute. Each slot is fixed, single-attempt, and
non-replaceable. This command never judges, ratifies, ranks, promotes, publishes,
or releases evidence.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys
from typing import Any

import openai_live_pilot as base
from sfa_bench.campaigns.capture.canonical import CaptureError, canonical_bytes
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.protocol import validate_campaign
from sfa_bench.campaigns.replication_authorization import (
    build_block_authorization,
    read_block_authorization,
    write_block_authorization,
)
from sfa_bench.campaigns.replication_plan import (
    PREREGISTRATION_REFERENCE,
    REPLICATION_ID,
    current_timestamp,
    initialize_slot_plan,
    read_slot_plan,
)
from sfa_bench.campaigns.replication_state import (
    next_pending_slot,
    scan_slot_states,
    status_document,
)


ROOT = Path(__file__).resolve().parent
SCRIPT_REFERENCE = "openai_gpt56_replication.py"
MODULE_REFERENCES = {
    "sfa_bench/campaigns/replication_plan.py",
    "sfa_bench/campaigns/replication_state.py",
    "sfa_bench/campaigns/replication_authorization.py",
}
CLOSURE_REFERENCE = "campaigns/examples/openai-gpt56-tier-pilot-closure-spec.json"
COMMAND_NAME = "openai-gpt56-replication"
_ORIGINAL_BUILD_CAMPAIGN = base._build_campaign
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

    commands.add_parser("initialize", help="write the immutable 30-slot plan without provider access")

    status = commands.add_parser("status", help="derive replication progress without provider access")
    status.add_argument("--full", action="store_true", help="include all slot records")

    authorize = commands.add_parser("authorize-block", help="record explicit authority for the next block")
    authorize.add_argument("--operator", required=True, help="declared human operator identity")
    authorize.add_argument("--block", required=True, type=int, help="next preregistered block number")
    authorize.add_argument("--rationale", required=True, help="explicit rationale for authorizing this block")
    authorize.add_argument("--now", help="timezone-qualified ISO timestamp; defaults to local current time")

    execute = commands.add_parser("execute-next", help="execute only the next slot in an authorized block")
    execute.add_argument("--operator", required=True, help="declared human operator identity")
    execute.add_argument("--block-authorization", required=True, help="canonical stored block authorization path")
    execute.add_argument("--max-output-tokens", type=int, default=base.DEFAULT_MAX_OUTPUT_TOKENS)
    execute.add_argument("--timeout", type=float, default=120.0)
    execute.add_argument("--now", help="timezone-qualified ISO timestamp; defaults to local current time")
    execute.add_argument("--execute", action="store_true", help="send the single authorized provider request")
    return parser.parse_args(argv)


def _active() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if _ACTIVE_SLOT is None or _ACTIVE_BLOCK_AUTHORIZATION is None or _ACTIVE_PLAN is None:
        raise HarnessError("REPLICATION_CONTEXT_MISSING", "active replication slot context is unavailable")
    return _ACTIVE_SLOT, _ACTIVE_BLOCK_AUTHORIZATION, _ACTIVE_PLAN


def _build_campaign(model: str, repository_commit: str) -> dict[str, Any]:
    slot, block_authorization, _plan = _active()
    if model != slot["model"]:
        raise HarnessError("REPLICATION_MODEL_SUBSTITUTION", "requested model differs from the next preregistered slot")
    previous_campaign_id = base.CAMPAIGN_ID
    try:
        base.CAMPAIGN_ID = slot["campaign_id"]
        campaign = _ORIGINAL_BUILD_CAMPAIGN(model, repository_commit)
    finally:
        base.CAMPAIGN_ID = previous_campaign_id

    tier = slot["tier"].title()
    campaign["campaign_title"] = f"OpenAI GPT-5.6 {tier} Memory Boundary Repeated-Execution Replication"
    campaign["research_question"] = (
        f"Across ten fresh governed executions of exact alias {model}, what proportion "
        "preserves the frozen memory-state boundary?"
    )
    campaign["run_count"] = 10
    campaign["run_classification"] = "pilot"
    campaign["retry_policy"]["max_attempts"] = 1
    campaign["retry_policy"]["retry_conditions"] = []
    campaign["declared_limitations"] = list(campaign["declared_limitations"]) + [
        "This is a post-pilot preregistered repeated-execution replication; the three pilot outcomes were observed before this design was fixed.",
        "The pilot executions are excluded from every primary and secondary replication estimate.",
        "The provider model identifier is a mutable alias and is not a snapshot or provider identity attestation.",
        "Results are descriptive and cannot support a provider-tier ranking or general model-performance claim.",
        "Block authorization is a declared human action and does not authenticate real-world identity or legal authority.",
    ]
    inputs = campaign["benchmark_inputs"]
    inputs["evidence_paths"] = sorted(
        set(inputs["evidence_paths"]) | {PREREGISTRATION_REFERENCE, CLOSURE_REFERENCE}
    )
    inputs["schema_paths"] = sorted(
        set(inputs["schema_paths"])
        | set(REQUIRED_ALPHA2_BINDINGS)
        | {SCRIPT_REFERENCE}
        | MODULE_REFERENCES
    )
    inputs["declared_commands"] = [
        f"py -3 {SCRIPT_REFERENCE} execute-next --operator <declared-operator> "
        "--block-authorization <canonical-block-authorization.json> --execute"
    ]
    plan = campaign["execution_plan"]
    plan["campaign_id"] = slot["campaign_id"]
    plan["planned_repetitions"] = 10
    plan["run_classification"] = "pilot"
    plan["output_path"] = f"out/campaign_runs/{slot['campaign_id']}"
    plan["retry_rules"]["max_attempts"] = 1
    plan["retry_rules"]["retry_conditions"] = []
    campaign.pop("benchmark_lock", None)

    issues = validate_campaign(campaign)
    if issues:
        raise HarnessError(
            "CAMPAIGN_VALIDATION_FAILED",
            json.dumps(issues, sort_keys=True, separators=(",", ":")),
        )
    if block_authorization["block"] != slot["block"]:
        raise HarnessError("BLOCK_AUTHORIZATION_SLOT_MISMATCH", "active block authorization does not cover this slot")
    return campaign


def _seal_execution_authorization(content: dict[str, Any]) -> dict[str, Any]:
    slot, block_authorization, _plan = _active()
    if content.get("execution_id") != slot["execution_id"] or content.get("campaign_id") != slot["campaign_id"]:
        raise HarnessError("REPLICATION_EXECUTION_AUTHORIZATION_MISMATCH", "execution authorization binds another slot")
    token = base64.b32encode(
        bytes.fromhex(block_authorization["authorization_sha256"])
    ).decode("ascii").rstrip("=").lower()
    document = dict(content)
    document["authorization_id"] = (
        f"b{slot['block']:03d}s{slot['global_slot']:03d}-{token}"
    )
    return _ORIGINAL_SEAL_AUTHORIZATION(document)


def _emit_live(value: dict[str, Any]) -> None:
    slot, block_authorization, plan = _active()
    document = dict(value)
    if document.get("command") == "openai-live-pilot":
        document["command"] = COMMAND_NAME
    document.update(
        {
            "replication_id": REPLICATION_ID,
            "slot_plan_sha256": plan["slot_plan_sha256"],
            "block_authorization_sha256": block_authorization["authorization_sha256"],
            "block": slot["block"],
            "global_slot": slot["global_slot"],
            "position": slot["position"],
            "within_tier_sequence": slot["within_tier_sequence"],
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
            "replication_id": REPLICATION_ID,
            "slot_count": 30,
            "block_count": 10,
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
    document.update({"command": COMMAND_NAME, "subcommand": "status", "status": "ok"})
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
    path = write_block_authorization(ROOT, authorization, plan)
    _emit(
        {
            "command": COMMAND_NAME,
            "subcommand": "authorize-block",
            "status": "ok",
            "replication_id": REPLICATION_ID,
            "block": authorization["block"],
            "authorized_slot_ids": [item["slot_id"] for item in authorization["authorized_slots"]],
            "authorization_sha256": authorization["authorization_sha256"],
            "output": str(path),
            "provider_requests_authorized": 3,
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
            "REPLICATION_EXECUTION_REQUIRED",
            "execute-next sends no provider request unless explicit --execute is supplied",
        )
    plan = read_slot_plan(ROOT)
    states = scan_slot_states(ROOT, plan)
    slot = next_pending_slot(states)
    if slot is None:
        raise HarnessError("REPLICATION_ALREADY_COMPLETE", "all 30 preregistered slots are occupied")
    authorization_path = Path(args.block_authorization).absolute()
    authorization = read_block_authorization(ROOT, authorization_path, plan)
    if authorization["block"] != slot["block"]:
        raise HarnessError(
            "REPLICATION_BLOCK_OUT_OF_ORDER",
            f"next slot belongs to block {slot['block']}, not authorized block {authorization['block']}",
        )
    if args.operator.strip() != authorization["operator_declaration"]["identity"]:
        raise HarnessError("REPLICATION_OPERATOR_MISMATCH", "executing operator differs from the block authorization declaration")
    if not any(item["execution_id"] == slot["execution_id"] for item in authorization["authorized_slots"]):
        raise HarnessError("BLOCK_AUTHORIZATION_SLOT_MISMATCH", "block authorization does not include the next exact execution ID")

    _ACTIVE_SLOT = slot
    _ACTIVE_BLOCK_AUTHORIZATION = authorization
    _ACTIVE_PLAN = plan
    previous_builder = base._build_campaign
    previous_emit = base._emit
    previous_seal = base.seal_authorization
    try:
        base._build_campaign = _build_campaign
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
        raise HarnessError("UNKNOWN_REPLICATION_COMMAND", "unsupported replication harness command")
    except (HarnessError, CaptureError) as exc:
        issue = exc.to_dict() if isinstance(exc, CaptureError) else {"code": exc.code, "path": "$", "message": exc.message}
        _emit({"command": COMMAND_NAME, "status": "error", "issue": issue, "provider_request_sent": False})
        return 2
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _emit(
            {
                "command": COMMAND_NAME,
                "status": "error",
                "issue": {"code": "REPLICATION_HARNESS_ERROR", "path": "$", "message": str(exc)},
                "provider_request_sent": False,
            }
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
