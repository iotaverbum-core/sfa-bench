"""Meta-ledger + circuit breakers (SFA-AutoLab v0, Item 5).

FROZEN ZONE — ledger code and halt policy, listed in
``autolab/frozen_manifest.json``. The loop may not patch it.

The **meta-ledger** is an append-only, hash-chained record of AutoLab events
(proposals, rejections, promotions, rollbacks, halts) — one level above the
occurrence ledger. Every proposal carries a **patch fingerprint**; rejections are
**inscribed** with their reasons; and recurrence over the ledger feeds **caution
directives** into the next proposal context. A patch lineage that fails ``K``
times **withers** — it is terminally blocked and never re-proposed.

**Circuit breakers** put the loop into *halt-and-hold* on any of:

  1. zone hash mismatch (the frozen zone drifted),
  2. chain break (the meta-ledger hash chain is broken),
  3. holdout budget exhausted,
  4. ``N`` consecutive rejections,
  5. any diff proposing gate/policy (frozen-zone) changes,
  6. cost/time budget exceeded.

A halt requires a **human restart** (a token the loop cannot produce). There is
no autonomous un-halt.

Two invariants shape this module besides the ones above:

  * **Builder cannot attest (3).** Caution directives are *advisory* proposal
    context. They never enter the gate; they only shape the *next* proposal.
  * **Determinism (6).** Chaining, recurrence, and breaker evaluation are pure
    functions; no wall-clock, network, or model.

Stdlib-only; standalone canonical hashing mirrors ``sfa.hashing``.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

LEDGER_SCHEMA = "sfa.autolab.meta_ledger.v0"
ENTRY_SCHEMA = "sfa.autolab.meta_ledger_entry.v0"
GENESIS = "GENESIS"

# Event kinds.
EVENT_PROPOSED = "proposed"
EVENT_REJECTED = "rejected"
EVENT_PROMOTED = "promoted"
EVENT_ROLLED_BACK = "rolled_back"
EVENT_HALT = "halt"

# Defaults (documented; overridable per call).
DEFAULT_MAX_CONSECUTIVE_REJECTIONS = 3
DEFAULT_WITHER_K = 3
RESTART_TOKEN_ENV = "SFA_AUTOLAB_RESTART_TOKEN"

# Halt reasons.
HALT_ZONE_HASH_MISMATCH = "zone_hash_mismatch"
HALT_CHAIN_BREAK = "chain_break"
HALT_HOLDOUT_BUDGET_EXHAUSTED = "holdout_budget_exhausted"
HALT_CONSECUTIVE_REJECTIONS = "consecutive_rejections"
HALT_GATE_POLICY_CHANGE = "gate_policy_change_proposed"
HALT_COST_TIME_BUDGET = "cost_time_budget_exceeded"

ALL_HALT_REASONS = (
    HALT_ZONE_HASH_MISMATCH, HALT_CHAIN_BREAK, HALT_HOLDOUT_BUDGET_EXHAUSTED,
    HALT_CONSECUTIVE_REJECTIONS, HALT_GATE_POLICY_CHANGE, HALT_COST_TIME_BUDGET,
)


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


# ---------------------------------------------------------------------------
# Append-only, hash-chained meta-ledger.
# ---------------------------------------------------------------------------
def _entry_hash(entry: dict[str, Any]) -> str:
    return sha256_hex({k: v for k, v in entry.items() if k != "entry_hash"})


def append_event(entries: list[dict[str, Any]], *, event: str, patch_fingerprint: Optional[str],
                 loop_hash: Optional[str] = None, lineage_id: Optional[str] = None,
                 detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Append one meta-ledger event and return the chained entry."""
    prev = entries[-1]["entry_hash"] if entries else GENESIS
    entry = {
        "schema": ENTRY_SCHEMA,
        "seq": len(entries),
        "event": event,
        "patch_fingerprint": patch_fingerprint,
        "lineage_id": lineage_id or patch_fingerprint,
        "loop_hash": loop_hash,
        "detail": detail or {},
        "prev_hash": prev,
    }
    entry["entry_hash"] = _entry_hash(entry)
    entries.append(entry)
    return entry


