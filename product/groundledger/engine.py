"""GroundLedger verification engine.

One submission (an assistant answer + the evidence it was supposed to use + a
rule pack) goes in; one sealed, content-addressed *receipt* comes out. The
receipt records the deterministic groundedness verdict and the hashes of every
input, so it can be independently replayed later.

The judgment itself is delegated unchanged to ``sfa.verifier.verify``. The
verifier never sees an answer key, history, or model metadata - that structural
blindness is what makes the receipt defensible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sfa import families, verifier
from sfa.hashing import sha256_hex

RECEIPT_SCHEMA = "groundledger.receipt.v1"


class SubmissionError(ValueError):
    """Raised when a submission is missing required structure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require(submission: dict[str, Any], field: str) -> Any:
    if field not in submission:
        raise SubmissionError(f"submission missing required field {field!r}")
    return submission[field]


def verify_submission(
    submission: dict[str, Any],
    rule_pack: dict[str, Any],
    *,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Run the deterministic verifier and return a sealed receipt."""
    answer_id = _require(submission, "answer_id")
    candidate = _require(submission, "candidate")
    evidence = _require(submission, "evidence")
    task = submission.get("task_input", {})
    rules = {
        "verifier_version": rule_pack.get("verifier_version", verifier.VERIFIER_VERSION),
        "rules": rule_pack["rules"],
    }

    verdict = verifier.verify(task, evidence, candidate, rules)
    family = None
    if verdict.status == "FAIL":
        family = families.classify_family(verdict.category, candidate, evidence)

    clock = now or _utc_now
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "answer_id": str(answer_id),
        "rule_pack_id": rule_pack["rule_pack_id"],
        "rule_pack_version": rule_pack["version"],
        "verifier_version": rules["verifier_version"],
        "status": verdict.status,
        "category": verdict.category,
        "family": family,
        "explanation": verdict.explanation,
        "violations": [v.to_dict() for v in verdict.violations],
        "input_hash": sha256_hex(task),
        "evidence_hash": sha256_hex(evidence),
        "candidate_hash": sha256_hex(candidate),
        "rules_hash": sha256_hex(rules),
        "verdict_hash": sha256_hex(verdict.to_dict()),
        "sealed_at": clock(),
    }
    receipt["receipt_hash"] = seal_hash(receipt)
    return receipt


def seal_hash(receipt: dict[str, Any]) -> str:
    """Content-address a receipt over everything except its own seal."""
    return sha256_hex({k: v for k, v in receipt.items() if k != "receipt_hash"})


def is_grounded(receipt: dict[str, Any]) -> bool:
    return receipt.get("status") == "PASS"
