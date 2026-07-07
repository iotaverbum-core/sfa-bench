"""Human ratification gate for AutoLab promotion (Item 4).

FROZEN ZONE - this module is promotion policy and is listed in
``autolab/frozen_manifest.json``. The AutoLab loop may not patch it; changes flow
only through the human-only amendment channel.

Item 2's gate may only reject. Item 4 is the separate, explicit promotion layer:
even when the deterministic gate is green, a candidate is not promoted unless a
human-supplied token matches a sealed ratification record that binds the exact
declaration, report, and gate-decision hash.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from autolab import controller
from autolab import preregistration

RATIFICATION_SCHEMA = "sfa.autolab.human_ratification.v0"
PROMOTION_SCHEMA = "sfa.autolab.promotion_decision.v0"
RATIFICATION_HASH_KEY = "ratification_hash"
HUMAN_RATIFICATION_TOKEN_ENV = "SFA_AUTOLAB_RATIFICATION_TOKEN"

DECISIONS = ("approve", "reject")


class RatificationError(ValueError):
    """Raised for malformed or tampered ratification records."""


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _hash_excluding(obj: dict[str, Any], key: str) -> str:
    return sha256_hex({k: v for k, v in obj.items() if k != key})


def gate_decision_hash(decision: preregistration.GateDecision | dict[str, Any]) -> str:
    payload = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    return sha256_hex(payload)


def resolve_ratification_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    token = os.environ.get(HUMAN_RATIFICATION_TOKEN_ENV)
    return token or None


def build_ratification(
    *,
    ratification_id: str,
    declaration_hash: str,
    report_hash: str,
    gate_decision_hash: str,
    target_ref: dict[str, Any],
    human_reviewer: str,
    rationale: str,
    decision: str = "approve",
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise RatificationError(f"decision must be one of {DECISIONS}")
    if not isinstance(target_ref, dict) or not target_ref:
        raise RatificationError("target_ref must be a non-empty object")
    return {
        "schema": RATIFICATION_SCHEMA,
        "ratification_id": str(ratification_id),
        "decision": decision,
        "declaration_hash": str(declaration_hash),
        "report_hash": str(report_hash),
        "gate_decision_hash": str(gate_decision_hash),
        "target_ref": dict(target_ref),
        "human_reviewer": str(human_reviewer),
        "rationale": str(rationale),
    }


def validate_ratification(record: dict[str, Any]) -> None:
    if record.get("schema") != RATIFICATION_SCHEMA:
        raise RatificationError(f"ratification schema must be {RATIFICATION_SCHEMA}")
    if record.get("decision") not in DECISIONS:
        raise RatificationError(f"ratification decision must be one of {DECISIONS}")
    for key in (
        "ratification_id",
        "declaration_hash",
        "report_hash",
        "gate_decision_hash",
        "target_ref",
        "human_reviewer",
        "rationale",
    ):
        if key not in record:
            raise RatificationError(f"ratification.{key} missing")
    if not isinstance(record.get("target_ref"), dict) or not record["target_ref"]:
        raise RatificationError("ratification.target_ref must be a non-empty object")


def seal_ratification(record: dict[str, Any]) -> dict[str, Any]:
    validate_ratification(record)
    sealed = {k: v for k, v in record.items() if k != RATIFICATION_HASH_KEY}
    sealed[RATIFICATION_HASH_KEY] = _hash_excluding(sealed, RATIFICATION_HASH_KEY)
    return sealed


def require_sealed_ratification(record: dict[str, Any]) -> None:
    validate_ratification(record)
    recorded = record.get(RATIFICATION_HASH_KEY)
    if not recorded:
        raise RatificationError("ratification is not sealed (no ratification_hash)")
    if _hash_excluding(record, RATIFICATION_HASH_KEY) != recorded:
        raise RatificationError("ratification_hash does not match ratification content")


@dataclass
class PromotionDecision:
    promoted: bool
    reasons: list[str]
    declaration_hash: str
    report_hash: Optional[str]
    gate_decision_hash: str
    ratification_hash: Optional[str]
    target_ref: Optional[dict[str, Any]]
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROMOTION_SCHEMA,
            "promoted": self.promoted,
            "reasons": list(self.reasons),
            "declaration_hash": self.declaration_hash,
            "report_hash": self.report_hash,
            "gate_decision_hash": self.gate_decision_hash,
            "ratification_hash": self.ratification_hash,
            "target_ref": dict(self.target_ref) if self.target_ref is not None else None,
            "checks": self.checks,
        }


def evaluate_promotion(
    declaration: dict[str, Any],
    report: dict[str, Any],
    ratification: dict[str, Any],
    *,
    ratification_token: Optional[str] = None,
) -> PromotionDecision:
    """Evaluate whether a candidate may be promoted.

    Promotion requires both a green deterministic gate and a human token matching
    the sealed ratification record. The builder's report rationale and any
    self-reported booleans are irrelevant because the gate decision is recomputed
    here from raw report numbers.
    """
    require_sealed_ratification(ratification)

    token = resolve_ratification_token(ratification_token)
    gate = preregistration.evaluate_gate(declaration, report)
    gate_hash = gate_decision_hash(gate)
    report_hash = gate.report_hash

    reasons: list[str] = []
    checks: dict[str, Any] = {}

    gate_ok = gate.gate_green
    checks["gate_green"] = gate_ok
    if not gate_ok:
        reasons.append(f"deterministic gate is red: {gate.reasons}")

    token_ok = bool(token) and token == ratification.get("ratification_id")
    checks["human_token"] = token_ok
    if not token:
        reasons.append(f"human ratification token missing ({HUMAN_RATIFICATION_TOKEN_ENV})")
    elif not token_ok:
        reasons.append("human ratification token does not match ratification_id")

    approved = ratification.get("decision") == "approve"
    checks["human_decision_approve"] = approved
    if not approved:
        reasons.append(f"human decision is {ratification.get('decision')!r}, not 'approve'")

    declaration_ok = ratification.get("declaration_hash") == gate.declaration_hash
    checks["declaration_binding"] = declaration_ok
    if not declaration_ok:
        reasons.append("ratification declaration_hash does not match the gated declaration")

    report_ok = bool(report_hash) and ratification.get("report_hash") == report_hash
    checks["report_binding"] = report_ok
    if not report_hash:
        reasons.append("report is not sealed (no report_hash)")
    elif not report_ok:
        reasons.append("ratification report_hash does not match the gated report")

    gate_hash_ok = ratification.get("gate_decision_hash") == gate_hash
    checks["gate_decision_binding"] = gate_hash_ok
    if not gate_hash_ok:
        reasons.append("ratification gate_decision_hash does not match recomputed gate")

    return PromotionDecision(
        promoted=not reasons,
        reasons=reasons,
        declaration_hash=gate.declaration_hash,
        report_hash=report_hash,
        gate_decision_hash=gate_hash,
        ratification_hash=ratification.get(RATIFICATION_HASH_KEY),
        target_ref=ratification.get("target_ref"),
        checks=checks,
    )


def append_promotion(
    ledger_path: str | Path,
    *,
    run_id: str,
    declaration: dict[str, Any],
    report: dict[str, Any],
    ratification: dict[str, Any],
    ratification_token: Optional[str] = None,
) -> dict[str, Any]:
    """Append a human-ratified promotion event to the AutoLab meta-ledger."""
    decision = evaluate_promotion(
        declaration,
        report,
        ratification,
        ratification_token=ratification_token,
    )
    if not decision.promoted:
        raise RatificationError(f"promotion rejected: {decision.reasons}")
    return controller.append_meta_event(
        ledger_path,
        event_type="human_ratification",
        run_id=run_id,
        payload={
            "promotion": decision.to_dict(),
            "ratification": dict(ratification),
        },
    )
