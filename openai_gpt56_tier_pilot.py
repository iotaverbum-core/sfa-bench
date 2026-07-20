#!/usr/bin/env python3
"""Prepare or execute one preregistered GPT-5.6 Terra or Luna tier pilot.

The ratified Sol execution is the cohort anchor. This helper permits only the two
planned successor model identifiers and their exact execution IDs. Each invocation
retains the alpha.2 execution-only authority boundary: one request, no retry, no
automatic judgment, ratification, promotion, publication, or release.
"""
from __future__ import annotations

import json
import sys
from typing import Any

import openai_live_pilot as base
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.protocol import validate_campaign


SCRIPT_REFERENCE = "openai_gpt56_tier_pilot.py"
PROTOCOL_REFERENCE = "campaigns/examples/openai-gpt56-tier-pilot-protocol.json"
MODEL_SPECS: dict[str, dict[str, str]] = {
    "gpt-5.6-terra": {
        "tier": "Terra",
        "campaign_id": "openai-gpt56-terra-memory-boundary-tier-pilot-alpha2-r1",
        "execution_id": "openai-gpt56-terra-pilot-001",
    },
    "gpt-5.6-luna": {
        "tier": "Luna",
        "campaign_id": "openai-gpt56-luna-memory-boundary-tier-pilot-alpha2-r1",
        "execution_id": "openai-gpt56-luna-pilot-001",
    },
}
_ORIGINAL_BUILD_CAMPAIGN = base._build_campaign
_ORIGINAL_PARSE_ARGS = base.parse_args


def _spec(model: str) -> dict[str, str]:
    selected = MODEL_SPECS.get(model)
    if selected is None:
        allowed = ", ".join(sorted(MODEL_SPECS))
        raise base.PilotError(
            "TIER_MODEL_NOT_PREREGISTERED",
            f"model must be one of the preregistered tier identifiers: {allowed}",
        )
    return selected


def _parse_args(argv: list[str] | None = None):
    args = _ORIGINAL_PARSE_ARGS(argv)
    model = args.model.strip() if isinstance(args.model, str) else args.model
    selected = _spec(model)
    args.model = model
    expected_execution = selected["execution_id"]
    if args.execution_id is None:
        args.execution_id = expected_execution
    elif args.execution_id != expected_execution:
        raise base.PilotError(
            "TIER_EXECUTION_ID_MISMATCH",
            f"{model} is preregistered only as execution {expected_execution!r}",
        )
    return args


def _complete_schema_paths(existing: list[str]) -> list[str]:
    return sorted(set(existing) | set(REQUIRED_ALPHA2_BINDINGS) | {SCRIPT_REFERENCE})


def _build_campaign(model: str, repository_commit: str) -> dict[str, Any]:
    selected = _spec(model)
    previous_campaign_id = base.CAMPAIGN_ID
    try:
        base.CAMPAIGN_ID = selected["campaign_id"]
        campaign = _ORIGINAL_BUILD_CAMPAIGN(model, repository_commit)
    finally:
        base.CAMPAIGN_ID = previous_campaign_id

    tier = selected["tier"]
    campaign["campaign_title"] = f"OpenAI GPT-5.6 {tier} Memory Boundary Tier Pilot"
    campaign["research_question"] = (
        f"Does the exact available OpenAI GPT-5.6 {tier} candidate preserve the same "
        "frozen memory-state boundary used by the ratified Sol anchor?"
    )
    campaign["declared_limitations"] = list(campaign["declared_limitations"]) + [
        "This execution belongs to an exploratory one-run-per-tier cohort.",
        "The cohort cannot support a provider-tier ranking or general model-performance claim.",
        "The ratified Sol result is a historical anchor, not a control sample or performance baseline.",
    ]

    inputs = campaign["benchmark_inputs"]
    inputs["evidence_paths"] = sorted(set(inputs["evidence_paths"]) | {PROTOCOL_REFERENCE})
    inputs["schema_paths"] = _complete_schema_paths(inputs["schema_paths"])
    command = (
        f"py -3 {SCRIPT_REFERENCE} --operator <declared-operator> --model {model} "
        f"--execution-id {selected['execution_id']}"
    )
    inputs["declared_commands"] = [command, command + " --execute"]

    issues = validate_campaign(campaign)
    if issues:
        raise base.PilotError(
            "CAMPAIGN_VALIDATION_FAILED",
            json.dumps(issues, sort_keys=True, separators=(",", ":")),
        )
    return campaign


def main(argv: list[str] | None = None) -> int:
    base.parse_args = _parse_args
    base._build_campaign = _build_campaign
    return base.main(argv)


if __name__ == "__main__":
    sys.exit(main())
