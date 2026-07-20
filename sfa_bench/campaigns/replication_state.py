"""Filesystem-derived progress for the fixed GPT-5.6 replication slots."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sfa_bench.campaigns.capture.canonical import CaptureError, ensure_no_reparse_ancestors, require_object, strict_json_file
from sfa_bench.campaigns.capture.storage import attempt_directories, read_record
from sfa_bench.campaigns.replication_plan import block_authorization_path, capture_root, slot_projection


def _attempt_state(run_dir: Path) -> tuple[int, str, bool | None]:
    attempts = attempt_directories(run_dir)
    if len(attempts) > 1:
        raise CaptureError("REPLICATION_ATTEMPT_LIMIT_EXCEEDED", "slot contains more than one attempt", str(run_dir))
    if not attempts:
        return 0, "initialized", None
    path = attempts[0] / "attempt.json"
    if not path.is_file():
        return 1, "attempt_uncommitted", None
    attempt = read_record(path)
    if attempt.get("attempt_number") != 1 or attempt.get("execution_id") != run_dir.name:
        raise CaptureError("REPLICATION_ATTEMPT_IDENTITY_MISMATCH", "attempt identity changed", str(path))
    complete = attempt.get("complete")
    if not isinstance(complete, bool):
        raise CaptureError("REPLICATION_ATTEMPT_STATE_INVALID", "attempt completion flag is invalid", str(path))
    return 1, "captured" if complete else "interrupted", complete


def scan_slot_states(repo_root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    root = capture_root(repo_root)
    states: list[dict[str, Any]] = []
    pending_seen = False
    for slot in plan["slots"]:
        run_dir = root / slot["campaign_id"] / slot["execution_id"]
        ensure_no_reparse_ancestors(root, run_dir)
        if not run_dir.exists():
            pending_seen = True
            states.append({**slot_projection(slot), "occupied": False, "attempt_count": 0, "capture_state": "pending", "complete": None})
            continue
        if pending_seen:
            raise CaptureError("REPLICATION_SLOT_ORDER_VIOLATION", "later slot occupied while an earlier slot is pending", str(run_dir))
        if not run_dir.is_dir():
            raise CaptureError("REPLICATION_SLOT_OCCUPIED_INVALID", "slot path is not a run directory", str(run_dir))
        run = read_record(run_dir / "run.json")
        prereg = read_record(run_dir / "preregistration.json")
        if run.get("campaign_id") != slot["campaign_id"] or run.get("execution_id") != slot["execution_id"]:
            raise CaptureError("REPLICATION_SLOT_IDENTITY_MISMATCH", "run identity differs from slot plan", str(run_dir))
        if prereg.get("campaign_id") != slot["campaign_id"] or prereg.get("provider_model_identifier") != slot["model"]:
            raise CaptureError("REPLICATION_MODEL_SUBSTITUTION_DETECTED", "stored model differs from exact slot alias", str(run_dir))
        attempts, state, complete = _attempt_state(run_dir)
        states.append({**slot_projection(slot), "occupied": True, "attempt_count": attempts, "capture_state": state, "complete": complete})
    return states


def next_pending_slot(states: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in states if item["occupied"] is False), None)


def status_document(repo_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    from sfa_bench.campaigns.replication_authorization import verify_block_authorization

    states = scan_slot_states(repo_root, plan)
    next_slot = next_pending_slot(states)
    blocks: list[dict[str, Any]] = []
    for block in range(1, 11):
        members = [item for item in states if item["block"] == block]
        path = block_authorization_path(repo_root, block)
        authorization = None
        if path.is_file():
            authorization = require_object(strict_json_file(path, require_canonical=True))
            verify_block_authorization(authorization, plan)
        blocks.append({
            "block": block,
            "occupied_slots": sum(1 for item in members if item["occupied"]),
            "slot_count": 3,
            "authorization_present": authorization is not None,
            "authorization_sha256": authorization.get("authorization_sha256") if authorization else None,
            "complete": all(item["occupied"] for item in members),
        })
    return {
        "schema_version": "sfa_bench.openai_gpt56_replication.status.v1",
        "replication_id": plan["replication_id"],
        "slot_plan_sha256": plan["slot_plan_sha256"],
        "occupied_slots": sum(1 for item in states if item["occupied"]),
        "pending_slots": sum(1 for item in states if not item["occupied"]),
        "complete": next_slot is None,
        "next_slot": slot_projection(next_slot) if next_slot else None,
        "next_authorizable_block": next_slot["block"] if next_slot else None,
        "blocks": blocks,
        "slots": states,
        "provider_request_sent": False,
    }
