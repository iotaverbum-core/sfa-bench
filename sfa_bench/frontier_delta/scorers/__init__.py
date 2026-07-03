"""Frontier Delta scorers.

A scorer consumes a task and a model-output object and returns a structured,
deterministic JSON result. Scoring is data-driven: a task's
``scoring_rubric.checks`` list is evaluated by the deterministic check engine
(:mod:`sfa_bench.frontier_delta.scorers.checks`), and the result is assembled the
same way for every lane. This keeps scoring uniform, auditable, and replayable.

Each result reports:
  * ``score``                  - float in [0, 1] (fraction of checks passed).
  * ``verdict``                - ``pass`` | ``fail`` | ``partial``.
  * ``detected_failure_modes`` - failure-mode labels for failed checks.
  * ``evidence_snippets``      - short human-readable evidence per check.
  * ``explanation``            - one-line summary.
  * ``replay_possible``        - whether the result can be re-derived deterministically.
  * ``scoring_mode``           - ``deterministic`` | ``rubric_assisted`` (with a note).

Verdict policy: ``pass`` if every check passes; ``fail`` if any check marked
``critical`` fails; otherwise ``partial``.
"""
from __future__ import annotations

from typing import Any

from sfa.hashing import sha256_hex

from .. import schemas
from .checks import run_check

MISSING_OUTPUT_FAILURE = "no_model_output"


def _explain(task_id, verdict, score, failures, scoring_mode):
    if verdict == "pass":
        return f"{task_id}: PASS (all checks satisfied, score {score:.3f})"
    modes = ", ".join(failures) if failures else "none"
    tag = "" if scoring_mode == "deterministic" else " [rubric-assisted]"
    return f"{task_id}: {verdict.upper()} (score {score:.3f}; failure modes: {modes}){tag}"


def score_task(task: dict[str, Any], output: dict[str, Any] | None) -> dict[str, Any]:
    """Score one task against a model-output object (or ``None`` if absent)."""
    task_id = task.get("task_id", "?")
    lane = task.get("lane", "?")
    rubric = task.get("scoring_rubric", {})
    declared_mode = rubric.get("scoring_mode", "deterministic")
    # A lane may be inherently rubric-assisted even if its proxy checks are exact.
    scoring_mode = "rubric_assisted" if lane in schemas.RUBRIC_ASSISTED_LANES else declared_mode
    replay_possible = bool(task.get("replay_requirements", {}).get("deterministic", False))

    if output is None:
        result = {
            "schema": schemas.RESULT_SCHEMA_VERSION,
            "task_id": task_id,
            "lane": lane,
            "scoring_mode": scoring_mode,
            "score": 0.0,
            "verdict": "fail",
            "detected_failure_modes": [MISSING_OUTPUT_FAILURE],
            "evidence_snippets": ["no model output was provided for this task"],
            "explanation": f"{task_id}: FAIL (no model output)",
            "replay_possible": replay_possible,
            "checks": [],
        }
        result["result_hash"] = sha256_hex({k: v for k, v in result.items() if k != "result_hash"})
        return result

    checks = rubric.get("checks", [])
    check_results = []
    failures: list[str] = []
    evidence: list[str] = []
    critical_failed = False

    for check in checks:
        passed, snippet = run_check(check, output, task)
        check_results.append({
            "id": check.get("id"),
            "type": check.get("type"),
            "critical": bool(check.get("critical", False)),
            "passed": passed,
            "evidence": snippet,
        })
        evidence.append(f"[{check.get('id')}] {'ok' if passed else 'FAIL'}: {snippet}")
        if not passed:
            failures.append(check.get("failure_mode", "unspecified_failure"))
            if check.get("critical", False):
                critical_failed = True

    total = len(check_results)
    passed_count = sum(1 for c in check_results if c["passed"])
    score = round(passed_count / total, 6) if total else 0.0

    if passed_count == total and total:
        verdict = "pass"
    elif critical_failed:
        verdict = "fail"
    else:
        verdict = "partial"

    # De-duplicate failure modes while preserving order.
    seen: set[str] = set()
    deduped = [m for m in failures if not (m in seen or seen.add(m))]

    result = {
        "schema": schemas.RESULT_SCHEMA_VERSION,
        "task_id": task_id,
        "lane": lane,
        "scoring_mode": scoring_mode,
        "score": score,
        "verdict": verdict,
        "detected_failure_modes": deduped,
        "evidence_snippets": evidence,
        "explanation": _explain(task_id, verdict, score, deduped, scoring_mode),
        "replay_possible": replay_possible,
        "checks": check_results,
    }
    if scoring_mode == "rubric_assisted":
        result["rubric_note"] = (
            "This lane's real-world judgment needs human rubric assessment; the score "
            "here is a deterministic proxy over explicit fixture fields, provided so CI "
            "can run without live models. Treat it as directional, not final."
        )
    result["result_hash"] = sha256_hex({k: v for k, v in result.items() if k != "result_hash"})
    return result
