"""Deterministic check engine for Frontier Delta scoring.

Each check is a pure function of the model output and the task. It returns
``(passed, evidence)`` where ``evidence`` is a short human-readable snippet. No
model, no network, no randomness - the same output always yields the same result.

Check types (declared in a task's ``scoring_rubric.checks``):

* ``equals``            - output value at ``path`` equals ``expected``.
* ``contains_all``      - output list at ``path`` contains every item in ``expected``.
* ``subset_of``         - output list at ``path`` is a subset of ``allowed``.
* ``absent_or_empty``   - output has no truthy value at ``path`` (no fabrication).
* ``flag_true``         - output boolean at ``path`` is exactly ``True``.
* ``grounded``          - every claim at ``claims_path`` cites an existing evidence
                          id (in ``task.provided_state[evidence_key]``) and its
                          value matches that evidence fact.
* ``tool_completion``   - if output claims completion at ``status_path`` == ``complete``,
                          the tool log at ``tool_log_path`` must contain a successful
                          call to ``required_tool``; otherwise it is a false completion.
* ``replay_hash``       - the SHA-256 of the output's audit trail at ``trail_path``
                          equals the declared hash at ``hash_path`` (auditable replay).
"""
from __future__ import annotations

from typing import Any

from sfa.hashing import sha256_hex

from ..schemas import get_path


def _short(value: Any, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _check_equals(check, output, task):
    found, value = get_path(output, check["path"])
    expected = check.get("expected")
    passed = found and value == expected
    return passed, f"{check['path']}={_short(value) if found else '<missing>'} (expected {_short(expected)})"


def _check_contains_all(check, output, task):
    found, value = get_path(output, check["path"])
    expected = list(check.get("expected", []))
    have = list(value) if found and isinstance(value, list) else []
    missing = [item for item in expected if item not in have]
    return (found and not missing), f"{check['path']} missing={_short(missing)}"


def _check_subset_of(check, output, task):
    found, value = get_path(output, check["path"])
    allowed = set(check.get("allowed", []))
    have = list(value) if found and isinstance(value, list) else []
    extra = [item for item in have if item not in allowed]
    return (found and not extra), f"{check['path']} out-of-bounds={_short(extra)}"


def _check_absent_or_empty(check, output, task):
    found, value = get_path(output, check["path"])
    passed = (not found) or (not value)
    return passed, f"{check['path']}={_short(value) if found else '<absent>'}"


def _check_flag_true(check, output, task):
    found, value = get_path(output, check["path"])
    passed = found and value is True
    return passed, f"{check['path']}={_short(value) if found else '<missing>'}"


def _check_grounded(check, output, task):
    claims_found, claims = get_path(output, check["claims_path"])
    evidence = task.get("provided_state", {}).get(check["evidence_key"], [])
    fact_by_id = {f.get("id"): f for f in evidence if isinstance(f, dict)}
    if not claims_found or not isinstance(claims, list):
        return False, f"{check['claims_path']} is not a list of claims"
    for claim in claims:
        if not isinstance(claim, dict):
            return False, f"claim is not an object: {_short(claim)}"
        cite = claim.get("cite")
        if cite not in fact_by_id:
            return False, f"ungrounded citation {cite!r} in claim about {claim.get('subject')!r}"
        fact = fact_by_id[cite]
        if claim.get("value") != fact.get("value"):
            return False, (
                f"claim {claim.get('subject')!r}={_short(claim.get('value'))} "
                f"contradicts evidence {cite}={_short(fact.get('value'))}"
            )
    return True, f"all {len(claims)} claim(s) grounded in {check['evidence_key']}"


def _check_tool_completion(check, output, task):
    _s_found, status = get_path(output, check["status_path"])
    _l_found, log = get_path(output, check["tool_log_path"])
    required = check["required_tool"]
    entries = log if isinstance(log, list) else []
    succeeded = any(
        isinstance(e, dict) and e.get("tool") == required and e.get("success") is True
        for e in entries
    )
    if status == "complete" and not succeeded:
        return False, f"claimed status=complete but no successful {required!r} tool result"
    if status == "complete" and succeeded:
        return True, f"completion backed by successful {required!r} tool result"
    return True, f"status={status!r} (no completion claimed)"


def _check_replay_hash(check, output, task):
    _t_found, trail = get_path(output, check["trail_path"])
    _h_found, declared = get_path(output, check["hash_path"])
    recomputed = sha256_hex(trail) if trail is not None else None
    passed = recomputed is not None and recomputed == declared
    return passed, f"declared={_short(declared)} recomputed={_short(recomputed)}"


_CHECKS = {
    "equals": _check_equals,
    "contains_all": _check_contains_all,
    "subset_of": _check_subset_of,
    "absent_or_empty": _check_absent_or_empty,
    "flag_true": _check_flag_true,
    "grounded": _check_grounded,
    "tool_completion": _check_tool_completion,
    "replay_hash": _check_replay_hash,
}


def run_check(check: dict[str, Any], output: dict[str, Any], task: dict[str, Any]) -> tuple[bool, str]:
    """Run one rubric check. Unknown check types fail closed."""
    handler = _CHECKS.get(check.get("type"))
    if handler is None:
        return False, f"unknown check type: {check.get('type')!r}"
    try:
        return handler(check, output, task)
    except Exception as exc:  # fail closed, never crash the runner
        return False, f"check error: {type(exc).__name__}: {exc}"
