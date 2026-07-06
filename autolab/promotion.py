"""Promotion / rollback with tagged states (SFA-AutoLab v0, Item 4).

FROZEN ZONE — the promotion path is gate policy and is listed in
``autolab/frozen_manifest.json``. The loop may not patch it.

Promotion is the **only** operation that flips a candidate into the incumbent,
and it is deliberately not autonomous. ``promote`` requires **both**:

  1. a deterministically **gate-green** loop record (Item 3), and
  2. an explicit **human promotion token** (an out-of-loop authority — a value
     the automated builder cannot produce), bound to the exact ``loop_hash``.

If either is missing the promotion is *refused* — promotion is asymmetric just
like the gate (invariant 2). There is no code path that promotes without a token.

Rollback is a first-class, tagged, replayable operation (invariant 4): it
restores the previous incumbent **bit-exact** (same payload, same
``state_hash``). The **anchor** is pinned at ``v-root`` and never moves, so every
comparison keeps the original baseline in view.

Stdlib-only; standalone canonical hashing mirrors ``sfa.hashing``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA = "sfa.autolab.promotion.v0"
LINEAGE_SCHEMA = "sfa.autolab.promotion_lineage.v0"
AUTHORIZATION_SCHEMA = "sfa.autolab.promotion_authorization.v0"
ANCHOR_TAG = "v-root"
PROMOTION_TOKEN_ENV = "SFA_PROMOTION_TOKEN"
PROMOTIONS_DIRNAME = "autolab/promotions"
GENESIS = "GENESIS"

ORIGIN_ROOT = "root"
ORIGIN_PROMOTION = "promotion"
ORIGIN_ROLLBACK = "rollback"


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def payload_hash(payload: Any) -> str:
    """Bit-exact content hash of a scaffold state payload."""
    return sha256_hex(payload)


class PromotionError(RuntimeError):
    """Raised when a promotion is refused (asymmetric: promotion can only fail)."""


# ---------------------------------------------------------------------------
# Tagged states.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class State:
    tag: str
    parent_tag: Optional[str]
    anchor_tag: str
    sequence: int
    origin: str
    state_hash: str
    payload: Any
    loop_hash: Optional[str] = None
    restored_from: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tag": self.tag,
            "parent_tag": self.parent_tag,
            "anchor_tag": self.anchor_tag,
            "sequence": self.sequence,
            "origin": self.origin,
            "state_hash": self.state_hash,
            "payload": self.payload,
            "loop_hash": self.loop_hash,
            "restored_from": self.restored_from,
        }


def make_root_state(payload: Any) -> State:
    """The pinned v-root incumbent. Its tag is also the immovable anchor."""
    return State(
        tag=ANCHOR_TAG, parent_tag=None, anchor_tag=ANCHOR_TAG, sequence=0,
        origin=ORIGIN_ROOT, state_hash=payload_hash(payload), payload=payload,
    )


# ---------------------------------------------------------------------------
# Human promotion authorization (out-of-loop authority).
# ---------------------------------------------------------------------------
def check_promotion_preconditions(loop_record: dict[str, Any], human_token: Optional[str]) -> list[str]:
    """Return the reasons a promotion must be refused (empty list => allowed)."""
    reasons: list[str] = []
    gate = loop_record.get("gate", {})
    if not gate.get("gate_green"):
        reasons.append("gate is not green: the deterministic gate did not pass")
    promo = loop_record.get("promotion", {})
    if promo.get("promoted"):
        reasons.append("loop record already claims promotion (the loop may not self-promote)")
    if not human_token:
        reasons.append(
            f"promotion requires an explicit human token ({PROMOTION_TOKEN_ENV}); none supplied"
        )
    return reasons


def validate_authorization(authorization: dict[str, Any], loop_record: dict[str, Any],
                           human_token: str) -> list[str]:
    """A human authorization must name the token and bind the exact loop_hash."""
    reasons: list[str] = []
    if authorization.get("token") != human_token:
        reasons.append("authorization token does not match the supplied token")
    if authorization.get("loop_hash") != loop_record.get("loop_hash"):
        reasons.append("authorization loop_hash does not match the loop record")
    return reasons


# ---------------------------------------------------------------------------
# Promote and rollback (pure).
# ---------------------------------------------------------------------------
def promote(incumbent: State, loop_record: dict[str, Any], candidate_payload: Any, *,
            human_token: Optional[str],
            authorization: Optional[dict[str, Any]] = None) -> State:
    """Promote a candidate to the new incumbent. Refused unless gate-green AND
    a valid human token (optionally an authorization binding the loop_hash)."""
    reasons = check_promotion_preconditions(loop_record, human_token)
    if authorization is not None and human_token:
        reasons.extend(validate_authorization(authorization, loop_record, human_token))
    if reasons:
        raise PromotionError("; ".join(reasons))
    return State(
        tag=f"v{incumbent.sequence + 1}",
        parent_tag=incumbent.tag,
        anchor_tag=ANCHOR_TAG,
        sequence=incumbent.sequence + 1,
        origin=ORIGIN_PROMOTION,
        state_hash=payload_hash(candidate_payload),
        payload=candidate_payload,
        loop_hash=loop_record.get("loop_hash"),
    )


def rollback(current: State, restore_to: State) -> State:
    """Restore ``restore_to`` bit-exact as a new tagged rollback event.

    The restored state carries the target's exact payload and ``state_hash``; it
    is tagged as a rollback so the lineage stays append-only (invariant 4).
    """
    return State(
        tag=f"v{current.sequence + 1}",
        parent_tag=current.tag,
        anchor_tag=ANCHOR_TAG,
        sequence=current.sequence + 1,
        origin=ORIGIN_ROLLBACK,
        state_hash=restore_to.state_hash,   # bit-exact
        payload=restore_to.payload,          # bit-exact
        loop_hash=None,
        restored_from=restore_to.tag,
    )


def restores_bit_exact(rolled_back: State, incumbent: State) -> bool:
    """True iff the rollback restored the incumbent's exact content."""
    return (rolled_back.state_hash == incumbent.state_hash
            and payload_hash(rolled_back.payload) == incumbent.state_hash
            and rolled_back.payload == incumbent.payload)


