#!/usr/bin/env python3
"""Run the offline SFA-Bench V2 campaign-protocol checks."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from sfa_bench.campaigns.locking import (
    build_benchmark_lock,
    verify_benchmark_lock,
)
from sfa_bench.campaigns.protocol import (
    BENCHMARK_LOCK_SCHEMA,
    CAMPAIGN_SCHEMA,
    CANDIDATE_MANIFEST_SCHEMA,
    EXECUTION_PLAN_SCHEMA,
    RATIFICATION_POLICY_SCHEMA,
    validate_campaign,
    validate_candidate_manifest,
)


ROOT = Path(__file__).resolve().parent
CAMPAIGN = ROOT / "campaigns" / "examples" / "gpt56-draft-preregistration.json"
CANDIDATE = (
    ROOT / "campaigns" / "examples" / "gpt56-draft-candidate-manifest.json"
)
SCHEMAS = {
    "benchmark-lock.schema.json": BENCHMARK_LOCK_SCHEMA,
    "campaign-preregistration.schema.json": CAMPAIGN_SCHEMA,
    "candidate-manifest.schema.json": CANDIDATE_MANIFEST_SCHEMA,
    "execution-plan.schema.json": EXECUTION_PLAN_SCHEMA,
    "ratification-policy.schema.json": RATIFICATION_POLICY_SCHEMA,
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _check_schema(path: Path, schema_version: str) -> None:
    schema = _load_object(path)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError(f"unexpected JSON Schema dialect: {path}")
    if schema.get("type") != "object" or not isinstance(schema.get("required"), list):
        raise ValueError(f"schema has no object/required contract: {path}")
    version_contract = schema.get("properties", {}).get("schema_version", {})
    if version_contract.get("const") != schema_version:
        raise ValueError(f"schema version contract mismatch: {path}")


def main() -> int:
    print("SFA-Bench v2.0.0-alpha.1 campaign-protocol check")
    print("=" * 56)
    try:
        campaign = _load_object(CAMPAIGN)
        candidate = _load_object(CANDIDATE)
        campaign_issues = validate_campaign(campaign)
        candidate_issues = validate_candidate_manifest(candidate)
        if campaign_issues:
            raise ValueError(f"example campaign invalid: {campaign_issues}")
        if candidate_issues:
            raise ValueError(f"example candidate invalid: {candidate_issues}")
        for filename, schema_version in sorted(SCHEMAS.items()):
            _check_schema(ROOT / "campaigns" / "schemas" / filename, schema_version)

        first = build_benchmark_lock(
            campaign,
            ROOT,
            envelope={"created_at": "2026-07-11T00:00:00Z"},
        )
        second = build_benchmark_lock(
            campaign,
            ROOT,
            envelope={"created_at": "2099-01-01T00:00:00Z"},
        )
        if first["lock_digest"] != second["lock_digest"]:
            raise ValueError("nondeterministic envelope changed the lock digest")
        lock_issues = verify_benchmark_lock(campaign, first, ROOT)
        if lock_issues:
            raise ValueError(f"benchmark lock verification failed: {lock_issues}")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"failure: {exc}")
        print("final status: FAIL")
        return 2

    print("draft campaign validation: PASS")
    print("candidate manifest validation: PASS")
    print(f"machine-readable schemas: PASS ({len(SCHEMAS)})")
    print(f"deterministic benchmark lock: PASS ({first['lock_digest']})")
    print("provider calls: NONE")
    print("=" * 56)
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
