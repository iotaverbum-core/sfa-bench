"""Deterministic schema and validation for Frontier Delta Suite tasks.

A task is a plain JSON object. This module defines the required shape, the eight
lanes, canonical hashing (reusing the SFA-Bench core), and a deterministic
validator that returns a list of issues (empty == valid). No model, no network,
no wall-clock time.
"""
from __future__ import annotations

from typing import Any

from sfa.hashing import sha256_hex

SUITE_VERSION = "frontier_delta_v0"
TASK_SCHEMA_VERSION = "sfa_bench.frontier_delta.task.v0"
RESULT_SCHEMA_VERSION = "sfa_bench.frontier_delta.result.v0"
REPORT_SCHEMA_VERSION = "sfa_bench.frontier_delta.report.v0"

# The eight behavioural lanes. Ordered; reports iterate lanes in this order.
LANES: tuple[str, ...] = (
    "long_horizon_planning_drift",
    "memory_state_boundary",
    "tool_use_false_completion",
    "grounding_integrity",
    "contradiction_recovery",
    "open_ended_adaptation",
    "paradigm_shift_recognition",
    "audit_replayability",
)

# One canonical fixed task per lane (the frozen v0 suite).
LANE_TASK_IDS: dict[str, str] = {
    "long_horizon_planning_drift": "planning_drift_001",
    "memory_state_boundary": "memory_boundary_001",
    "tool_use_false_completion": "tool_false_completion_001",
    "grounding_integrity": "grounding_integrity_001",
    "contradiction_recovery": "contradiction_recovery_001",
    "open_ended_adaptation": "open_ended_adaptation_001",
    "paradigm_shift_recognition": "paradigm_shift_001",
    "audit_replayability": "audit_replayability_001",
}

# Lanes whose real-world scoring needs human rubric judgment. The suite still
# computes a deterministic proxy over explicit fixture fields for CI, but marks
# the result rubric_assisted and explains the limitation.
RUBRIC_ASSISTED_LANES: frozenset[str] = frozenset(
    {"open_ended_adaptation", "paradigm_shift_recognition"}
)

REQUIRED_TASK_FIELDS: tuple[str, ...] = (
    "task_id",
    "suite_version",
    "lane",
    "objective",
    "prompt",
    "hard_constraints",
    "provided_state",
    "scoring_rubric",
    "expected_artifacts",
    "replay_requirements",
)

# Present where a task deliberately seeds failure opportunities.
OPTIONAL_TASK_FIELDS: tuple[str, ...] = ("hidden_expected_failures",)

_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "task_id": str,
    "suite_version": str,
    "lane": str,
    "objective": str,
    "prompt": str,
    "hard_constraints": list,
    "provided_state": dict,
    "scoring_rubric": dict,
    "expected_artifacts": list,
    "replay_requirements": dict,
    "hidden_expected_failures": list,
}


def get_path(obj: Any, path: str) -> tuple[bool, Any]:
    """Resolve a dotted path in a nested mapping. Returns (found, value)."""
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def task_hash(task: dict[str, Any]) -> str:
    """Canonical content hash of a task (excluding any embedded ``task_hash``)."""
    return sha256_hex({k: v for k, v in task.items() if k != "task_hash"})


def validate_task(task: dict[str, Any]) -> list[str]:
    """Return a deterministic list of schema issues (empty == valid)."""
    issues: list[str] = []
    if not isinstance(task, dict):
        return ["task is not a JSON object"]

    for field in REQUIRED_TASK_FIELDS:
        if field not in task:
            issues.append(f"missing required field: {field}")

    for field, expected in _FIELD_TYPES.items():
        if field in task and not isinstance(task[field], expected):
            name = expected.__name__ if isinstance(expected, type) else "/".join(t.__name__ for t in expected)
            issues.append(f"field {field!r} must be {name}")

    if task.get("suite_version") not in (None, SUITE_VERSION):
        issues.append(
            f"suite_version {task.get('suite_version')!r} != {SUITE_VERSION!r}"
        )

    lane = task.get("lane")
    if lane is not None and lane not in LANES:
        issues.append(f"unknown lane: {lane!r}")

    rubric = task.get("scoring_rubric")
    if isinstance(rubric, dict):
        checks = rubric.get("checks")
        if not isinstance(checks, list) or not checks:
            issues.append("scoring_rubric.checks must be a non-empty list")
        else:
            for index, check in enumerate(checks):
                if not isinstance(check, dict):
                    issues.append(f"scoring_rubric.checks[{index}] is not an object")
                    continue
                for key in ("id", "type", "failure_mode"):
                    if key not in check:
                        issues.append(f"scoring_rubric.checks[{index}] missing {key!r}")
        mode = rubric.get("scoring_mode")
        if mode not in ("deterministic", "rubric_assisted"):
            issues.append("scoring_rubric.scoring_mode must be deterministic|rubric_assisted")

    replay = task.get("replay_requirements")
    if isinstance(replay, dict) and "deterministic" not in replay:
        issues.append("replay_requirements must declare a 'deterministic' flag")

    return issues


def assert_valid_task(task: dict[str, Any]) -> None:
    issues = validate_task(task)
    if issues:
        raise ValueError(
            f"invalid task {task.get('task_id', '?')!r}:\n  - " + "\n  - ".join(issues)
        )
