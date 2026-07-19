#!/usr/bin/env python3
"""Prepare and optionally execute one governed OpenAI SFA-Bench pilot capture.

Preparation verifies the exact model identifier, freezes campaign inputs, builds
one exact request, and seals execution-only authorization. A provider generation
occurs only when ``--execute`` is supplied. This command never retries, judges,
ratifies, promotes, publishes, or releases evidence.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from typing import Any, Callable
from urllib import error, parse, request as urllib_request
import uuid

from sfa_bench.campaigns.capture import (
    AUTHORIZATION_SCHEMA,
    CaptureError,
    canonical_bytes,
    capture_attempt,
    initialize_run,
    seal_authorization,
    sha256_bytes,
    strict_json_file,
    validate_authorization,
)
from sfa_bench.campaigns.capture.canonical import validate_timestamp
from sfa_bench.campaigns.capture.openai_responses import OpenAIResponsesAdapter
from sfa_bench.campaigns.locking import (
    LockingError,
    _binding_entries,
    binding_set_digest,
    build_benchmark_lock,
    canonical_json,
    package_release_identifier,
    reference_digest,
)
from sfa_bench.campaigns.protocol import validate_campaign
from sfa_bench.frontier_delta.candidate_adapter import build_blinded_prompt

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "gpt-5.6"
DEFAULT_MAX_OUTPUT_TOKENS = 1000
MODELS_ENDPOINT = "https://api.openai.com/v1/models"
TEMPLATE_REFERENCE = "campaigns/examples/gpt56-draft-preregistration.json"
SYSTEM_PROMPT_REFERENCE = "campaigns/examples/prompts/gpt56-study-system-prompt.txt"
TASK_REFERENCE = "sfa_bench/frontier_delta/tasks/memory_boundary_001.json"
RULE_REFERENCE = "sfa_bench/frontier_delta/scorers"
TAXONOMY_REFERENCE = "families.json"
NORMALIZER_REFERENCE = "sfa_bench/frontier_delta/candidate_adapter.py"
CAMPAIGN_ID = "openai-gpt56-memory-boundary-pilot-alpha2"


class PilotError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(canonical_bytes(value).decode("utf-8") + "\n")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise PilotError("GIT_PROVENANCE_UNAVAILABLE", result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def _capture_root() -> Path:
    configured = os.environ.get("SFA_CAMPAIGN_CAPTURE_ROOT")
    return Path(configured).absolute() if configured else ROOT / "out" / "campaign_runs"


def _api_key() -> str:
    value = os.environ.get("OPENAI_API_KEY")
    if not isinstance(value, str) or not value.strip():
        raise PilotError("OPENAI_API_KEY_MISSING", "OPENAI_API_KEY is not available to this process")
    return value.strip()


def _confirm_model_available(
    api_key: str,
    model: str,
    *,
    timeout: float,
    opener: Callable[..., Any] = urllib_request.urlopen,
) -> dict[str, Any]:
    endpoint = MODELS_ENDPOINT + "/" + parse.quote(model, safe="")
    outbound = urllib_request.Request(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(outbound, timeout=timeout) as response:
            body = response.read()
    except error.HTTPError as exc:
        if exc.code == 404:
            raise PilotError("OPENAI_MODEL_NOT_AVAILABLE", f"the account does not expose exact model {model!r}") from exc
        if exc.code in {401, 403}:
            raise PilotError("OPENAI_AUTHORIZATION_FAILED", "the API key cannot retrieve the requested model") from exc
        raise PilotError("OPENAI_MODEL_PREFLIGHT_HTTP_ERROR", f"model preflight returned HTTP {exc.code}") from exc
    except (TimeoutError, socket.timeout, error.URLError, OSError) as exc:
        raise PilotError("OPENAI_MODEL_PREFLIGHT_TRANSPORT_ERROR", "model preflight could not reach OpenAI") from exc
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PilotError("OPENAI_MODEL_PREFLIGHT_INVALID", "model preflight returned malformed JSON") from exc
    if not isinstance(document, dict) or document.get("object") != "model" or document.get("id") != model:
        raise PilotError("OPENAI_MODEL_IDENTITY_MISMATCH", "model preflight did not return the exact requested identifier")
    return {"id": model, "owned_by": document.get("owned_by")}


def _group_digest(paths: list[str], issue_path: str) -> str:
    return binding_set_digest(_binding_entries(ROOT, paths, issue_path))


def _build_campaign(model: str, repository_commit: str) -> dict[str, Any]:
    template = strict_json_file(ROOT / TEMPLATE_REFERENCE)
    if not isinstance(template, dict):
        raise PilotError("INVALID_CAMPAIGN_TEMPLATE", "campaign template must be a JSON object")
    campaign = copy.deepcopy(template)
    release_identifier = package_release_identifier(ROOT, repository_commit)
    case_paths = [TASK_REFERENCE]
    rule_paths = [RULE_REFERENCE]
    taxonomy_paths = [TAXONOMY_REFERENCE]
    adapter = OpenAIResponsesAdapter()

    campaign.update(
        {
            "campaign_id": CAMPAIGN_ID,
            "campaign_title": "OpenAI GPT-5.6 Memory Boundary Pilot",
            "status": "preregistered",
            "research_question": "Does the exact available OpenAI candidate preserve the frozen memory-state boundary in one governed pilot capture?",
            "candidate_provider": "OpenAI",
            "provider_model_identifier": model,
            "candidate_snapshot_or_alias_status": "mutable_alias",
            "mutable_alias_use_declared": True,
            "api_or_execution_surface": "OpenAI Responses API POST /v1/responses",
            "tool_permissions": ["none"],
            "reasoning_configuration": {"mode": "provider_default"},
            "sampling_configuration": {"mode": "provider_default"},
            "run_count": 1,
            "run_classification": "pilot",
            "benchmark_commit_sha": repository_commit,
            "verifier_commit_sha": repository_commit,
            "adapter_version": adapter.adapter_version,
            "release_identifier": release_identifier,
            "frozen_case_set_digest": _group_digest(case_paths, "$.benchmark_inputs.case_paths"),
            "frozen_rule_digest": _group_digest(rule_paths, "$.benchmark_inputs.rule_paths"),
            "frozen_taxonomy_digest": _group_digest(taxonomy_paths, "$.benchmark_inputs.taxonomy_paths"),
            "declared_limitations": [
                "No provider response had been observed when this pilot was preregistered.",
                "The requested provider identifier is explicitly treated as a mutable alias.",
                "Generation reproducibility may be limited; judgment reproducibility is mandatory.",
                "A captured or passing result would not establish legal or regulatory conformity.",
            ],
        }
    )
    campaign["system_prompt"] = {
        "reference": SYSTEM_PROMPT_REFERENCE,
        "sha256": reference_digest(ROOT, SYSTEM_PROMPT_REFERENCE),
    }
    campaign["user_prompt_or_case_set"] = {
        "reference": TASK_REFERENCE,
        "sha256": reference_digest(ROOT, TASK_REFERENCE),
    }
    campaign["benchmark_inputs"] = {
        "adapter_paths": [adapter.implementation_path],
        "case_paths": case_paths,
        "evidence_paths": case_paths,
        "normalizer_paths": [NORMALIZER_REFERENCE],
        "rule_paths": rule_paths,
        "schema_paths": [
            "campaign_cli.py",
            "campaign_capture_cli.py",
            "openai_capture_cli.py",
            "openai_live_pilot.py",
            "campaigns/alpha2/schemas",
            "campaigns/schemas",
            "sfa_bench/campaigns/capture",
            "sfa_bench/campaigns/locking.py",
            "sfa_bench/campaigns/protocol.py",
        ],
        "taxonomy_paths": taxonomy_paths,
        "declared_commands": [
            f"py -3 openai_live_pilot.py --operator <declared-operator> --model {model}",
            f"py -3 openai_live_pilot.py --operator <declared-operator> --model {model} --execute",
        ],
    }
    campaign["execution_plan"].update(
        {
            "campaign_id": CAMPAIGN_ID,
            "planned_repetitions": 1,
            "run_classification": "pilot",
            "output_path": f"out/campaign_runs/{CAMPAIGN_ID}",
        }
    )
    campaign.pop("benchmark_lock", None)
    issues = validate_campaign(campaign)
    if issues:
        raise PilotError("CAMPAIGN_VALIDATION_FAILED", json.dumps(issues, sort_keys=True, separators=(",", ":")))
    return campaign


def _build_request(model: str, max_output_tokens: int) -> bytes:
    task = strict_json_file(ROOT / TASK_REFERENCE)
    if not isinstance(task, dict):
        raise PilotError("INVALID_TASK", "pilot task must be a JSON object")
    instructions = (ROOT / SYSTEM_PROMPT_REFERENCE).read_text(encoding="utf-8")
    prompt = build_blinded_prompt(task, neutral_case_id="case-001")
    return canonical_bytes(
        {
            "input": prompt,
            "instructions": instructions,
            "max_output_tokens": max_output_tokens,
            "model": model,
            "store": False,
        }
    )


def _now(value: str | None) -> str:
    observed = value or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    validate_timestamp(observed, "$.observed_at")
    return observed


def _execution_id(value: str | None) -> str:
    if value:
        if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value) is None:
            raise PilotError("INVALID_EXECUTION_ID", "execution id must be 1-80 lowercase safe characters")
        return value
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%sz")
    return f"openai-pilot-{stamp}-{uuid.uuid4().hex[:8]}"


def _write_pack(
    *,
    campaign: dict[str, Any],
    lock: dict[str, Any],
    authorization: dict[str, Any],
    request_bytes: bytes,
    execution_id: str,
) -> Path:
    root = _capture_root()
    root.mkdir(parents=True, exist_ok=True)
    pack = root / f"_prepared-{execution_id}"
    pack.mkdir(exist_ok=False)
    (pack / "campaign.json").write_text(canonical_json(campaign), encoding="utf-8", newline="\n")
    (pack / "benchmark-lock.json").write_text(canonical_json(lock), encoding="utf-8", newline="\n")
    (pack / "execution-authorization.json").write_text(canonical_json(authorization), encoding="utf-8", newline="\n")
    (pack / "request.json").write_bytes(request_bytes)
    return pack


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator", required=True, help="declared human operator identity")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="exact OpenAI model identifier; no substitution occurs")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--execution-id")
    parser.add_argument("--now", help="timezone-qualified ISO timestamp; defaults to local current time")
    parser.add_argument("--execute", action="store_true", help="send the single authorized provider request")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if not isinstance(args.operator, str) or not args.operator.strip() or len(args.operator.strip()) > 200:
            raise PilotError("INVALID_OPERATOR", "operator identity must contain 1-200 characters")
        if not isinstance(args.model, str) or not args.model.strip() or len(args.model.strip()) > 200:
            raise PilotError("INVALID_MODEL", "model identifier must contain 1-200 characters")
        if not 1 <= args.max_output_tokens <= 4096:
            raise PilotError("INVALID_MAX_OUTPUT_TOKENS", "max output tokens must be between 1 and 4096")
        if not isinstance(args.timeout, (int, float)) or isinstance(args.timeout, bool) or args.timeout <= 0:
            raise PilotError("INVALID_TIMEOUT", "timeout must be positive")

        model = args.model.strip()
        api_key = _api_key()
        model_record = _confirm_model_available(api_key, model, timeout=float(args.timeout))
        repository_commit = _git("rev-parse", "HEAD").lower()
        campaign = _build_campaign(model, repository_commit)
        lock = build_benchmark_lock(campaign, ROOT)
        request_bytes = _build_request(model, args.max_output_tokens)
        observed_at = _now(args.now)
        execution_id = _execution_id(args.execution_id)
        adapter = OpenAIResponsesAdapter(timeout_seconds=float(args.timeout))
        authorization = seal_authorization(
            {
                "schema_version": AUTHORIZATION_SCHEMA,
                "authorization_id": f"auth-{execution_id}",
                "campaign_id": campaign["campaign_id"],
                "benchmark_lock_digest": lock["lock_digest"],
                "benchmark_commit": lock["repository_commit"],
                "verifier_commit": lock["verifier_commit"],
                "release_identifier": lock["release_identifier"],
                "execution_id": execution_id,
                "adapter": {
                    "adapter_id": adapter.adapter_id,
                    "adapter_version": adapter.adapter_version,
                    "implementation_path": adapter.implementation_path,
                },
                "request": {
                    "sha256": sha256_bytes(request_bytes),
                    "byte_length": len(request_bytes),
                    "prompt_reference": SYSTEM_PROMPT_REFERENCE,
                    "case_reference": TASK_REFERENCE,
                },
                "retry_policy": {
                    "max_attempts": campaign["retry_policy"]["max_attempts"],
                    "allowed_reasons": campaign["retry_policy"]["retry_conditions"],
                },
                "operator_declaration": {
                    "identity": args.operator.strip(),
                    "authority_type": "declared_human_operator",
                    "authorization_scope": "execution_only",
                },
                "issued_at": observed_at,
                "ratification_status": "unratified",
                "automatic_actions": {"ratify": False, "promote": False, "publish": False, "release": False},
            }
        )
        validate_authorization(
            authorization,
            campaign=campaign,
            lock=lock,
            request_bytes=request_bytes,
            adapter=adapter,
        )
        pack = _write_pack(
            campaign=campaign,
            lock=lock,
            authorization=authorization,
            request_bytes=request_bytes,
            execution_id=execution_id,
        )
        result: dict[str, Any] = {
            "command": "openai-live-pilot",
            "status": "prepared",
            "model": model_record,
            "execution_id": execution_id,
            "benchmark_commit": repository_commit,
            "benchmark_lock_digest": lock["lock_digest"],
            "request_sha256": sha256_bytes(request_bytes),
            "preparation_pack": str(pack),
            "live_request_sent": False,
            "ratification_status": "unratified",
        }
        if args.execute:
            run_dir = initialize_run(
                campaign=campaign,
                lock=lock,
                authorization=authorization,
                request_bytes=request_bytes,
                adapter=adapter,
                repo_root=ROOT,
                output_root=_capture_root(),
                observed_at=observed_at,
            )
            attempt = capture_attempt(
                run_dir,
                request_bytes=request_bytes,
                adapter=adapter,
                repo_root=ROOT,
                observed_at=observed_at,
            )
            result.update(
                {
                    "status": "captured" if attempt["complete"] else "interrupted",
                    "run": str(run_dir),
                    "live_request_sent": True,
                    "attempt_number": attempt["attempt_number"],
                    "transport_status": attempt["transport_status"],
                    "complete": attempt["complete"],
                    "warnings": attempt["warnings"],
                }
            )
        _emit(result)
        return 0
    except PilotError as exc:
        _emit({"status": "error", "issue": {"code": exc.code, "path": "$", "message": exc.message}})
        return 2
    except CaptureError as exc:
        _emit({"status": "error", "issue": exc.to_dict()})
        return 2
    except LockingError as exc:
        _emit({"status": "error", "issues": exc.issues})
        return 2
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
        _emit({"status": "error", "issue": {"code": "PILOT_EXECUTION_ERROR", "path": "$", "message": str(exc)}})
        return 2


if __name__ == "__main__":
    sys.exit(main())