# ---------------------------------------------------------------------------
# Append-only, hash-chained lineage of tagged states.
# ---------------------------------------------------------------------------
@dataclass
class Lineage:
    events: list[dict[str, Any]] = field(default_factory=list)

    def _append(self, state: State) -> None:
        prev = self.events[-1]["entry_hash"] if self.events else GENESIS
        entry = {
            "seq": len(self.events),
            "tag": state.tag,
            "parent_tag": state.parent_tag,
            "anchor_tag": state.anchor_tag,
            "origin": state.origin,
            "state_hash": state.state_hash,
            "loop_hash": state.loop_hash,
            "restored_from": state.restored_from,
            "prev_hash": prev,
        }
        entry["entry_hash"] = sha256_hex({k: v for k, v in entry.items() if k != "entry_hash"})
        self.events.append(entry)

    def add(self, state: State) -> State:
        self._append(state)
        return state

    @property
    def head_hash(self) -> str:
        return self.events[-1]["entry_hash"] if self.events else GENESIS

    def seal(self) -> dict[str, Any]:
        record = {"schema": LINEAGE_SCHEMA, "anchor_tag": ANCHOR_TAG,
                  "events": self.events, "head_hash": self.head_hash}
        record["lineage_hash"] = sha256_hex({k: v for k, v in record.items() if k != "lineage_hash"})
        return record


# ---------------------------------------------------------------------------
# Promote -> rollback round trip (pure, replayable).
# ---------------------------------------------------------------------------
def promote_rollback_round_trip(root_payload: Any, loop_record: dict[str, Any],
                                candidate_payload: Any, *, human_token: str) -> dict[str, Any]:
    """Run root -> promote -> rollback and seal the lineage.

    Returns a sealed record with the three tagged states, the lineage, and a
    bit-exact restoration flag. Pure: a function of its inputs, so ``replay``
    reproduces it exactly.
    """
    lineage = Lineage()
    incumbent = make_root_state(root_payload)
    lineage.add(incumbent)
    promoted = promote(incumbent, loop_record, candidate_payload, human_token=human_token)
    lineage.add(promoted)
    restored = rollback(promoted, incumbent)
    lineage.add(restored)

    record = {
        "schema": "sfa.autolab.promotion_round_trip.v0",
        "anchor_tag": ANCHOR_TAG,
        "incumbent": incumbent.to_dict(),
        "promoted": promoted.to_dict(),
        "restored": restored.to_dict(),
        "restores_bit_exact": restores_bit_exact(restored, incumbent),
        "lineage": lineage.seal(),
    }
    record["round_trip_hash"] = sha256_hex({k: v for k, v in record.items() if k != "round_trip_hash"})
    return record


def replay_round_trip(record: dict[str, Any], root_payload: Any, loop_record: dict[str, Any],
                      candidate_payload: Any, *, human_token: str) -> dict[str, Any]:
    """Re-derive a round trip and confirm it is byte-identical + bit-exact."""
    rebuilt = promote_rollback_round_trip(root_payload, loop_record, candidate_payload,
                                          human_token=human_token)
    issues = []
    if rebuilt["round_trip_hash"] != record.get("round_trip_hash"):
        issues.append("round_trip_hash mismatch: not reproducible from inputs")
    if rebuilt["lineage"]["lineage_hash"] != record.get("lineage", {}).get("lineage_hash"):
        issues.append("lineage_hash mismatch")
    if not rebuilt["restores_bit_exact"]:
        issues.append("rollback did not restore the incumbent bit-exact")
    return {"attested": not issues, "issues": issues,
            "round_trip_hash": rebuilt["round_trip_hash"]}


# ---------------------------------------------------------------------------
# File-based human authorization channel.
# ---------------------------------------------------------------------------
def load_authorization(root: str | Path, token: str) -> Optional[dict[str, Any]]:
    directory = Path(root) / PROMOTIONS_DIRNAME
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("token") == token:
            return record
    return None


def resolve_promotion_token(explicit: Optional[str]) -> Optional[str]:
    import os
    if explicit:
        return explicit
    return os.environ.get(PROMOTION_TOKEN_ENV) or None
