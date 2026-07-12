"""Immutable, hash-chained lifecycle events for governed campaign capture."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .canonical import (
    CaptureError,
    canonical_bytes,
    ensure_no_reparse_ancestors,
    require_exact_fields,
    sha256_value,
    strict_json_file,
    validate_timestamp,
    write_exclusive_json,
)


EVENT_SCHEMA = "sfa_bench.campaign_capture.lifecycle_event.v1"
ZERO_HASH = "0" * 64
STATES = frozenset(
    {
        "draft",
        "validated",
        "locked",
        "execution_authorized",
        "capturing",
        "captured",
        "interrupted",
        "aborted",
        "sealed",
        "judged",
        "review_required",
    }
)
TRANSITION_EVENTS: dict[tuple[str | None, str], str] = {
    (None, "draft"): "run_drafted",
    ("draft", "validated"): "campaign_validated",
    ("validated", "locked"): "benchmark_locked",
    ("locked", "execution_authorized"): "execution_authorization_bound",
    ("execution_authorized", "capturing"): "capture_started",
    ("capturing", "captured"): "capture_completed",
    ("capturing", "interrupted"): "capture_interrupted",
    ("capturing", "aborted"): "capture_aborted",
    ("interrupted", "capturing"): "capture_resumed",
    ("interrupted", "aborted"): "capture_aborted",
    ("captured", "sealed"): "capture_sealed",
    ("aborted", "sealed"): "aborted_capture_sealed",
    ("sealed", "judged"): "judgment_sealed",
    ("sealed", "review_required"): "human_review_required",
    ("judged", "review_required"): "human_review_required",
}
OCCURRENCE_STATES: dict[str, frozenset[str]] = {
    "request_preserved": frozenset({"capturing"}),
    "response_preserved": frozenset({"capturing"}),
    "attempt_interrupted": frozenset({"capturing"}),
    "metadata_rejected": frozenset({"capturing"}),
    "provider_request_id_reused": frozenset({"capturing", "captured"}),
    "recovery_evidence_preserved": frozenset({"interrupted"}),
    "recovery_declared": frozenset({"interrupted"}),
}
_EVENT_NAME_RE = re.compile(r"^(\d{8})\.json$")
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "event_id",
        "execution_id",
        "event_type",
        "transition",
        "from_state",
        "to_state",
        "observed_at",
        "previous_event_sha256",
        "payload",
        "event_sha256",
    }
)


@dataclass(frozen=True)
class LedgerState:
    state: str | None
    root_sha256: str
    events: tuple[dict[str, Any], ...]


def _run_execution_id(run_dir: Path) -> str:
    ensure_no_reparse_ancestors(run_dir, run_dir / "run.json")
    run = strict_json_file(run_dir / "run.json", require_canonical=True)
    if not isinstance(run, dict) or not isinstance(run.get("execution_id"), str):
        raise CaptureError("INVALID_RUN_METADATA", "run metadata has no execution ID")
    return run["execution_id"]


def _event_digest(event: dict[str, Any]) -> str:
    content = dict(event)
    content.pop("event_sha256", None)
    return sha256_value(content)


def _validate_event(
    event: Any,
    *,
    expected_sequence: int,
    expected_execution_id: str,
    expected_previous: str,
    current_state: str | None,
) -> str:
    if not isinstance(event, dict):
        raise CaptureError("MALFORMED_LEDGER_EVENT", "ledger event must be an object")
    require_exact_fields(event, _EVENT_FIELDS)
    if event["schema_version"] != EVENT_SCHEMA:
        raise CaptureError("UNSUPPORTED_EVENT_SCHEMA", "unsupported lifecycle event schema")
    if event["sequence"] != expected_sequence:
        raise CaptureError("LEDGER_SEQUENCE_MISMATCH", "lifecycle sequence is not contiguous")
    if event["execution_id"] != expected_execution_id:
        raise CaptureError("LEDGER_EXECUTION_MISMATCH", "event execution ID changed")
    expected_id = f"{expected_execution_id}:{expected_sequence:08d}:{event['event_type']}"
    if event["event_id"] != expected_id:
        raise CaptureError("EVENT_ID_MISMATCH", "event ID is not deterministic")
    validate_timestamp(event["observed_at"], "$.observed_at")
    if event["previous_event_sha256"] != expected_previous:
        raise CaptureError("LEDGER_CHAIN_MISMATCH", "event previous hash is invalid")
    if event["event_sha256"] != _event_digest(event):
        raise CaptureError("EVENT_HASH_MISMATCH", "event content hash is invalid")
    if not isinstance(event["payload"], dict):
        raise CaptureError("INVALID_EVENT_PAYLOAD", "event payload must be an object")
    if event["from_state"] != current_state:
        raise CaptureError("LIFECYCLE_FROM_STATE_MISMATCH", "event contradicts current state")
    to_state = event["to_state"]
    if to_state not in STATES:
        raise CaptureError("UNKNOWN_LIFECYCLE_STATE", "event contains an unknown state")
    if event["transition"] is True:
        expected_type = TRANSITION_EVENTS.get((current_state, to_state))
        if expected_type is None or event["event_type"] != expected_type:
            raise CaptureError("ILLEGAL_LIFECYCLE_TRANSITION", "illegal or skipped transition")
    elif event["transition"] is False:
        allowed_states = OCCURRENCE_STATES.get(event["event_type"])
        if to_state != current_state or allowed_states is None or current_state not in allowed_states:
            raise CaptureError("ILLEGAL_LIFECYCLE_OCCURRENCE", "occurrence is invalid for current state")
    else:
        raise CaptureError("INVALID_TRANSITION_FLAG", "transition must be boolean")
    return to_state


def verify_ledger(run_dir: Path) -> LedgerState:
    execution_id = _run_execution_id(run_dir)
    directory = run_dir / "ledger" / "events"
    ensure_no_reparse_ancestors(run_dir, directory)
    if not directory.is_dir():
        return LedgerState(None, ZERO_HASH, ())
    paths = sorted(directory.iterdir(), key=lambda path: path.name)
    for path in paths:
        if not path.is_file() or _EVENT_NAME_RE.fullmatch(path.name) is None:
            raise CaptureError("UNEXPECTED_LEDGER_ENTRY", "ledger contains an unexpected entry", str(path))
    events: list[dict[str, Any]] = []
    previous = ZERO_HASH
    state: str | None = None
    for sequence, path in enumerate(paths):
        ensure_no_reparse_ancestors(run_dir, path)
        if path.name != f"{sequence:08d}.json":
            raise CaptureError("LEDGER_SEQUENCE_GAP", "ledger filenames are not contiguous", str(path))
        event = strict_json_file(path, require_canonical=True)
        state = _validate_event(
            event,
            expected_sequence=sequence,
            expected_execution_id=execution_id,
            expected_previous=previous,
            current_state=state,
        )
        previous = event["event_sha256"]
        events.append(event)
    return LedgerState(state, previous, tuple(events))


def _append(
    run_dir: Path,
    *,
    event_type: str,
    to_state: str,
    observed_at: str,
    payload: dict[str, Any],
    transition: bool,
) -> dict[str, Any]:
    validate_timestamp(observed_at, "$.observed_at")
    if not isinstance(payload, dict):
        raise CaptureError("INVALID_EVENT_PAYLOAD", "event payload must be an object")
    ledger = verify_ledger(run_dir)
    sequence = len(ledger.events)
    execution_id = _run_execution_id(run_dir)
    event: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA,
        "sequence": sequence,
        "event_id": f"{execution_id}:{sequence:08d}:{event_type}",
        "execution_id": execution_id,
        "event_type": event_type,
        "transition": transition,
        "from_state": ledger.state,
        "to_state": to_state,
        "observed_at": observed_at,
        "previous_event_sha256": ledger.root_sha256,
        "payload": payload,
    }
    event["event_sha256"] = _event_digest(event)
    _validate_event(
        event,
        expected_sequence=sequence,
        expected_execution_id=execution_id,
        expected_previous=ledger.root_sha256,
        current_state=ledger.state,
    )
    target = run_dir / "ledger" / "events" / f"{sequence:08d}.json"
    try:
        write_exclusive_json(target, event)
    except CaptureError as exc:
        if exc.code == "NO_OVERWRITE":
            raise CaptureError(
                "CONCURRENT_LEDGER_COLLISION",
                "another writer published the next lifecycle event",
                str(target),
            ) from exc
        raise
    if canonical_bytes(strict_json_file(target, require_canonical=True)) != canonical_bytes(event):
        raise CaptureError("EVENT_PUBLICATION_MISMATCH", "published event bytes differ")
    return event


def append_transition(
    run_dir: Path,
    to_state: str,
    *,
    observed_at: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = verify_ledger(run_dir)
    event_type = TRANSITION_EVENTS.get((ledger.state, to_state))
    if event_type is None:
        raise CaptureError(
            "ILLEGAL_LIFECYCLE_TRANSITION",
            f"cannot transition from {ledger.state!r} to {to_state!r}",
        )
    return _append(
        run_dir,
        event_type=event_type,
        to_state=to_state,
        observed_at=observed_at,
        payload=payload or {},
        transition=True,
    )


def append_occurrence(
    run_dir: Path,
    event_type: str,
    *,
    observed_at: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = verify_ledger(run_dir)
    if ledger.state is None:
        raise CaptureError("MISSING_LIFECYCLE_STATE", "cannot append before draft state")
    return _append(
        run_dir,
        event_type=event_type,
        to_state=ledger.state,
        observed_at=observed_at,
        payload=payload or {},
        transition=False,
    )
