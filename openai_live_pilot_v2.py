#!/usr/bin/env python3
"""Run the guarded OpenAI pilot with the complete alpha.2 capture core bound.

This corrected entry point reuses the original pilot implementation while deriving
its schema binding declaration from the capture core's authoritative required-path
set. It retains the same execution-only authority boundary: no automatic retry,
judgment, ratification, promotion, publication, or release.
"""
from __future__ import annotations

import json
import sys
from typing import Any

import openai_live_pilot as base
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.protocol import validate_campaign


SCRIPT_REFERENCE = "openai_live_pilot_v2.py"
CORRECTED_CAMPAIGN_ID = "openai-gpt56-memory-boundary-pilot-alpha2-r1"
_ORIGINAL_BUILD_CAMPAIGN = base._build_campaign


def _complete_schema_paths(existing: list[str]) -> list[str]:
    """Return one duplicate-free declaration containing every required core path."""
    return sorted(set(existing) | set(REQUIRED_ALPHA2_BINDINGS) | {SCRIPT_REFERENCE})


def _build_campaign(model: str, repository_commit: str) -> dict[str, Any]:
    """Build the pilot campaign, then bind the authoritative capture-core set."""
    previous_campaign_id = base.CAMPAIGN_ID
    try:
        base.CAMPAIGN_ID = CORRECTED_CAMPAIGN_ID
        campaign = _ORIGINAL_BUILD_CAMPAIGN(model, repository_commit)
    finally:
        base.CAMPAIGN_ID = previous_campaign_id

    inputs = campaign["benchmark_inputs"]
    inputs["schema_paths"] = _complete_schema_paths(inputs["schema_paths"])
    inputs["declared_commands"] = [
        f"py -3 {SCRIPT_REFERENCE} --operator <declared-operator> --model {model}",
        f"py -3 {SCRIPT_REFERENCE} --operator <declared-operator> --model {model} --execute",
    ]

    issues = validate_campaign(campaign)
    if issues:
        raise base.PilotError(
            "CAMPAIGN_VALIDATION_FAILED",
            json.dumps(issues, sort_keys=True, separators=(",", ":")),
        )
    return campaign


def main(argv: list[str] | None = None) -> int:
    """Delegate to the guarded pilot after installing the corrected builder."""
    base.CAMPAIGN_ID = CORRECTED_CAMPAIGN_ID
    base._build_campaign = _build_campaign
    return base.main(argv)


if __name__ == "__main__":
    sys.exit(main())
