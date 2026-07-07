"""Append-only promotion lineage and rollback guard for AutoLab (Item 5).

FROZEN ZONE - this module is promotion-history policy and is listed in
``autolab/frozen_manifest.json``. The AutoLab loop may not patch it; changes
flow only through the human-only amendment channel.

Item 4 decides whether a candidate may be promoted and appends a
``human_ratification`` event. Item 5 turns that ratification into explicit
deployment lineage: the promoted target is inscribed as the current target, and
any rollback is also a sealed, human-token-gated ledger event. Rollback never
rewrites or deletes history; it appends a new transition from the current target
to a restore ref.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from autolab import controller
from autolab import ratification

LINEAGE_STATE_SCHEMA = "sfa.autolab.lineage_state.v0"
PROMOTION_INSCRIPTION_SCHEMA = "sfa.autolab.promotion_inscription.v0"
ROLLBACK_SCHEMA = "sfa.autolab.rollback.v0"
ROLLBACK_HASH_KEY = "rollback_hash"
HUMAN_ROLLBACK_TOKEN_ENV = "SFA_AUTOLAB_ROLLBACK_TOKEN"


class LineageError(ValueError):
    """Raised when lineage or rollback records are malformed or unsafe."""


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _hash_excluding(obj: dict[str, Any], key: str) -> str:
    return sha256_hex({k: v for k, v in obj.items() if k != key})


def target_key(target_ref: dict[str, Any]) -> str:
    """Return a stable key for a target reference."""
    if not isinstance(target_ref, dict) or not target_ref:
        raise LineageError("target_ref must be a non-empty object")
    return sha256_hex(target_ref)


def _resolve_rollback_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    token = os.environ.get(HUMAN_ROLLBACK_TOKEN_ENV)
    return token or None


def _entry_hash(entry: dict[str, Any]) -> Optional[str]:
    value = entry.get(controller.ENTRY_HASH_KEY)
    return str(value) if value else None


def _require_clean_ledger(path: str | Path) -> list[dict[str, Any]]:
    ok, errors, _ = controller.verify_meta_ledger(path)
    if not ok:
        raise LineageError(f"meta-ledger is not append-only clean: {errors}")
    return controller.read_meta_ledger(path)


def _find_entry(entries: list[dict[str, Any]], entry_hash: str) -> dict[str, Any]:
    for entry in entries:
        if _entry_hash(entry) == entry_hash:
            return entry
    raise LineageError(f"meta-ledger entry not found: {entry_hash}")


def _promotion_entry_hash_is_inscribed(entries: list[dict[str, Any]], entry_hash: str) -> bool:
    for entry in entries:
        if entry.get("event_type") != "promotion_inscribed":
            continue
        payload = entry.get("payload")
        if isinstance(payload, dict) and payload.get("promotion_entry_hash") == entry_hash:
            return True
    return False


def _ratified_promotion_payload(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("event_type") != "human_ratification":
        raise LineageError("promotion inscription requires a human_ratification entry")
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        raise LineageError("human_ratification payload must be an object")
    promotion = payload.get("promotion")
    if not isinstance(promotion, dict):
        raise LineageError("human_ratification payload missing promotion object")
    if promotion.get("schema") != ratification.PROMOTION_SCHEMA:
        raise LineageError("promotion payload schema mismatch")
    if promotion.get("promoted") is not True:
        raise LineageError("only promoted human_ratification entries may be inscribed")
    target_ref = promotion.get("target_ref")
    if not isinstance(target_ref, dict) or not target_ref:
        raise LineageError("promotion payload missing target_ref")
    return payload


def build_promotion_inscription(
    *,
    promotion_entry_hash: str,
    target_ref: dict[str, Any],
    ratification_hash: str,
    previous_ref: Optional[dict[str, Any]] = None,
    human_reviewer: str = "",
    rationale: str = "",
) -> dict[str, Any]:
    previous_key = target_key(previous_ref) if previous_ref is not None else None
    return {
        "schema": PROMOTION_INSCRIPTION_SCHEMA,
        "promotion_entry_hash": str(promotion_entry_hash),
        "ratification_hash": str(ratification_hash),
        "target_ref": dict(target_ref),
        "target_key": target_key(target_ref),
        "previous_ref": dict(previous_ref) if previous_ref is not None else None,
        "previous_key": previous_key,
        "human_reviewer": str(human_reviewer),
        "rationale": str(rationale),
    }


def validate_promotion_inscription(record: dict[str, Any]) -> None:
    if record.get("schema") != PROMOTION_INSCRIPTION_SCHEMA:
        raise LineageError(f"promotion inscription schema must be {PROMOTION_INSCRIPTION_SCHEMA}")
    for key in ("promotion_entry_hash", "ratification_hash", "target_ref", "target_key"):
        if not record.get(key):
            raise LineageError(f"promotion inscription.{key} missing")
    if target_key(record["target_ref"]) != record.get("target_key"):
        raise LineageError("promotion inscription target_key does not match target_ref")
    previous_ref = record.get("previous_ref")
    previous_key = record.get("previous_key")
    if previous_ref is None:
        if previous_key is not None:
            raise LineageError("promotion inscription previous_key set without previous_ref")
    elif target_key(previous_ref) != previous_key:
        raise LineageError("promotion inscription previous_key does not match previous_ref")


def build_rollback(
    *,
    rollback_id: str,
    target_ref: dict[str, Any],
    restore_ref: dict[str, Any],
    human_reviewer: str,
    reason: str,
) -> dict[str, Any]:
    if target_key(target_ref) == target_key(restore_ref):
        raise LineageError("rollback target_ref and restore_ref must differ")
    return {
        "schema": ROLLBACK_SCHEMA,
        "rollback_id": str(rollback_id),
        "target_ref": dict(target_ref),
        "target_key": target_key(target_ref),
        "restore_ref": dict(restore_ref),
        "restore_key": target_key(restore_ref),
        "human_reviewer": str(human_reviewer),
        "reason": str(reason),
    }


def validate_rollback(record: dict[str, Any]) -> None:
    if record.get("schema") != ROLLBACK_SCHEMA:
        raise LineageError(f"rollback schema must be {ROLLBACK_SCHEMA}")
    for key in (
        "rollback_id",
        "target_ref",
        "target_key",
        "restore_ref",
        "restore_key",
        "human_reviewer",
        "reason",
    ):
        if not record.get(key):
            raise LineageError(f"rollback.{key} missing")
    if target_key(record["target_ref"]) != record.get("target_key"):
        raise LineageError("rollback target_key does not match target_ref")
    if target_key(record["restore_ref"]) != record.get("restore_key"):
        raise LineageError("rollback restore_key does not match restore_ref")
    if record.get("target_key") == record.get("restore_key"):
        raise LineageError("rollback target_ref and restore_ref must differ")


def seal_rollback(record: dict[str, Any]) -> dict[str, Any]:
    validate_rollback(record)
    sealed = {k: v for k, v in record.items() if k != ROLLBACK_HASH_KEY}
    sealed[ROLLBACK_HASH_KEY] = _hash_excluding(sealed, ROLLBACK_HASH_KEY)
    return sealed


def require_sealed_rollback(record: dict[str, Any]) -> None:
    validate_rollback(record)
    recorded = record.get(ROLLBACK_HASH_KEY)
    if not recorded:
        raise LineageError("rollback is not sealed (no rollback_hash)")
    if _hash_excluding(record, ROLLBACK_HASH_KEY) != recorded:
        raise LineageError("rollback_hash does not match rollback content")


@dataclass
class LineageState:
    current_ref: Optional[dict[str, Any]]
    current_key: Optional[str]
    promotions: list[dict[str, Any]] = field(default_factory=list)
    rollbacks: list[dict[str, Any]] = field(default_factory=list)
    ledger_root: str = controller.GENESIS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LINEAGE_STATE_SCHEMA,
            "current_ref": dict(self.current_ref) if self.current_ref is not None else None,
            "current_key": self.current_key,
            "promotions": list(self.promotions),
            "rollbacks": list(self.rollbacks),
            "ledger_root": self.ledger_root,
        }


def derive_lineage_state(ledger_path: str | Path) -> LineageState:
    """Derive the current promoted target from append-only lineage events."""
    entries = _require_clean_ledger(ledger_path)
    current_ref: Optional[dict[str, Any]] = None
    current_key: Optional[str] = None
    promotions: list[dict[str, Any]] = []
    rollbacks: list[dict[str, Any]] = []

    for entry in entries:
        event_type = entry.get("event_type")
        payload = entry.get("payload", {})
        if not isinstance(payload, dict):
            raise LineageError("meta-ledger event payload must be an object")

        if event_type == "promotion_inscribed":
            validate_promotion_inscription(payload)
            expected_previous = payload.get("previous_key")
            if current_key is not None and expected_previous != current_key:
                raise LineageError(
                    "promotion inscription previous_key does not match current lineage target"
                )
            current_ref = dict(payload["target_ref"])
            current_key = str(payload["target_key"])
            promotions.append({
                "entry_hash": _entry_hash(entry),
                "seq": entry.get("seq"),
                "promotion_entry_hash": payload["promotion_entry_hash"],
                "target_key": current_key,
                "target_ref": dict(current_ref),
            })

        elif event_type == "rollback_inscribed":
            rollback = payload.get("rollback")
            if not isinstance(rollback, dict):
                raise LineageError("rollback_inscribed payload missing rollback object")
            require_sealed_rollback(rollback)
            if current_key is None:
                raise LineageError("rollback has no current promoted target")
            if rollback["target_key"] != current_key:
                raise LineageError("rollback target_ref is not the current lineage target")
            current_ref = dict(rollback["restore_ref"])
            current_key = str(rollback["restore_key"])
            rollbacks.append({
                "entry_hash": _entry_hash(entry),
                "seq": entry.get("seq"),
                "rollback_id": rollback["rollback_id"],
                "target_key": rollback["target_key"],
                "restore_key": rollback["restore_key"],
            })

    return LineageState(
        current_ref=current_ref,
        current_key=current_key,
        promotions=promotions,
        rollbacks=rollbacks,
        ledger_root=controller.meta_ledger_root(ledger_path),
    )


def append_promotion_inscription(
    ledger_path: str | Path,
    *,
    run_id: str,
    promotion_entry_hash: str,
    previous_ref: Optional[dict[str, Any]] = None,
    rationale: str = "",
) -> dict[str, Any]:
    """Append a promotion inscription for an existing human ratification event."""
    entries = _require_clean_ledger(ledger_path)
    state = derive_lineage_state(ledger_path)
    promotion_entry = _find_entry(entries, str(promotion_entry_hash))
    ratified = _ratified_promotion_payload(promotion_entry)
    promotion = ratified["promotion"]
    rat_record = ratified.get("ratification", {})
    target_ref = dict(promotion["target_ref"])
    target = target_key(target_ref)

    if state.current_key == target:
        raise LineageError("target_ref is already current in lineage")
    if _promotion_entry_hash_is_inscribed(entries, str(promotion_entry_hash)):
        raise LineageError("promotion_entry_hash is already inscribed")
    if previous_ref is None:
        previous_ref = state.current_ref
    elif state.current_key is not None and target_key(previous_ref) != state.current_key:
        raise LineageError("previous_ref does not match current lineage target")

    inscription = build_promotion_inscription(
        promotion_entry_hash=str(promotion_entry_hash),
        ratification_hash=str(promotion.get("ratification_hash") or ""),
        target_ref=target_ref,
        previous_ref=previous_ref,
        human_reviewer=str(rat_record.get("human_reviewer", "")),
        rationale=rationale,
    )
    validate_promotion_inscription(inscription)
    return controller.append_meta_event(
        ledger_path,
        event_type="promotion_inscribed",
        run_id=run_id,
        payload=inscription,
    )


def append_rollback(
    ledger_path: str | Path,
    *,
    run_id: str,
    rollback: dict[str, Any],
    rollback_token: Optional[str] = None,
) -> dict[str, Any]:
    """Append a sealed human rollback event to the AutoLab meta-ledger."""
    require_sealed_rollback(rollback)
    token = _resolve_rollback_token(rollback_token)
    if not token:
        raise LineageError(f"human rollback token missing ({HUMAN_ROLLBACK_TOKEN_ENV})")
    if token != rollback.get("rollback_id"):
        raise LineageError("human rollback token does not match rollback_id")

    state = derive_lineage_state(ledger_path)
    if state.current_key is None:
        raise LineageError("rollback requires an active lineage target")
    if rollback["target_key"] != state.current_key:
        raise LineageError("rollback target_ref is not the current lineage target")

    return controller.append_meta_event(
        ledger_path,
        event_type="rollback_inscribed",
        run_id=run_id,
        payload={
            "rollback": dict(rollback),
            "previous_current_key": state.current_key,
            "next_current_key": rollback["restore_key"],
        },
    )
