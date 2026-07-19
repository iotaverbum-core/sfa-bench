#!/usr/bin/env python3
"""Explicit execution-only OpenAI Responses capture CLI for SFA-Bench.

This command never constructs request content, retries automatically, judges,
ratifies, promotes, publishes, or releases evidence. The exact request file and
adapter identity must already be bound by the execution authorization and lock.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

from sfa_bench.campaigns.capture import (
    CaptureError,
    canonical_bytes,
    capture_attempt,
    initialize_run,
    strict_json_file,
    validate_authorization,
)
from sfa_bench.campaigns.capture.canonical import ensure_no_reparse_ancestors
from sfa_bench.campaigns.capture.openai_responses import OpenAIResponsesAdapter

ROOT = Path(__file__).resolve().parent


class CliUsageError(ValueError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(canonical_bytes(value).decode("utf-8") + "\n")


def _capture_root() -> Path:
    configured = os.environ.get("SFA_CAMPAIGN_CAPTURE_ROOT")
    return Path(configured).absolute() if configured else ROOT / "out" / "campaign_runs"


def _run_path(value: str) -> Path:
    root = _capture_root()
    path = Path(value).absolute()
    try:
        relative = path.relative_to(root.absolute())
    except ValueError as exc:
        raise CaptureError("PATH_ESCAPE", "run path must remain under the configured capture root") from exc
    if len(relative.parts) != 2:
        raise CaptureError("INVALID_RUN_PATH", "run path must be <campaign_id>/<execution_id>")
    ensure_no_reparse_ancestors(root, path)
    return path


def _json(path_text: str) -> dict[str, Any]:
    value = strict_json_file(Path(path_text))
    if not isinstance(value, dict):
        raise CaptureError("MALFORMED_DOCUMENT", "input JSON must be an object", path_text)
    return value


def _adapter(args: argparse.Namespace) -> OpenAIResponsesAdapter:
    return OpenAIResponsesAdapter(timeout_seconds=args.timeout)


def _validate(args: argparse.Namespace) -> dict[str, Any]:
    campaign = _json(args.campaign)
    lock = _json(args.lock)
    authorization = _json(args.authorization)
    request_bytes = Path(args.request).read_bytes()
    summary = validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=_adapter(args),
    )
    return {"command": "validate-authorization", "status": "ok", "authorization": summary}


def _init(args: argparse.Namespace) -> dict[str, Any]:
    request_bytes = Path(args.request).read_bytes()
    run_dir = initialize_run(
        campaign=_json(args.campaign),
        lock=_json(args.lock),
        authorization=_json(args.authorization),
        request_bytes=request_bytes,
        adapter=_adapter(args),
        repo_root=ROOT,
        output_root=_capture_root(),
        observed_at=args.now,
    )
    return {"command": "init-openai", "status": "ok", "run": str(run_dir)}


def _capture(args: argparse.Namespace) -> dict[str, Any]:
    attempt = capture_attempt(
        _run_path(args.run),
        request_bytes=Path(args.request).read_bytes(),
        adapter=_adapter(args),
        repo_root=ROOT,
        observed_at=args.now,
        attempt_number=args.attempt,
    )
    return {
        "command": "capture-openai",
        "status": "ok",
        "attempt_number": attempt["attempt_number"],
        "transport_status": attempt["transport_status"],
        "complete": attempt["complete"],
        "warnings": attempt["warnings"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-authorization")
    init = subparsers.add_parser("init")
    for subparser in (validate, init):
        subparser.add_argument("--campaign", required=True)
        subparser.add_argument("--lock", required=True)
        subparser.add_argument("--authorization", required=True)
        subparser.add_argument("--request", required=True)
        subparser.add_argument("--timeout", type=float, default=120.0)
    init.add_argument("--now", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--run", required=True)
    capture.add_argument("--request", required=True)
    capture.add_argument("--attempt", type=int)
    capture.add_argument("--timeout", type=float, default=120.0)
    capture.add_argument("--now", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        handlers = {
            "validate-authorization": _validate,
            "init": _init,
            "capture": _capture,
        }
        _emit(handlers[args.command](args))
        return 0
    except (CaptureError, CliUsageError, FileNotFoundError, OSError) as exc:
        issue = exc.to_dict() if isinstance(exc, CaptureError) else {
            "code": "CLI_INPUT_ERROR",
            "path": "$",
            "message": str(exc),
        }
        _emit({"status": "error", "issue": issue})
        return 2


if __name__ == "__main__":
    sys.exit(main())
