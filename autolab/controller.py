"""AutoLab controller, meta-ledger, and holdout budget guard (Item 3).

FROZEN ZONE - this module is controller/gate machinery and is listed in
``autolab/frozen_manifest.json``. The AutoLab loop may not patch it; changes flow
only through the human-only amendment channel.

The controller enforces the temporal boundary that Item 2 only declared:

* attest the frozen zone before an iteration;
* seal and append the pre-registration declaration to an append-only meta-ledger;
* reserve any requested holdout budget in that ledger before the builder runs;
* invoke the builder only after those records exist;
* attest the frozen zone again after the builder returns.

The builder receives the sealed declaration, but no builder-supplied field can
create the declaration, consume holdout budget, or attest the zone. Those records
are written by this frozen controller from canonical inputs.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from autolab import frozen_zone
from autolab import preregistration

CONTROLLER_SCHEMA = "sfa.autolab.controller.v0"
META_LEDGER_SCHEMA = "sfa.autolab.meta_ledger.entry.v0"
HOLDOUT_BUDGET_SCHEMA = "sfa.autolab.holdout_budget.v0"
HOLDOUT_RECEIPT_SCHEMA = "sfa.autolab.holdout_consumption.v0"

GENESIS = "GENESIS"
ENTRY_HASH_KEY = "entry_hash"


class ControllerError(RuntimeError):
    """Raised when the controller refuses to run an unsafe iteration."""


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _entry_hash(entry: dict[str, Any]) -> str:
    return sha256_hex({k: v for k, v in entry.items() if k != ENTRY_HASH_KEY})


def read_meta_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ControllerError(f"invalid meta-ledger JSON on line {line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ControllerError(f"invalid meta-ledger entry on line {line_no}: not an object")
            out.append(record)
    return out


def verify_meta_ledger(path: str | Path) -> tuple[bool, list[tuple[int, str]], int]:
    try:
        entries = read_meta_ledger(path)
    except ControllerError as exc:
        return False, [(-1, str(exc))], 0
    errors: list[tuple[int, str]] = []
    prev = GENESIS
    for index, entry in enumerate(entries):
        if entry.get("schema") != META_LEDGER_SCHEMA:
            errors.append((index, f"schema mismatch: {entry.get('schema')!r}"))
        if entry.get("seq") != index:
            errors.append((index, f"seq mismatch: stored {entry.get('seq')} expected {index}"))
        if entry.get("prev_hash") != prev:
            errors.append((index, "broken link: prev_hash does not match previous entry"))
        if _entry_hash(entry) != entry.get(ENTRY_HASH_KEY):
            errors.append((index, "entry hash mismatch: entry was edited"))
        prev = entry.get(ENTRY_HASH_KEY)
    return not errors, errors, len(entries)


def append_meta_event(
    path: str | Path,
    *,
    event_type: str,
    run_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ok, errors, _ = verify_meta_ledger(path)
    if not ok:
        raise ControllerError(f"meta-ledger is not append-only clean: {errors}")
    path = Path(path)
    os.makedirs(path.parent or Path("."), exist_ok=True)
    entries = read_meta_ledger(path)
    entry = {
        "schema": META_LEDGER_SCHEMA,
        "seq": len(entries),
        "prev_hash": entries[-1][ENTRY_HASH_KEY] if entries else GENESIS,
        "run_id": str(run_id),
        "event_type": str(event_type),
        "payload": dict(payload),
    }
    entry[ENTRY_HASH_KEY] = _entry_hash(entry)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def meta_ledger_root(path: str | Path) -> str:
    entries = read_meta_ledger(path)
    return entries[-1][ENTRY_HASH_KEY] if entries else GENESIS


def build_holdout_budget(
    *,
    budget_id: str,
    suite: str,
    version: str,
    max_uses: int,
    unit: str = "model_run",
    commitment_path: str = "holdout/frontier-delta-holdout_hd-v0.1.0_PREREGISTRATION.md",
) -> dict[str, Any]:
    max_uses = int(max_uses)
    if max_uses < 0:
        raise ControllerError("holdout max_uses must be non-negative")
    return {
        "schema": HOLDOUT_BUDGET_SCHEMA,
        "budget_id": str(budget_id),
        "suite": str(suite),
        "version": str(version),
        "max_uses": max_uses,
        "unit": str(unit),
        "commitment_path": str(commitment_path),
    }


def _declared_holdout_request(eval_plan: dict[str, Any]) -> Optional[dict[str, Any]]:
    holdout = eval_plan.get("holdout")
    suite_name = str(eval_plan.get("suite", "")).lower()
    if holdout is None:
        if "holdout" in suite_name:
            raise ControllerError(
                "holdout eval_plan requires explicit eval_plan.holdout budget binding"
            )
        return None
    if not isinstance(holdout, dict):
        raise ControllerError("eval_plan.holdout must be an object")
    units = holdout.get("units", 1)
    if isinstance(units, bool):
        raise ControllerError("eval_plan.holdout.units must be a positive integer")
    units = int(units)
    if units <= 0:
        raise ControllerError("eval_plan.holdout.units must be a positive integer")
    request = {
        "budget_id": str(holdout.get("budget_id", "")),
        "suite": str(holdout.get("suite", "")),
        "version": str(holdout.get("version", "")),
        "units": units,
    }
    missing = [key for key in ("budget_id", "suite", "version") if not request[key]]
    if missing:
        raise ControllerError(f"eval_plan.holdout missing required fields: {missing}")
    return request


def holdout_units_used(entries: list[dict[str, Any]], budget_id: str) -> int:
    used = 0
    for entry in entries:
        if entry.get("event_type") != "holdout_budget_consumed":
            continue
        payload = entry.get("payload", {})
        if isinstance(payload, dict) and payload.get("budget_id") == budget_id:
            used += int(payload.get("units", 0))
    return used


def reserve_holdout_budget(
    ledger_path: str | Path,
    *,
    run_id: str,
    declaration_hash: str,
    eval_plan: dict[str, Any],
    holdout_budget: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    request = _declared_holdout_request(eval_plan)
    if request is None:
        return None
    if holdout_budget is None:
        raise ControllerError("holdout eval_plan requires a controller holdout_budget")
    if holdout_budget.get("schema") != HOLDOUT_BUDGET_SCHEMA:
        raise ControllerError(f"holdout budget schema must be {HOLDOUT_BUDGET_SCHEMA}")
    for key in ("budget_id", "suite", "version"):
        if request[key] != holdout_budget.get(key):
            raise ControllerError(
                f"holdout budget {key} mismatch: declared {request[key]!r} "
                f"!= budget {holdout_budget.get(key)!r}"
            )
    entries = read_meta_ledger(ledger_path)
    used_before = holdout_units_used(entries, request["budget_id"])
    max_uses = int(holdout_budget["max_uses"])
    used_after = used_before + request["units"]
    if used_after > max_uses:
        raise ControllerError(
            f"holdout budget exhausted for {request['budget_id']}: "
            f"{used_before} used + {request['units']} requested > {max_uses}"
        )
    receipt = {
        "schema": HOLDOUT_RECEIPT_SCHEMA,
        "budget_id": request["budget_id"],
        "suite": request["suite"],
        "version": request["version"],
        "units": request["units"],
        "used_before": used_before,
        "used_after": used_after,
        "remaining_after": max_uses - used_after,
        "declaration_hash": str(declaration_hash),
    }
    return append_meta_event(
        ledger_path,
        event_type="holdout_budget_consumed",
        run_id=run_id,
        payload=receipt,
    )


def _require_clean_attestation(root: str | Path, *, label: str) -> frozen_zone.Attestation:
    ok, issues, attestation = frozen_zone.verify_attestation(root)
    if not ok:
        raise ControllerError(f"{label} frozen-zone attestation failed: {issues}")
    return attestation


@dataclass
class ControllerRun:
    run_id: str
    declaration: dict[str, Any]
    declaration_entry: dict[str, Any]
    holdout_entry: Optional[dict[str, Any]]
    builder_invoked_entry: dict[str, Any]
    builder_completed_entry: dict[str, Any]
    pre_zone_hash: str
    post_zone_hash: str
    ledger_root: str
    builder_result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTROLLER_SCHEMA,
            "run_id": self.run_id,
            "declaration_hash": self.declaration["declaration_hash"],
            "declaration_entry_hash": self.declaration_entry[ENTRY_HASH_KEY],
            "holdout_entry_hash": (
                self.holdout_entry[ENTRY_HASH_KEY] if self.holdout_entry is not None else None
            ),
            "builder_invoked_entry_hash": self.builder_invoked_entry[ENTRY_HASH_KEY],
            "builder_completed_entry_hash": self.builder_completed_entry[ENTRY_HASH_KEY],
            "pre_zone_hash": self.pre_zone_hash,
            "post_zone_hash": self.post_zone_hash,
            "ledger_root": self.ledger_root,
            "builder_result_hash": self.builder_result_hash,
        }


Builder = Callable[[dict[str, Any]], Any]


def run_iteration(
    *,
    repo_root: str | Path,
    ledger_path: str | Path,
    run_id: str,
    declaration: dict[str, Any],
    builder: Builder,
    holdout_budget: Optional[dict[str, Any]] = None,
) -> ControllerRun:
    """Run one controlled builder iteration.

    The builder callback is invoked only after the sealed declaration and any
    holdout-budget receipt have been appended to the meta-ledger.
    """
    ok, errors, _ = verify_meta_ledger(ledger_path)
    if not ok:
        raise ControllerError(f"meta-ledger is not append-only clean: {errors}")

    pre = _require_clean_attestation(repo_root, label="pre")
    append_meta_event(
        ledger_path,
        event_type="zone_attested_pre",
        run_id=run_id,
        payload={"manifest_version": pre.manifest_version, "zone_hash": pre.zone_hash},
    )

    sealed_declaration = preregistration.seal_declaration(declaration)
    if sealed_declaration.get("phase") != "pre_patch":
        raise ControllerError("declaration phase must be pre_patch")
    declaration_hash = sealed_declaration["declaration_hash"]
    declaration_entry = append_meta_event(
        ledger_path,
        event_type="declaration_sealed",
        run_id=run_id,
        payload={
            "declaration_hash": declaration_hash,
            "declaration": sealed_declaration,
        },
    )

    holdout_entry = reserve_holdout_budget(
        ledger_path,
        run_id=run_id,
        declaration_hash=declaration_hash,
        eval_plan=sealed_declaration["eval_plan"],
        holdout_budget=holdout_budget,
    )

    builder_invoked_entry = append_meta_event(
        ledger_path,
        event_type="builder_invoked",
        run_id=run_id,
        payload={
            "declaration_hash": declaration_hash,
            "declaration_entry_hash": declaration_entry[ENTRY_HASH_KEY],
            "holdout_entry_hash": (
                holdout_entry[ENTRY_HASH_KEY] if holdout_entry is not None else None
            ),
        },
    )

    builder_result = builder(sealed_declaration)
    builder_result_hash = sha256_hex(builder_result)
    builder_completed_entry = append_meta_event(
        ledger_path,
        event_type="builder_completed",
        run_id=run_id,
        payload={
            "declaration_hash": declaration_hash,
            "builder_result_hash": builder_result_hash,
        },
    )

    post = _require_clean_attestation(repo_root, label="post")
    if post.zone_hash != pre.zone_hash:
        raise ControllerError(
            f"frozen zone changed during iteration: {pre.zone_hash} -> {post.zone_hash}"
        )
    append_meta_event(
        ledger_path,
        event_type="zone_attested_post",
        run_id=run_id,
        payload={"manifest_version": post.manifest_version, "zone_hash": post.zone_hash},
    )

    ok, errors, _ = verify_meta_ledger(ledger_path)
    if not ok:
        raise ControllerError(f"meta-ledger failed after append: {errors}")

    return ControllerRun(
        run_id=str(run_id),
        declaration=sealed_declaration,
        declaration_entry=declaration_entry,
        holdout_entry=holdout_entry,
        builder_invoked_entry=builder_invoked_entry,
        builder_completed_entry=builder_completed_entry,
        pre_zone_hash=pre.zone_hash,
        post_zone_hash=post.zone_hash,
        ledger_root=meta_ledger_root(ledger_path),
        builder_result_hash=builder_result_hash,
    )
