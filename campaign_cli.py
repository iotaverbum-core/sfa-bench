#!/usr/bin/env python3
"""Validate V2 campaign documents and create or verify benchmark locks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from sfa_bench.campaigns.locking import (
    LockingError,
    RepositoryContext,
    build_benchmark_lock,
    canonical_json,
    verify_benchmark_lock,
    write_lock_atomic,
)
from sfa_bench.campaigns.protocol import (
    issue,
    validate_campaign,
    validate_candidate_manifest,
)


ROOT = Path(__file__).resolve().parent
LOCK_OUTPUT_ROOT = ROOT / "out" / "campaign_locks"
# Tests and isolated verification may inject an already observed source context.
# The user-facing CLI leaves this as None and observes Git/package state itself.
LOCK_CONTEXT: RepositoryContext | None = None


class JsonInputError(ValueError):
    """Raised for an unreadable or malformed JSON input."""

    def __init__(self, code: str, path: Path, message: str):
        self.issue = issue(code, str(path), message)
        super().__init__(message)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        _emit(
            {
                "command": "argument-parse",
                "ok": False,
                "issues": [issue("INVALID_ARGUMENTS", "$", message)],
            }
        )
        raise SystemExit(2)


def _emit(result: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    )


def _load_json(path_text: str) -> Any:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JsonInputError("INPUT_NOT_FOUND", path, "input file does not exist") from exc
    except UnicodeDecodeError as exc:
        raise JsonInputError("INPUT_NOT_UTF8", path, "input file is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise JsonInputError(
            "MALFORMED_JSON",
            path,
            f"invalid JSON at line {exc.lineno}, column {exc.colno}",
        ) from exc


def _input_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _result(command: str, issues: list[dict[str, str]], **extra: Any) -> int:
    ok = not issues
    payload: dict[str, Any] = {"command": command, "ok": ok, "issues": issues}
    payload.update(extra)
    _emit(payload)
    return 0 if ok else 2


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_campaign_command(args: argparse.Namespace) -> int:
    campaign = _load_json(args.campaign)
    issues = validate_campaign(campaign)
    if (
        not issues
        and isinstance(campaign, dict)
        and campaign.get("run_classification") == "official"
    ):
        lock_reference = campaign.get("benchmark_lock")
        if isinstance(lock_reference, dict):
            lock_path = lock_reference.get("path")
            if isinstance(lock_path, str):
                lock = _load_json(lock_path)
                issues.extend(
                    verify_benchmark_lock(
                        campaign, lock, ROOT, context=LOCK_CONTEXT
                    )
                )
    return _result("validate", issues)


def _validate_candidate_command(args: argparse.Namespace) -> int:
    manifest = _load_json(args.manifest)
    return _result("validate-candidate", validate_candidate_manifest(manifest))


def _lock_command(args: argparse.Namespace) -> int:
    campaign = _load_json(args.campaign)
    lock = build_benchmark_lock(campaign, ROOT, context=LOCK_CONTEXT)
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
    else:
        output = LOCK_OUTPUT_ROOT / f"{campaign['campaign_id']}.benchmark-lock.json"
    written = write_lock_atomic(lock, output, LOCK_OUTPUT_ROOT)
    return _result(
        "lock",
        [],
        lock_digest=lock["lock_digest"],
        output=_display_path(written),
    )


def _verify_lock_command(args: argparse.Namespace) -> int:
    campaign = _load_json(args.campaign)
    lock = _load_json(args.lock)
    issues = verify_benchmark_lock(campaign, lock, ROOT, context=LOCK_CONTEXT)
    digest = lock.get("lock_digest") if isinstance(lock, dict) else None
    return _result("verify-lock", issues, lock_digest=digest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate", help="validate a campaign pre-registration"
    )
    validate.add_argument("--campaign", required=True)
    validate.set_defaults(handler=_validate_campaign_command)

    lock = subparsers.add_parser("lock", help="create a deterministic benchmark lock")
    lock.add_argument("--campaign", required=True)
    lock.add_argument(
        "--output",
        help="new JSON path beneath out/campaign_locks; existing files are refused",
    )
    lock.set_defaults(handler=_lock_command)

    verify = subparsers.add_parser(
        "verify-lock", help="verify a benchmark lock against current inputs"
    )
    verify.add_argument("--campaign", required=True)
    verify.add_argument("--lock", required=True)
    verify.set_defaults(handler=_verify_lock_command)

    candidate = subparsers.add_parser(
        "validate-candidate", help="validate a provider-neutral candidate manifest"
    )
    candidate.add_argument("--manifest", required=True)
    candidate.set_defaults(handler=_validate_candidate_command)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return args.handler(args)
    except JsonInputError as exc:
        return _result(args.command, [exc.issue])
    except LockingError as exc:
        return _result(args.command, exc.issues)
    except OSError as exc:
        return _result(
            args.command,
            [issue("FILESYSTEM_ERROR", "$", f"filesystem operation failed: {exc}")],
        )


if __name__ == "__main__":
    sys.exit(main())
