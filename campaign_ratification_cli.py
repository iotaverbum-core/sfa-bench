#!/usr/bin/env python3
"""Record an explicit human disposition for one verified campaign review bundle."""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
import sys
import uuid
from typing import Any

from sfa_bench.campaigns.capture.canonical import CaptureError, canonical_bytes
from sfa_bench.campaigns.ratification import (
    ACTION_OUTCOME,
    build_ratification_records,
    read_validated_review_bundle,
    write_ratification_records,
)


ROOT = Path(__file__).resolve().parent


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CaptureError("CLI_INPUT_ERROR", message)


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(canonical_bytes(value).decode("utf-8") + "\n")


def _output_root() -> Path:
    configured = os.environ.get("SFA_CAMPAIGN_RATIFICATION_ROOT")
    return Path(configured).absolute() if configured else ROOT / "out" / "campaign_ratifications"


def _action(args: argparse.Namespace) -> str:
    for value in ("prepare", "ratify", "reject", "halt"):
        if getattr(args, value):
            return value
    raise CaptureError("CLI_INPUT_ERROR", "one human action is required")


def _now(value: str | None) -> tuple[str, dt.datetime]:
    if value:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise CaptureError("INVALID_TIMESTAMP", "--now must be timezone-qualified ISO 8601") from exc
        if parsed.tzinfo is None:
            raise CaptureError("INVALID_TIMESTAMP", "--now must include a timezone")
    else:
        parsed = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return parsed.isoformat(timespec="seconds"), parsed.astimezone(dt.timezone.utc)


def _ratification_id(value: str | None, action: str, bundle_sha: str, utc: dt.datetime) -> str:
    if value:
        return value
    stamp = utc.strftime("%Y%m%dt%H%M%Sz").lower()
    return f"rat-{action}-{bundle_sha[:12]}-{stamp}-{uuid.uuid4().hex[:8]}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--review-bundle", required=True, help="path to the secret-free review-bundle.json")
    parser.add_argument("--reviewer", required=True, help="declared human reviewer identity")
    parser.add_argument("--rationale", default="", help="human rationale; required for ratify, reject, and halt")
    parser.add_argument("--ratification-id", help="optional portable id for deterministic operations")
    parser.add_argument("--now", help="timezone-qualified ISO timestamp; defaults to current UTC time")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true", help="prepare a companion record without disposition")
    group.add_argument("--ratify", action="store_true", help="accept the sealed deterministic judgment")
    group.add_argument("--reject", action="store_true", help="dispute the sealed deterministic judgment")
    group.add_argument("--halt", action="store_true", help="defer disposition and halt this evidence workflow")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        action = _action(args)
        source = Path(args.review_bundle).absolute()
        bundle, source_file_sha = read_validated_review_bundle(source)
        created_at, utc = _now(args.now)
        ratification_id = _ratification_id(
            args.ratification_id,
            action,
            bundle["bundle_sha256"],
            utc,
        )
        packet, lineage = build_ratification_records(
            bundle=bundle,
            source_file_sha256=source_file_sha,
            ratification_id=ratification_id,
            action=action,
            reviewer=args.reviewer,
            rationale=args.rationale,
            created_at=created_at,
        )
        target = write_ratification_records(_output_root(), packet, lineage)
        _emit(
            {
                "command": "campaign-ratification",
                "status": "ok",
                "ratification_id": ratification_id,
                "action": action,
                "outcome": ACTION_OUTCOME[action],
                "campaign_id": bundle["campaign_id"],
                "execution_id": bundle["execution_id"],
                "source_bundle_sha256": bundle["bundle_sha256"],
                "judgment_sha256": bundle["deterministic_judgment"]["judgment_sha256"],
                "ratification_packet_sha256": packet["ratification_packet_sha256"],
                "lineage_record_sha256": lineage["lineage_record_sha256"],
                "output": str(target),
                "capture_run_mutated": False,
                "model_endorsement": False,
                "promotion": False,
                "publication": False,
                "release": False,
            }
        )
        return 0
    except (CaptureError, FileNotFoundError, FileExistsError, OSError) as exc:
        issue = exc.to_dict() if isinstance(exc, CaptureError) else {
            "code": "RATIFICATION_IO_ERROR",
            "path": "$",
            "message": str(exc),
        }
        _emit({"status": "error", "issue": issue})
        return 2


if __name__ == "__main__":
    sys.exit(main())
