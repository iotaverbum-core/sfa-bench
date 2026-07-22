#!/usr/bin/env python3
"""Canonical R2 entrypoint enforcing one provider HTTP request per slot.

This wrapper delegates to the guarded R2 control plane while replacing the
historical network model-preflight GET with an offline exact-request binding.
The only provider HTTP request reachable during ``execute-next --execute`` is
the authorized Responses API POST performed by the capture adapter.
"""
from __future__ import annotations

import sys
from typing import Any, Callable

import openai_gpt56_r2 as core
import openai_live_pilot as base

ENTRYPOINT_REFERENCE = "openai_gpt56_r2_single_request.py"
CORE_REFERENCE = "openai_gpt56_r2.py"


def _confirm_model_without_provider_request(
    api_key: str,
    model: str,
    *,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Bind the exact requested alias without making a preflight HTTP call."""
    del api_key, timeout, opener
    if model != core.MODEL:
        raise core.HarnessError(
            "R2_MODEL_SUBSTITUTION",
            "requested model differs from the preregistered R2 alias",
        )
    return {
        "id": model,
        "owned_by": None,
        "verification": "request_bound_response_label_captured",
        "provider_preflight_request_sent": False,
    }


def main(argv: list[str] | None = None) -> int:
    previous_preflight = base._confirm_model_available
    previous_script_reference = core.SCRIPT_REFERENCE
    previous_module_references = set(core.MODULE_REFERENCES)
    try:
        base._confirm_model_available = _confirm_model_without_provider_request
        core.SCRIPT_REFERENCE = ENTRYPOINT_REFERENCE
        core.MODULE_REFERENCES = previous_module_references | {CORE_REFERENCE}
        return core.main(argv)
    finally:
        base._confirm_model_available = previous_preflight
        core.SCRIPT_REFERENCE = previous_script_reference
        core.MODULE_REFERENCES = previous_module_references


if __name__ == "__main__":
    sys.exit(main())
