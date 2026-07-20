#!/usr/bin/env python3
"""Close one fully ratified campaign cohort without mutating source evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
from pathlib import Path
import sys
from typing import Any

from sfa_bench.campaigns.capture.canonical import CaptureError, canonical_bytes
from sfa_bench.campaigns.cohort_closure import (
    build_closure_records,
    load_member,
    read_closure_spec,
    write_closure_records,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_SPEC = "campaigns/examples/openai-gpt56-tier-pilot-closure-spec.json"


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CaptureError("CLI_INPUT_ERROR", message)


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(canonical_bytes(value).decode("utf-8") + "\n")


def _configured_root(name: str, fallback: Path) -> Path:
    configured = os.environ.get(name)
    return Path(configured).absolute() if configured else fallback


def _now(value: str | None) -> str:
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
    return parsed.isoformat(timespec="seconds")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--operator", required=True, help="declared human operator identity")
    parser.add_argument("--spec", default=DEFAULT_SPEC, help="repository-relative closure spec")
    parser.add_argument("--capture-root", help="defaults to out/campaign_runs")
    parser.add_argument("--ratification-root", help="defaults to out/campaign_ratifications")
    parser.add_argument("--output-root", help="defaults to out/campaign_cohort_closures")
    parser.add_argument("--now", help="timezone-qualified ISO timestamp; defaults to current UTC time")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        operator = args.operator.strip() if isinstance(args.operator, str) else ""
        if not operator or len(operator) > 300:
            raise CaptureError("INVALID_OPERATOR", "operator identity must contain 1-300 characters")

        spec_path = Path(args.spec)
        if not spec_path.is_absolute():
            spec_path = ROOT / spec_path
        spec_path = spec_path.resolve()
        try:
            spec_reference = spec_path.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise CaptureError("CLOSURE_SPEC_OUTSIDE_REPOSITORY", "closure spec must be inside the repository") from exc
        spec, spec_sha = read_closure_spec(spec_path)

        protocol_path = (ROOT / spec["protocol_reference"]).resolve()
        try:
            protocol_path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise CaptureError("COHORT_PROTOCOL_OUTSIDE_REPOSITORY", "cohort protocol must be inside the repository") from exc
        protocol_sha = hashlib.sha256(protocol_path.read_bytes()).hexdigest()

        capture_root = (
            Path(args.capture_root).absolute()
            if args.capture_root
            else _configured_root("SFA_CAMPAIGN_CAPTURE_ROOT", ROOT / "out" / "campaign_runs")
        )
        ratification_root = (
            Path(args.ratification_root).absolute()
            if args.ratification_root
            else _configured_root("SFA_CAMPAIGN_RATIFICATION_ROOT", ROOT / "out" / "campaign_ratifications")
        )
        output_root = (
            Path(args.output_root).absolute()
            if args.output_root
            else _configured_root("SFA_CAMPAIGN_COHORT_CLOSURE_ROOT", ROOT / "out" / "campaign_cohort_closures")
        )

        members = [
            load_member(
                item,
                capture_root=capture_root,
                ratification_root=ratification_root,
                protocol_reference=spec["protocol_reference"],
                protocol_sha256=protocol_sha,
            )
            for item in spec["members"]
        ]
        record, lineage = build_closure_records(
            spec=spec,
            spec_reference=spec_reference,
            spec_file_sha256=spec_sha,
            protocol_sha256=protocol_sha,
            members=members,
            closed_by=operator,
            created_at=_now(args.now),
        )
        target = write_closure_records(output_root, record, lineage)
        _emit(
            {
                "command": "campaign-cohort-closure",
                "status": "ok",
                "outcome": record["outcome"]["class"],
                "closure_id": record["closure_id"],
                "cohort_id": record["cohort"]["cohort_id"],
                "member_count": record["cohort"]["member_count"],
                "verdict_counts": record["descriptive_summary"]["verdict_counts"],
                "closure_record_sha256": record["closure_record_sha256"],
                "closure_lineage_sha256": lineage["closure_lineage_sha256"],
                "output": str(target),
                "capture_runs_mutated": False,
                "ratification_records_mutated": False,
                "model_endorsement": False,
                "ranking": False,
                "promotion": False,
                "publication": False,
                "release": False,
            }
        )
        return 0
    except (CaptureError, FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        issue = exc.to_dict() if isinstance(exc, CaptureError) else {
            "code": "COHORT_CLOSURE_ERROR",
            "path": "$",
            "message": str(exc),
        }
        _emit({"status": "error", "issue": issue})
        return 2


if __name__ == "__main__":
    sys.exit(main())
