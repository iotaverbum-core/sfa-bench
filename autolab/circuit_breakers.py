"""Circuit breakers and halt-and-hold restart guard for AutoLab (Item 6).

FROZEN ZONE - this module is loop safety policy and is listed in
``autolab/frozen_manifest.json``. The AutoLab loop may not patch it; changes
flow only through the human-only amendment channel.

Items 3-5 make the loop auditable: controlled iterations, human ratification,
and append-only promotion lineage. Item 6 defines the stop conditions around
that loop. A breaker report is a deterministic function of the frozen-zone
attestation, the controller meta-ledger, proposed paths, budget counters, and
lineage rejection history. When a report halts, restart is not automatic: a
sealed human restart clearance plus matching token must be appended.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from autolab import controller
from autolab import frozen_zone

BREAKER_REPORT_SCHEMA = "sfa.autolab.circuit_breaker_report.v0"
RESTART_CLEARANCE_SCHEMA = "sfa.autolab.restart_clearance.v0"
BREAKER_REPORT_HASH_KEY = "breaker_report_hash"
CLEARANCE_HASH_KEY = "clearance_hash"
HUMAN_RESTART_TOKEN_ENV = "SFA_AUTOLAB_RESTART_TOKEN"

EVENT_HALTED = "autolab_halted"
EVENT_RESTART_AUTHORIZED = "autolab_restart_authorized"

REJECTION_EVENTS = (
    "gate_rejected",
    "promotion_rejected",
    "human_ratification_rejected",
    "autolab_rejected",
)
RESET_REJECTION_EVENTS = (
    "human_ratification",
    "promotion_inscribed",
    "rollback_inscribed",
    EVENT_RESTART_AUTHORIZED,
)

REASON_ZONE_HASH_MISMATCH = "zone_hash_mismatch"
REASON_CHAIN_BREAK = "chain_break"
REASON_HOLDOUT_BUDGET_EXHAUSTED = "holdout_budget_exhausted"
REASON_CONSECUTIVE_REJECTIONS = "consecutive_rejections"
REASON_FROZEN_PATH_CHANGE_PROPOSED = "frozen_path_change_proposed"
REASON_COST_TIME_BUDGET_EXCEEDED = "cost_time_budget_exceeded"
REASON_LINEAGE_WITHERED = "lineage_withered"

DEFAULT_MAX_CONSECUTIVE_REJECTIONS = 3
DEFAULT_WITHER_THRESHOLD = 3


class CircuitBreakerError(ValueError):
    """Raised when a halt or restart operation is malformed or unsafe."""


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _hash_excluding(obj: dict[str, Any], key: str) -> str:
    return sha256_hex({k: v for k, v in obj.items() if k != key})


def _entry_hash(entry: dict[str, Any]) -> Optional[str]:
    value = entry.get(controller.ENTRY_HASH_KEY)
    return str(value) if value else None


def _clean_entries(ledger_path: str | Path) -> tuple[bool, list[str], list[dict[str, Any]]]:
    ok, errors, _ = controller.verify_meta_ledger(ledger_path)
    if not ok:
        return False, [f"{index}: {message}" for index, message in errors], []
    return True, [], controller.read_meta_ledger(ledger_path)


def _is_rejection(entry: dict[str, Any]) -> bool:
    if entry.get("event_type") in REJECTION_EVENTS:
        return True
    payload = entry.get("payload")
    return isinstance(payload, dict) and payload.get("gate_green") is False


def trailing_rejection_count(entries: list[dict[str, Any]]) -> int:
    count = 0
    for entry in reversed(entries):
        if _is_rejection(entry):
            count += 1
            continue
        if entry.get("event_type") in RESET_REJECTION_EVENTS:
            break
        if entry.get("event_type") not in (EVENT_HALTED,):
            break
    return count


def rejection_counts_by_lineage(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if not _is_rejection(entry):
            continue
        payload = entry.get("payload")
        lineage_id = None
        if isinstance(payload, dict):
            lineage_id = payload.get("lineage_id") or payload.get("patch_fingerprint")
        if not lineage_id:
            lineage_id = entry.get("run_id")
        key = str(lineage_id)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def is_withered(
    entries: list[dict[str, Any]],
    lineage_id: str,
    *,
    threshold: int = DEFAULT_WITHER_THRESHOLD,
) -> bool:
    return rejection_counts_by_lineage(entries).get(str(lineage_id), 0) >= int(threshold)


def caution_directives(
    entries: list[dict[str, Any]],
    *,
    threshold: int = DEFAULT_WITHER_THRESHOLD,
) -> list[dict[str, Any]]:
    directives: list[dict[str, Any]] = []
    for lineage_id, count in rejection_counts_by_lineage(entries).items():
        withered = count >= int(threshold)
        directives.append({
            "lineage_id": lineage_id,
            "rejections": count,
            "withered": withered,
            "directive": (
                "TERMINAL: do not re-propose this lineage"
                if withered else
                "CAUTION: prior rejection history is advisory and excluded from gate"
            ),
            "advisory": True,
            "excluded_from_gate": True,
        })
    return directives


def _holdout_exhausted(entries: list[dict[str, Any]]) -> bool:
    for entry in entries:
        if entry.get("event_type") != "holdout_budget_consumed":
            continue
        payload = entry.get("payload")
        if isinstance(payload, dict) and int(payload.get("remaining_after", 1)) <= 0:
            return True
    return False


def _current_halt_from_entries(entries: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    active: Optional[dict[str, Any]] = None
    for entry in entries:
        if entry.get("event_type") == EVENT_HALTED:
            active = entry
        elif entry.get("event_type") == EVENT_RESTART_AUTHORIZED:
            payload = entry.get("payload")
            clearance = payload.get("clearance") if isinstance(payload, dict) else None
            if isinstance(clearance, dict) and active is not None:
                if clearance.get("halt_entry_hash") == _entry_hash(active):
                    active = None
    return active


def current_halt(ledger_path: str | Path) -> Optional[dict[str, Any]]:
    ok, errors, entries = _clean_entries(ledger_path)
    if not ok:
        raise CircuitBreakerError(f"meta-ledger is not append-only clean: {errors}")
    return _current_halt_from_entries(entries)


@dataclass
class BreakerReport:
    halted: bool
    reasons: list[str]
    checks: dict[str, Any] = field(default_factory=dict)
    ledger_root: str = controller.GENESIS
    zone_hash: Optional[str] = None

    def _payload(self) -> dict[str, Any]:
        return {
            "schema": BREAKER_REPORT_SCHEMA,
            "halted": bool(self.halted),
            "reasons": list(self.reasons),
            "checks": dict(self.checks),
            "ledger_root": self.ledger_root,
            "zone_hash": self.zone_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload[BREAKER_REPORT_HASH_KEY] = sha256_hex(payload)
        return payload


def require_sealed_report(record: dict[str, Any]) -> None:
    if record.get("schema") != BREAKER_REPORT_SCHEMA:
        raise CircuitBreakerError(f"breaker report schema must be {BREAKER_REPORT_SCHEMA}")
    recorded = record.get(BREAKER_REPORT_HASH_KEY)
    if not recorded:
        raise CircuitBreakerError("breaker report is not sealed")
    if _hash_excluding(record, BREAKER_REPORT_HASH_KEY) != recorded:
        raise CircuitBreakerError("breaker_report_hash does not match report content")


def evaluate_breakers(
    *,
    repo_root: str | Path,
    ledger_path: str | Path,
    expected_zone_hash: Optional[str] = None,
    proposed_changed_paths: Optional[list[str]] = None,
    max_consecutive_rejections: int = DEFAULT_MAX_CONSECUTIVE_REJECTIONS,
    proposed_lineage_id: Optional[str] = None,
    wither_threshold: int = DEFAULT_WITHER_THRESHOLD,
    cost_spent: float = 0.0,
    max_cost: Optional[float] = None,
    seconds_spent: float = 0.0,
    max_seconds: Optional[float] = None,
) -> BreakerReport:
    """Evaluate deterministic halt conditions around the AutoLab loop."""
    reasons: list[str] = []
    checks: dict[str, Any] = {}

    att_ok, att_issues, att = frozen_zone.verify_attestation(repo_root)
    checks["zone_attestation_ok"] = att_ok
    checks["zone_attestation_issues"] = list(att_issues)
    checks["zone_hash"] = att.zone_hash
    if not att_ok:
        reasons.append(REASON_ZONE_HASH_MISMATCH)
    if expected_zone_hash is not None and att.zone_hash != expected_zone_hash:
        checks["expected_zone_hash"] = str(expected_zone_hash)
        reasons.append(REASON_ZONE_HASH_MISMATCH)

    ledger_ok, ledger_errors, entries = _clean_entries(ledger_path)
    checks["meta_ledger_ok"] = ledger_ok
    checks["meta_ledger_errors"] = list(ledger_errors)
    if not ledger_ok:
        reasons.append(REASON_CHAIN_BREAK)
        entries = []

    manifest = frozen_zone.load_manifest(repo_root)
    changed_paths = [p.replace("\\", "/") for p in (proposed_changed_paths or [])]
    touched = frozen_zone.zone_touching_paths(
        changed_paths,
        {str(p).replace("\\", "/") for p in manifest.get("frozen_paths", [])},
    )
    checks["frozen_paths_touched"] = touched
    if touched:
        reasons.append(REASON_FROZEN_PATH_CHANGE_PROPOSED)

    if entries:
        holdout_exhausted = _holdout_exhausted(entries)
        trailing = trailing_rejection_count(entries)
        directives = caution_directives(entries, threshold=wither_threshold)
    else:
        holdout_exhausted = False
        trailing = 0
        directives = []
    checks["holdout_budget_exhausted"] = holdout_exhausted
    checks["trailing_rejections"] = trailing
    checks["max_consecutive_rejections"] = int(max_consecutive_rejections)
    checks["caution_directives"] = directives
    if holdout_exhausted:
        reasons.append(REASON_HOLDOUT_BUDGET_EXHAUSTED)
    if trailing >= int(max_consecutive_rejections) and int(max_consecutive_rejections) > 0:
        reasons.append(REASON_CONSECUTIVE_REJECTIONS)

    if proposed_lineage_id is not None and is_withered(
        entries, str(proposed_lineage_id), threshold=wither_threshold
    ):
        checks["proposed_lineage_id"] = str(proposed_lineage_id)
        reasons.append(REASON_LINEAGE_WITHERED)

    cost_exceeded = max_cost is not None and float(cost_spent) > float(max_cost)
    seconds_exceeded = max_seconds is not None and float(seconds_spent) > float(max_seconds)
    checks["cost_spent"] = float(cost_spent)
    checks["max_cost"] = float(max_cost) if max_cost is not None else None
    checks["seconds_spent"] = float(seconds_spent)
    checks["max_seconds"] = float(max_seconds) if max_seconds is not None else None
    checks["cost_budget_exceeded"] = cost_exceeded
    checks["time_budget_exceeded"] = seconds_exceeded
    if cost_exceeded or seconds_exceeded:
        reasons.append(REASON_COST_TIME_BUDGET_EXCEEDED)

    reasons = sorted(set(reasons))
    ledger_root = controller.meta_ledger_root(ledger_path) if ledger_ok else controller.GENESIS
    return BreakerReport(
        halted=bool(reasons),
        reasons=reasons,
        checks=checks,
        ledger_root=ledger_root,
        zone_hash=att.zone_hash,
    )


def append_halt(
    ledger_path: str | Path,
    *,
    run_id: str,
    report: BreakerReport | dict[str, Any],
) -> dict[str, Any]:
    report_record = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    require_sealed_report(report_record)
    if report_record.get("halted") is not True:
        raise CircuitBreakerError("cannot append a halt for a non-halted breaker report")
    if current_halt(ledger_path) is not None:
        raise CircuitBreakerError("meta-ledger already has an active halt")
    return controller.append_meta_event(
        ledger_path,
        event_type=EVENT_HALTED,
        run_id=run_id,
        payload={"breaker_report": report_record},
    )


def _resolve_restart_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    token = os.environ.get(HUMAN_RESTART_TOKEN_ENV)
    return token or None


def build_restart_clearance(
    *,
    clearance_id: str,
    halt_entry_hash: str,
    human_reviewer: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "schema": RESTART_CLEARANCE_SCHEMA,
        "clearance_id": str(clearance_id),
        "halt_entry_hash": str(halt_entry_hash),
        "human_reviewer": str(human_reviewer),
        "rationale": str(rationale),
    }


def validate_restart_clearance(record: dict[str, Any]) -> None:
    if record.get("schema") != RESTART_CLEARANCE_SCHEMA:
        raise CircuitBreakerError(f"restart clearance schema must be {RESTART_CLEARANCE_SCHEMA}")
    for key in ("clearance_id", "halt_entry_hash", "human_reviewer", "rationale"):
        if not record.get(key):
            raise CircuitBreakerError(f"restart clearance.{key} missing")


def seal_restart_clearance(record: dict[str, Any]) -> dict[str, Any]:
    validate_restart_clearance(record)
    sealed = {k: v for k, v in record.items() if k != CLEARANCE_HASH_KEY}
    sealed[CLEARANCE_HASH_KEY] = _hash_excluding(sealed, CLEARANCE_HASH_KEY)
    return sealed


def require_sealed_restart_clearance(record: dict[str, Any]) -> None:
    validate_restart_clearance(record)
    recorded = record.get(CLEARANCE_HASH_KEY)
    if not recorded:
        raise CircuitBreakerError("restart clearance is not sealed")
    if _hash_excluding(record, CLEARANCE_HASH_KEY) != recorded:
        raise CircuitBreakerError("clearance_hash does not match restart clearance content")


def append_restart_clearance(
    ledger_path: str | Path,
    *,
    run_id: str,
    clearance: dict[str, Any],
    restart_token: Optional[str] = None,
) -> dict[str, Any]:
    require_sealed_restart_clearance(clearance)
    token = _resolve_restart_token(restart_token)
    if not token:
        raise CircuitBreakerError(f"human restart token missing ({HUMAN_RESTART_TOKEN_ENV})")
    if token != clearance.get("clearance_id"):
        raise CircuitBreakerError("human restart token does not match clearance_id")
    active = current_halt(ledger_path)
    if active is None:
        raise CircuitBreakerError("no active halt to clear")
    if clearance.get("halt_entry_hash") != _entry_hash(active):
        raise CircuitBreakerError("restart clearance does not bind the active halt")
    return controller.append_meta_event(
        ledger_path,
        event_type=EVENT_RESTART_AUTHORIZED,
        run_id=run_id,
        payload={"clearance": dict(clearance)},
    )
