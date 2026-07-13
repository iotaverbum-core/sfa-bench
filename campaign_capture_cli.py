#!/usr/bin/env python3
"""Offline SFA-Bench governed campaign capture CLI (alpha.2 implementation)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

from sfa_bench.campaigns.capture import (
    CaptureError,
    SyntheticAdapter,
    build_review_bundle,
    canonical_bytes,
    capture_attempt,
    initialize_run,
    judge_run,
    recover_run,
    seal_run,
    strict_json_file,
    validate_authorization,
    verify_judgment,
    verify_review_bundle,
    verify_run,
)
from sfa_bench.campaigns.capture.canonical import ensure_no_reparse_ancestors


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


def _init(args: argparse.Namespace) -> dict[str, Any]:
    campaign = _json(args.campaign)
    lock = _json(args.lock)
    authorization = _json(args.authorization)
    request_bytes = Path(args.request).read_bytes()
    adapter = SyntheticAdapter(args.mode)
    run_dir = initialize_run(
        campaign=campaign,
        lock=lock,
        authorization=authorization,
        request_bytes=request_bytes,
        adapter=adapter,
        repo_root=ROOT,
        output_root=_capture_root(),
        observed_at=args.now,
    )
    return {"command": "init", "status": "ok", "run": str(run_dir)}


def _validate_authorization(args: argparse.Namespace) -> dict[str, Any]:
    campaign = _json(args.campaign)
    lock = _json(args.lock)
    authorization = _json(args.authorization)
    request_bytes = Path(args.request).read_bytes()
    summary = validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=SyntheticAdapter(args.mode),
    )
    return {"command": "validate-authorization", "status": "ok", "authorization": summary}


def _capture(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = _run_path(args.run)
    request_bytes = Path(args.request).read_bytes()
    adapter = SyntheticAdapter(args.mode)
    attempt = capture_attempt(
        run_dir,
        request_bytes=request_bytes,
        adapter=adapter,
        repo_root=ROOT,
        observed_at=args.now,
        attempt_number=args.attempt,
    )
    return {
        "command": "capture-synthetic",
        "status": "ok",
        "attempt_number": attempt["attempt_number"],
        "transport_status": attempt["transport_status"],
        "complete": attempt["complete"],
        "warnings": attempt["warnings"],
    }


def _recover(args: argparse.Namespace) -> dict[str, Any]:
    partial = Path(args.partial_file).read_bytes() if args.partial_file else None
    record = recover_run(
        _run_path(args.run),
        action=args.action,
        reason=args.reason,
        observed_at=args.now,
        partial_bytes=partial,
    )
    return {
        "command": "recover",
        "status": "ok",
        "action": args.action,
        "recovery_digest": record["recovery_digest"],
        "execution_outcome": "unknown",
    }


def _seal(args: argparse.Namespace) -> dict[str, Any]:
    manifest = seal_run(_run_path(args.run), repo_root=ROOT, observed_at=args.now)
    return {
        "command": "seal",
        "status": "ok",
        "manifest_sha256": manifest["manifest_sha256"],
        "capture_state": manifest["capture_state"],
        "ratification_status": "unratified",
    }


def _judge(args: argparse.Namespace) -> dict[str, Any]:
    artifact = judge_run(
        _run_path(args.run),
        repo_root=ROOT,
        task_reference=args.task_reference,
        observed_at=args.now,
    )
    return {
        "command": "judge",
        "status": "ok",
        "judgment_sha256": artifact["judgment_sha256"],
        "verdict": artifact["deterministic_result"]["verdict"],
        "score": artifact["deterministic_result"]["score"],
        "ratification_status": "unratified",
    }


def _bundle(args: argparse.Namespace) -> dict[str, Any]:
    bundle = build_review_bundle(
        _run_path(args.run),
        repo_root=ROOT,
        observed_at=args.now,
    )
    return {
        "command": "bundle",
        "status": "ok",
        "bundle_sha256": bundle["bundle_sha256"],
        "ratification_status": "unratified",
        "packaging_is_approval": False,
    }


def _verify(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = _run_path(args.run)
    report = verify_run(run_dir, repo_root=ROOT)
    if report["lifecycle_state"] == "judged":
        verify_judgment(run_dir, repo_root=ROOT)
        report["judgment"] = "verified"
    if (run_dir / "review-bundle.json").is_file():
        verify_review_bundle(run_dir, repo_root=ROOT)
        report["review_bundle"] = "verified"
    return {"command": "verify", "status": "ok", "integrity": report}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-authorization")
    for subparser in (validate,):
        subparser.add_argument("--campaign", required=True)
        subparser.add_argument("--lock", required=True)
        subparser.add_argument("--authorization", required=True)
        subparser.add_argument("--request", required=True)
        subparser.add_argument("--mode", choices=sorted(SyntheticAdapter.MODES), default="valid_json_object")

    init = subparsers.add_parser("init")
    init.add_argument("--campaign", required=True)
    init.add_argument("--lock", required=True)
    init.add_argument("--authorization", required=True)
    init.add_argument("--request", required=True)
    init.add_argument("--mode", choices=sorted(SyntheticAdapter.MODES), default="valid_json_object")
    init.add_argument("--now", required=True)

    capture = subparsers.add_parser("capture-synthetic")
    capture.add_argument("--run", required=True)
    capture.add_argument("--request", required=True)
    capture.add_argument("--mode", choices=sorted(SyntheticAdapter.MODES), required=True)
    capture.add_argument("--attempt", type=int)
    capture.add_argument("--now", required=True)

    recover = subparsers.add_parser("recover")
    recover.add_argument("--run", required=True)
    recover.add_argument("--action", choices=["record_interruption", "resume", "abort"], required=True)
    recover.add_argument("--reason", required=True)
    recover.add_argument("--partial-file")
    recover.add_argument("--now", required=True)

    seal = subparsers.add_parser("seal")
    seal.add_argument("--run", required=True)
    seal.add_argument("--now", required=True)

    judge = subparsers.add_parser("judge")
    judge.add_argument("--run", required=True)
    judge.add_argument("--task-reference", required=True)
    judge.add_argument("--now", required=True)

    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--run", required=True)
    bundle.add_argument("--now", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--run", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        handlers = {
            "validate-authorization": _validate_authorization,
            "init": _init,
            "capture-synthetic": _capture,
            "recover": _recover,
            "seal": _seal,
            "judge": _judge,
            "bundle": _bundle,
            "verify": _verify,
        }
        _emit(handlers[args.command](args))
        return 0
    except (CaptureError, CliUsageError, FileNotFoundError, OSError) as exc:
        if isinstance(exc, CaptureError):
            issue = exc.to_dict()
        else:
            issue = {"code": "CLI_INPUT_ERROR", "path": "$", "message": str(exc)}
        _emit({"status": "error", "issue": issue})
        return 2


if __name__ == "__main__":
    sys.exit(main())
