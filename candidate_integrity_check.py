#!/usr/bin/env python3
"""Run the SFA-Bench candidate-integrity and evidence-lineage checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from sfa_bench.frontier_delta.candidate_adapter import score_response
from sfa_bench.frontier_delta.candidate_evidence import (
    verify_successor,
)
from sfa_bench.frontier_delta.tasks import load_tasks


ROOT = Path(__file__).resolve().parent
RAW_EVIDENCE = ROOT / "out" / "fable5_failure_delta" / "raw_outputs.jsonl"
PREDECESSOR = ROOT / "out" / "fable5_failure_delta" / "scored_results.json"
SUCCESSOR = (
    ROOT
    / "out"
    / "candidate_evidence_successors"
    / "fable5-frontier-delta-20260703-corrected-v2-alpha1.json"
)
EXPECTED_RAW_SHA256 = (
    "2b46cd926bddf7bc8dd04c6b8039dd69bd18d9febb5d350c73acd4309d833998"
)
EXPECTED_PREDECESSOR_SHA256 = (
    "ab12bfea98be01ed2ce93d796c4276b5bfdde6831efc87af0ad4c41541ecec0d"
)
INVALID_SAMPLES: tuple[tuple[str, str], ...] = (
    ("", "no_model_output"),
    (" \t\r\n", "no_model_output"),
    ("I cannot comply with this request.", "unparseable_model_output"),
    ("ordinary plaintext", "unparseable_model_output"),
    ('{"broken":', "unparseable_model_output"),
    ("[]", "invalid_model_output"),
    ('"text"', "invalid_model_output"),
    ("42", "invalid_model_output"),
    ("true", "invalid_model_output"),
    ("null", "invalid_model_output"),
    ('{"value":NaN}', "unparseable_model_output"),
    ('{"value":Infinity}', "unparseable_model_output"),
    ('{"value":-Infinity}', "unparseable_model_output"),
    ('{"value":1e309}', "unparseable_model_output"),
    (r'{"value":"\ud800"}', "unparseable_model_output"),
    (r'{"value":"\udc00"}', "unparseable_model_output"),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _check_invalid_boundaries() -> int:
    checks = 0
    for task in load_tasks():
        for response_text, expected_status in INVALID_SAMPLES:
            first = score_response(task, response_text)
            second = score_response(task, response_text)
            if first != second:
                raise ValueError(
                    f"nondeterministic invalid result: {task['task_id']}"
                )
            if (
                first.get("score") != 0.0
                or first.get("verdict") != "fail"
                or first.get("canonical_output") is not None
                or first.get("detected_failure_modes") != [expected_status]
                or first.get("parse_notes", {}).get("candidate_output_status")
                != expected_status
            ):
                raise ValueError(
                    f"invalid-output boundary failed: {task['task_id']} "
                    f"{expected_status}"
                )
            checks += 1
    return checks


def main() -> int:
    print("SFA-Bench v2.0.0-alpha.1 candidate-integrity check")
    print("=" * 56)
    try:
        raw_digest = _sha256_file(RAW_EVIDENCE)
        predecessor_digest = _sha256_file(PREDECESSOR)
        if raw_digest != EXPECTED_RAW_SHA256:
            raise ValueError("historical raw evidence digest changed")
        if predecessor_digest != EXPECTED_PREDECESSOR_SHA256:
            raise ValueError("historical predecessor digest changed")

        boundary_checks = _check_invalid_boundaries()
        verification = verify_successor(
            SUCCESSOR, RAW_EVIDENCE, PREDECESSOR
        )
        successor = _load_json(SUCCESSOR)
        corrected = successor["scoring_status"]["successor"]
        if corrected.get("total_score") != 0.6875:
            raise ValueError("corrected successor score is not the reviewed value")
        if corrected.get("status") != "corrected_offline_rederivation_not_ratified":
            raise ValueError("corrected successor status is not bounded")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"failure: {exc}")
        print("final status: FAIL")
        return 2

    print(f"historical raw evidence: PRESERVED ({raw_digest})")
    print(f"historical predecessor: PRESERVED ({predecessor_digest})")
    print(f"invalid-output lane checks: PASS ({boundary_checks})")
    print(
        "successor re-derivation: PASS "
        f"({verification['canonical_artifact_sha256']})"
    )
    print("provider calls: NONE")
    print("=" * 56)
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