def inscribe_from_loop(entries: list[dict[str, Any]], loop_record: dict[str, Any],
                       *, lineage_id: Optional[str] = None) -> dict[str, Any]:
    """Inscribe a loop iteration: proposal + (rejection or gate-green outcome).

    A rejected iteration is inscribed as ``rejected`` with the gate reasons.
    A gate-green iteration is inscribed as ``proposed`` (promotion, if any, is a
    separate human-authorized ``promoted`` event).
    """
    fingerprint = loop_record["proposal"]["patch_fingerprint"]
    loop_hash = loop_record.get("loop_hash")
    gate = loop_record.get("gate", {})
    if gate.get("gate_green"):
        return append_event(entries, event=EVENT_PROPOSED, patch_fingerprint=fingerprint,
                            loop_hash=loop_hash, lineage_id=lineage_id,
                            detail={"gate_green": True})
    return append_event(entries, event=EVENT_REJECTED, patch_fingerprint=fingerprint,
                        loop_hash=loop_hash, lineage_id=lineage_id,
                        detail={"gate_green": False, "reasons": gate.get("reasons", [])})


def verify_chain(entries: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Detect deletion, insertion, reorder, or edit. Returns (ok, errors)."""
    errors: list[str] = []
    prev = GENESIS
    for i, entry in enumerate(entries):
        if entry.get("seq") != i:
            errors.append(f"seq mismatch at {i}: stored {entry.get('seq')}")
        if entry.get("prev_hash") != prev:
            errors.append(f"broken link at {i}: prev_hash mismatch")
        if _entry_hash(entry) != entry.get("entry_hash"):
            errors.append(f"entry hash mismatch at {i}: entry was edited")
        prev = entry.get("entry_hash")
    return (not errors), errors


def seal_ledger(entries: list[dict[str, Any]]) -> dict[str, Any]:
    record = {"schema": LEDGER_SCHEMA, "count": len(entries), "entries": entries,
              "head_hash": entries[-1]["entry_hash"] if entries else GENESIS}
    record["ledger_hash"] = sha256_hex({k: v for k, v in record.items() if k != "ledger_hash"})
    return record


# ---------------------------------------------------------------------------
# Recurrence-fed caution directives + wither.
# ---------------------------------------------------------------------------
def rejection_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Rejections per patch lineage."""
    counts: Counter[str] = Counter()
    for entry in entries:
        if entry.get("event") == EVENT_REJECTED:
            counts[entry.get("lineage_id") or entry.get("patch_fingerprint")] += 1
    return dict(counts)


def is_withered(entries: list[dict[str, Any]], lineage_id: str, *, k: int = DEFAULT_WITHER_K) -> bool:
    """A lineage withers (terminal) once it has accrued ``k`` rejections."""
    return rejection_counts(entries).get(lineage_id, 0) >= k


def rejection_reasons(entries: list[dict[str, Any]], lineage_id: str) -> list[str]:
    reasons: list[str] = []
    for entry in entries:
        if entry.get("event") == EVENT_REJECTED and \
                (entry.get("lineage_id") or entry.get("patch_fingerprint")) == lineage_id:
            reasons.extend(entry.get("detail", {}).get("reasons", []))
    return reasons


def caution_directives(entries: list[dict[str, Any]], *, k: int = DEFAULT_WITHER_K) -> list[dict[str, Any]]:
    """Advisory caution directives for the next proposal context.

    A lineage that has been rejected at least once earns a caution; at ``k``
    rejections it is *withered* (terminal: a hard "do not re-propose").
    """
    directives = []
    for lineage_id, count in sorted(rejection_counts(entries).items()):
        withered = count >= k
        directives.append({
            "lineage_id": lineage_id,
            "rejections": count,
            "withered": withered,
            "directive": ("TERMINAL: do not re-propose this lineage (withered)"
                          if withered else
                          f"CAUTION: this lineage was rejected {count} time(s); avoid its known failure"),
            "known_failure_reasons": sorted(set(rejection_reasons(entries, lineage_id))),
        })
    return directives


def next_proposal_context(entries: list[dict[str, Any]], *, k: int = DEFAULT_WITHER_K) -> dict[str, Any]:
    """Advisory context for the next proposal. NEVER enters the gate (invariant 3)."""
    directives = caution_directives(entries, k=k)
    return {
        "advisory": True,
        "excluded_from_gate": True,
        "cautions": directives,
        "withered_lineages": [d["lineage_id"] for d in directives if d["withered"]],
    }


# ---------------------------------------------------------------------------
# Circuit breakers.
# ---------------------------------------------------------------------------
@dataclass
class BreakerContext:
    entries: list[dict[str, Any]] = field(default_factory=list)
    zone_ok: bool = True
    holdout_exhausted: bool = False
    proposed_changed_paths: list[str] = field(default_factory=list)
    frozen_paths: set[str] = field(default_factory=set)
    max_consecutive_rejections: int = DEFAULT_MAX_CONSECUTIVE_REJECTIONS
    cost_spent: float = 0.0
    cost_budget: Optional[float] = None
    time_spent: float = 0.0
    time_budget: Optional[float] = None


def _consecutive_rejections(entries: list[dict[str, Any]]) -> int:
    count = 0
    for entry in reversed(entries):
        if entry.get("event") == EVENT_REJECTED:
            count += 1
        elif entry.get("event") in (EVENT_PROPOSED, EVENT_PROMOTED, EVENT_ROLLED_BACK):
            break
    return count


def evaluate_breakers(ctx: BreakerContext) -> dict[str, Any]:
    """Evaluate all six breakers. Any trip => halt-and-hold."""
    tripped: list[dict[str, Any]] = []

    if not ctx.zone_ok:
        tripped.append({"breaker": HALT_ZONE_HASH_MISMATCH,
                        "detail": "frozen zone hash does not match the sealed manifest"})

    chain_ok, chain_errors = verify_chain(ctx.entries)
    if not chain_ok:
        tripped.append({"breaker": HALT_CHAIN_BREAK, "detail": chain_errors})

    if ctx.holdout_exhausted:
        tripped.append({"breaker": HALT_HOLDOUT_BUDGET_EXHAUSTED,
                        "detail": "holdout exposure budget exhausted"})

    consecutive = _consecutive_rejections(ctx.entries)
    if consecutive >= ctx.max_consecutive_rejections:
        tripped.append({"breaker": HALT_CONSECUTIVE_REJECTIONS,
                        "detail": f"{consecutive} consecutive rejections "
                                  f"(limit {ctx.max_consecutive_rejections})"})

    gate_paths = sorted(set(p.replace("\\", "/") for p in ctx.proposed_changed_paths) & ctx.frozen_paths)
    if gate_paths:
        tripped.append({"breaker": HALT_GATE_POLICY_CHANGE,
                        "detail": {"frozen_paths_touched": gate_paths}})

    if ctx.cost_budget is not None and ctx.cost_spent > ctx.cost_budget:
        tripped.append({"breaker": HALT_COST_TIME_BUDGET,
                        "detail": f"cost {ctx.cost_spent} > budget {ctx.cost_budget}"})
    if ctx.time_budget is not None and ctx.time_spent > ctx.time_budget:
        tripped.append({"breaker": HALT_COST_TIME_BUDGET,
                        "detail": f"time {ctx.time_spent} > budget {ctx.time_budget}"})

    halted = bool(tripped)
    report = {
        "schema": "sfa.autolab.breaker_report.v0",
        "halted": halted,
        "tripped": tripped,
        "tripped_breakers": sorted({t["breaker"] for t in tripped}),
        "requires_human_restart": halted,
    }
    report["report_hash"] = sha256_hex({k: v for k, v in report.items() if k != "report_hash"})
    return report


# ---------------------------------------------------------------------------
# Halt-and-hold state (human restart required).
# ---------------------------------------------------------------------------
@dataclass
class HaltState:
    halted: bool
    reasons: list[str] = field(default_factory=list)
    cleared_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"halted": self.halted, "reasons": list(self.reasons),
                "requires_human_restart": self.halted, "cleared_by": self.cleared_by}


def halt(report: dict[str, Any]) -> HaltState:
    return HaltState(halted=bool(report.get("halted")), reasons=list(report.get("tripped_breakers", [])))


def clear_halt(state: HaltState, restart_token: Optional[str]) -> HaltState:
    """Clear a halt — only with a human restart token. No autonomous un-halt."""
    if not state.halted:
        return state
    if not restart_token:
        # Held: the loop cannot restart itself.
        return HaltState(halted=True, reasons=state.reasons, cleared_by=None)
    return HaltState(halted=False, reasons=state.reasons, cleared_by=restart_token)


def resolve_restart_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    return os.environ.get(RESTART_TOKEN_ENV) or None


# ---------------------------------------------------------------------------
# File-backed ledger helpers (optional persistence).
# ---------------------------------------------------------------------------
def read_ledger(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid meta-ledger JSON on line {line_no}: {exc}") from exc
    return out


def write_ledger(path: str | Path, entries: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
