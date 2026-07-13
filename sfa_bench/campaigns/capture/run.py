"""Governed initialization, byte capture, recovery, sealing, and verification."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import (
    CaptureAdapter,
    LockedCaptureRequest,
    sanitize_transport_metadata,
    validate_adapter_identity,
    validate_transport_shape,
)
from .authorization import validate_authorization
from .canonical import (
    CaptureError,
    assert_no_governance_claims,
    assert_secret_free,
    bytes_may_contain_secret,
    canonical_bytes,
    ensure_no_reparse_ancestors,
    require_exact_fields,
    sha256_bytes,
    sha256_value,
    strict_json_file,
    validate_timestamp,
)
from .context import require_bound_reference, verify_governed_context
from .lifecycle import (
    ZERO_HASH,
    append_occurrence,
    append_transition,
    verify_ledger,
)
from .storage import (
    attempt_directories,
    create_attempt_dir,
    prepare_run_staging,
    publish_staged_run,
    read_blob,
    read_record,
    write_blob,
    write_record,
)


RUN_SCHEMA = "sfa_bench.campaign_capture.run.v1"
ATTEMPT_SCHEMA = "sfa_bench.campaign_capture.attempt.v1"
CAPTURE_MANIFEST_SCHEMA = "sfa_bench.campaign_capture.manifest.v1"
INTEGRITY_REPORT_SCHEMA = "sfa_bench.campaign_capture.integrity_report.v1"
RUN_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "execution_id",
        "benchmark_lock_digest",
        "benchmark_commit",
        "verifier_commit",
        "release_identifier",
        "authorization_id",
        "authorization_digest",
        "adapter",
        "authorized_request_blob",
        "prompt_reference",
        "case_reference",
        "retry_policy",
        "ratification_status",
        "authority_boundary",
    }
)
REQUEST_FIELDS = frozenset(
    {
        "attempt_number",
        "request_blob",
        "request_sha256",
        "byte_length",
        "preserved_before_transport",
    }
)
ATTEMPT_FIELDS = frozenset(
    {
        "schema_version",
        "execution_id",
        "attempt_number",
        "retry_reason",
        "request_blob",
        "response_blob",
        "transport_status",
        "complete",
        "capture_started_at",
        "capture_completed_at",
        "allowlisted_transport_metadata",
        "diagnostic",
        "warnings",
        "provenance",
        "attempt_digest",
    }
)
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "execution_id",
        "benchmark_lock_digest",
        "benchmark_commit",
        "verifier_commit",
        "release_identifier",
        "authorization_digest",
        "adapter",
        "prompt_reference",
        "case_reference",
        "attempts",
        "raw_evidence_hashes",
        "capture_state",
        "ledger_root_before_seal",
        "capture_started_at",
        "capture_completed_at",
        "warnings",
        "provenance_classes",
        "ratification_status",
        "capture_content_sha256",
        "manifest_sha256",
    }
)
RECOVERY_FIELDS = frozenset(
    {
        "schema_version",
        "action",
        "reason",
        "observed_at",
        "state_before",
        "attempt_number",
        "partial_blob",
        "execution_outcome",
        "provenance_class",
        "recovery_digest",
    }
)


def _load_documents(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    run = read_record(run_dir / "run.json")
    campaign = read_record(run_dir / "preregistration.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    authorization = read_record(run_dir / "execution-authorization.json")
    require_exact_fields(run, RUN_FIELDS)
    if run["schema_version"] != RUN_SCHEMA:
        raise CaptureError("UNSUPPORTED_RUN_SCHEMA", "unsupported run schema")
    return run, campaign, lock, authorization


def _attempt_digest(attempt: dict[str, Any]) -> str:
    content = dict(attempt)
    content.pop("attempt_digest", None)
    return sha256_value(content)


def _manifest_digest(manifest: dict[str, Any]) -> str:
    content = dict(manifest)
    content.pop("manifest_sha256", None)
    return sha256_value(content)


def _recovery_digest(record: dict[str, Any]) -> str:
    content = dict(record)
    content.pop("recovery_digest", None)
    return sha256_value(content)


def _attempt_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    response = attempt["response_blob"]
    return {
        "attempt_number": attempt["attempt_number"],
        "retry_reason": attempt["retry_reason"],
        "transport_status": attempt["transport_status"],
        "complete": attempt["complete"],
        "request_sha256": attempt["request_blob"]["sha256"],
        "response_sha256": response["sha256"] if isinstance(response, dict) else None,
        "response_byte_length": response["byte_length"] if isinstance(response, dict) else None,
        "provider_request_id": attempt["allowlisted_transport_metadata"].get("provider_request_id"),
        "warnings": attempt["warnings"],
        "attempt_digest": attempt["attempt_digest"],
    }


def _read_recovery_records(run_dir: Path) -> list[dict[str, Any]]:
    paths = sorted((run_dir / "recovery").glob("*.json"))
    records: list[dict[str, Any]] = []
    for index, path in enumerate(paths):
        if path.name != f"{index:06d}.json":
            raise CaptureError("RECOVERY_SEQUENCE_MISMATCH", "recovery records are not contiguous", str(path))
        record = read_record(path)
        require_exact_fields(record, RECOVERY_FIELDS)
        if record["schema_version"] != "sfa_bench.campaign_capture.recovery.v1":
            raise CaptureError("UNSUPPORTED_RECOVERY_SCHEMA", "unsupported recovery record schema")
        if record["recovery_digest"] != _recovery_digest(record):
            raise CaptureError("RECOVERY_DIGEST_MISMATCH", "recovery record was modified")
        if record["action"] not in {"record_interruption", "resume", "abort"}:
            raise CaptureError("INVALID_RECOVERY_ACTION", "stored recovery action is invalid")
        if record["state_before"] not in {"capturing", "interrupted"}:
            raise CaptureError("RECOVERY_STATE_MISMATCH", "stored recovery predecessor state is invalid")
        if record["execution_outcome"] != "unknown" or record["provenance_class"] != "operator_declared":
            raise CaptureError("RECOVERY_PROVENANCE_MISMATCH", "stored recovery provenance is invalid")
        if not isinstance(record["reason"], str) or not record["reason"].strip() or len(record["reason"]) > 200:
            raise CaptureError("INVALID_RECOVERY_REASON", "stored recovery reason is invalid")
        assert_secret_free(record["reason"], "$.reason")
        assert_no_governance_claims(record["reason"], "$.reason")
        validate_timestamp(record["observed_at"], "$.observed_at")
        attempt_number = record["attempt_number"]
        if attempt_number is not None and (
            not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1
        ):
            raise CaptureError("INVALID_ATTEMPT_NUMBER", "stored recovery attempt number is invalid")
        if record["partial_blob"] is not None:
            read_blob(run_dir, record["partial_blob"])
            if record["partial_blob"]["capture_disposition"] != "partial":
                raise CaptureError("INVALID_BLOB_DISPOSITION", "recovery evidence must be marked partial")
        records.append(record)
    return records


def _recovery_event_digests(ledger) -> set[str]:
    return {
        value
        for event in ledger.events
        for key, value in event["payload"].items()
        if key == "recovery_digest" and isinstance(value, str)
    }


def _recovery_record_complete(record: dict[str, Any], ledger) -> bool:
    digest = record["recovery_digest"]
    declaration = {
        "action": record["action"],
        "attempt_number": record["attempt_number"],
        "recovery_digest": digest,
    }
    declared = [
        event
        for event in ledger.events
        if event["event_type"] == "recovery_declared" and event["payload"] == declaration
    ]
    if len(declared) > 1:
        raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery declaration is duplicated")
    if record["state_before"] == "capturing":
        occurrence_payload = {"recovery_digest": digest}
        occurrences = [
            event
            for event in ledger.events
            if event["event_type"] == "attempt_interrupted" and event["payload"] == occurrence_payload
        ]
        if len(occurrences) > 1:
            raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery interruption occurrence is duplicated")
        if not occurrences:
            return False
        transition_payload = {"execution_outcome": "unknown", "recovery_digest": digest}
        interrupted = [
            event
            for event in ledger.events
            if event["event_type"] == "capture_interrupted" and event["payload"] == transition_payload
        ]
        if len(interrupted) > 1:
            raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery interruption transition is duplicated")
        if not interrupted:
            return False
    if record["partial_blob"] is not None:
        partial_payload = {
            "partial_sha256": record["partial_blob"]["sha256"],
            "recovery_digest": digest,
        }
        partial = [
            event
            for event in ledger.events
            if event["event_type"] == "recovery_evidence_preserved" and event["payload"] == partial_payload
        ]
        if len(partial) > 1:
            raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery evidence event is duplicated")
        if not partial:
            return False
    if not declared:
        return False
    if record["action"] == "resume":
        final_payload = {"retry_reason": record["reason"], "recovery_digest": digest}
        final_events = [
            event
            for event in ledger.events
            if event["event_type"] == "capture_resumed" and event["payload"] == final_payload
        ]
    elif record["action"] == "abort":
        final_payload = {"execution_outcome": "unknown", "recovery_digest": digest}
        final_events = [
            event
            for event in ledger.events
            if event["event_type"] == "capture_aborted" and event["payload"] == final_payload
        ]
    else:
        final_events = [True]
    if len(final_events) > 1:
        raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery terminal event is duplicated")
    return bool(final_events)


def _verify_recovery_events(records: list[dict[str, Any]], ledger) -> None:
    referenced = _recovery_event_digests(ledger)
    stored = {record["recovery_digest"] for record in records}
    if referenced - stored:
        raise CaptureError("MISSING_RECOVERY_RECORD", "lifecycle references a missing recovery record")
    if stored - referenced:
        raise CaptureError("UNBOUND_RECOVERY_RECORD", "recovery record is not bound by the lifecycle")
    for record in records:
        if not _recovery_record_complete(record, ledger):
            raise CaptureError("INCOMPLETE_RECOVERY_RECORD", "recovery lifecycle binding is incomplete")


def _raw_blob_inventory(run_dir: Path) -> dict[str, bytes]:
    directory = run_dir / "private" / "raw" / "blobs" / "sha256"
    ensure_no_reparse_ancestors(run_dir, directory)
    inventory: dict[str, bytes] = {}
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        ensure_no_reparse_ancestors(run_dir, path)
        if not path.is_file() or path.suffix != ".bin" or len(path.stem) != 64:
            raise CaptureError("UNEXPECTED_RAW_BLOB_ENTRY", "raw blob store contains an unexpected entry", str(path))
        try:
            int(path.stem, 16)
        except ValueError as exc:
            raise CaptureError("UNEXPECTED_RAW_BLOB_ENTRY", "raw blob filename is not a digest", str(path)) from exc
        data = path.read_bytes()
        if sha256_bytes(data) != path.stem:
            raise CaptureError("RAW_BLOB_DIGEST_MISMATCH", "raw blob filename does not match bytes", str(path))
        inventory[path.stem] = data
    return inventory


def _loosely_referenced_raw_hashes(run_dir: Path, records: list[dict[str, Any]]) -> set[str]:
    run = _load_documents(run_dir)[0]
    referenced = {run["authorized_request_blob"]["sha256"]}
    for directory in attempt_directories(run_dir):
        request_path = directory / "request.json"
        if request_path.is_file():
            request = read_record(request_path)
            descriptor = request.get("request_blob")
            if isinstance(descriptor, dict) and isinstance(descriptor.get("sha256"), str):
                referenced.add(descriptor["sha256"])
        attempt_path = directory / "attempt.json"
        if attempt_path.is_file():
            attempt = read_record(attempt_path)
            for field in ("request_blob", "response_blob"):
                descriptor = attempt.get(field)
                if isinstance(descriptor, dict) and isinstance(descriptor.get("sha256"), str):
                    referenced.add(descriptor["sha256"])
    for record in records:
        descriptor = record["partial_blob"]
        if isinstance(descriptor, dict):
            referenced.add(descriptor["sha256"])
    return referenced


def _recover_orphan_blob(
    run_dir: Path,
    records: list[dict[str, Any]],
    partial_bytes: bytes | None,
) -> dict[str, Any] | None:
    inventory = _raw_blob_inventory(run_dir)
    referenced = _loosely_referenced_raw_hashes(run_dir, records)
    descriptor = None
    if partial_bytes is not None:
        descriptor = write_blob(run_dir, partial_bytes, disposition="partial")
        referenced.add(descriptor["sha256"])
    orphans = sorted(set(inventory) - referenced)
    if len(orphans) > 1:
        raise CaptureError("AMBIGUOUS_ORPHAN_BLOBS", "multiple unbound raw blobs require manual review")
    if orphans:
        orphan = orphans[0]
        if descriptor is not None and descriptor["sha256"] != orphan:
            raise CaptureError("ORPHAN_BLOB_CONFLICT", "supplied partial bytes differ from preserved orphan bytes")
        descriptor = write_blob(run_dir, inventory[orphan], disposition="partial")
    return descriptor


def _read_attempts(run_dir: Path, *, allow_partial: bool) -> list[dict[str, Any]]:
    run = _load_documents(run_dir)[0]
    attempts: list[dict[str, Any]] = []
    recovery_records = _read_recovery_records(run_dir)
    for number, directory in enumerate(attempt_directories(run_dir), start=1):
        matching_recovery = any(record["attempt_number"] == number for record in recovery_records)
        request_path = directory / "request.json"
        if request_path.is_file():
            request_record = read_record(request_path)
            require_exact_fields(request_record, REQUEST_FIELDS)
            expected_request = run["authorized_request_blob"]
            if (
                request_record["attempt_number"] != number
                or request_record["request_blob"] != expected_request
                or request_record["request_sha256"] != expected_request["sha256"]
                or request_record["byte_length"] != expected_request["byte_length"]
                or request_record["preserved_before_transport"] is not True
            ):
                raise CaptureError(
                    "REQUEST_PRESERVATION_MISMATCH",
                    "attempt request record differs from authorized bytes",
                    str(request_path),
                )
            read_blob(run_dir, request_record["request_blob"])
        elif not (allow_partial and matching_recovery):
            raise CaptureError(
                "PARTIAL_CAPTURE_DETECTED",
                "attempt directory exists without preserved request metadata",
                str(request_path),
            )
        record_path = directory / "attempt.json"
        if not record_path.is_file():
            if allow_partial and matching_recovery:
                attempts.append(
                    {
                        "schema_version": ATTEMPT_SCHEMA,
                        "execution_id": run["execution_id"],
                        "attempt_number": number,
                        "retry_reason": None,
                        "request_blob": run["authorized_request_blob"],
                        "response_blob": None,
                        "transport_status": "interrupted_uncommitted",
                        "complete": False,
                        "capture_started_at": None,
                        "capture_completed_at": None,
                        "allowlisted_transport_metadata": {},
                        "diagnostic": {
                            "classification": "derived_redaction",
                            "code": "PARTIAL_ATTEMPT_RECOVERED",
                        },
                        "warnings": ["PARTIAL_ATTEMPT"],
                        "provenance": {
                            "request": "capture_observed",
                            "response": "capture_observed",
                            "transport_metadata": "provider_declared_unverified",
                            "retry_reason": "operator_declared",
                        },
                        "attempt_digest": "",
                    }
                )
                attempts[-1]["attempt_digest"] = _attempt_digest(attempts[-1])
                continue
            raise CaptureError(
                "PARTIAL_CAPTURE_DETECTED",
                "attempt directory exists without an immutable terminal record",
                str(record_path),
            )
        attempt = read_record(record_path)
        require_exact_fields(attempt, ATTEMPT_FIELDS)
        if attempt["schema_version"] != ATTEMPT_SCHEMA or attempt["attempt_number"] != number:
            raise CaptureError("ATTEMPT_SEQUENCE_MISMATCH", "attempt record is inconsistent")
        if attempt["attempt_digest"] != _attempt_digest(attempt):
            raise CaptureError("ATTEMPT_DIGEST_MISMATCH", "attempt record was modified")
        read_blob(run_dir, attempt["request_blob"])
        if attempt["response_blob"] is not None:
            read_blob(run_dir, attempt["response_blob"])
        if attempt["complete"] is True:
            if attempt["transport_status"] != "completed" or attempt["response_blob"] is None:
                raise CaptureError("FALSE_CAPTURE_COMPLETION", "attempt completion is unsupported by evidence")
            if attempt["response_blob"]["capture_disposition"] != "complete":
                raise CaptureError("PARTIAL_RESPONSE_AS_COMPLETE", "partial response was marked complete")
        elif attempt["complete"] is not False:
            raise CaptureError("INVALID_ATTEMPT_COMPLETION", "attempt complete flag must be boolean")
        if attempt["execution_id"] != run["execution_id"]:
            raise CaptureError("ATTEMPT_EXECUTION_MISMATCH", "attempt execution ID changed")
        assert_secret_free(attempt["allowlisted_transport_metadata"])
        attempts.append(attempt)
    return attempts


def _verify_attempt_events(attempts: list[dict[str, Any]], ledger) -> None:
    request_events = [event for event in ledger.events if event["event_type"] == "request_preserved"]
    response_events = [event for event in ledger.events if event["event_type"] == "response_preserved"]
    captured_events = [
        event for event in ledger.events if event["to_state"] == "captured" and event["transition"]
    ]
    for attempt in attempts:
        number = attempt["attempt_number"]
        matching_requests = [event for event in request_events if event["payload"].get("attempt_number") == number]
        if attempt["transport_status"] != "interrupted_uncommitted":
            expected_request = {
                "attempt_number": number,
                "request_sha256": attempt["request_blob"]["sha256"],
            }
            if len(matching_requests) != 1 or matching_requests[0]["payload"] != expected_request:
                raise CaptureError("REQUEST_EVENT_MISMATCH", "request preservation event is missing or inconsistent")
        if attempt["complete"]:
            expected_response = {
                "attempt_number": number,
                "response_sha256": attempt["response_blob"]["sha256"],
            }
            matching_responses = [
                event for event in response_events if event["payload"].get("attempt_number") == number
            ]
            if len(matching_responses) != 1 or matching_responses[0]["payload"] != expected_response:
                raise CaptureError("RESPONSE_EVENT_MISMATCH", "response preservation event is missing or inconsistent")
            matching_capture = [event for event in captured_events if event["payload"].get("attempt_number") == number]
            if len(matching_capture) != 1 or matching_capture[0]["payload"] != {
                "attempt_number": number,
                "complete": True,
            }:
                raise CaptureError("CAPTURE_EVENT_MISMATCH", "capture completion event is missing or inconsistent")
    if len(captured_events) > 1:
        raise CaptureError("CAPTURE_EVENT_MISMATCH", "lifecycle contains multiple capture completions")


def _write_or_match_record(path: Path, value: dict[str, Any]) -> None:
    if path.is_file():
        if read_record(path) != value:
            raise CaptureError("INITIALIZATION_CONTENT_CONFLICT", "staged initialization content differs", str(path))
        return
    write_record(path, value)


def _ensure_initial_transition(
    run_dir: Path,
    to_state: str,
    *,
    observed_at: str,
    payload: dict[str, Any],
) -> None:
    order = ["draft", "validated", "locked", "execution_authorized"]
    ledger = verify_ledger(run_dir)
    current_index = order.index(ledger.state) if ledger.state in order else -1
    target_index = order.index(to_state)
    if current_index >= target_index:
        events = [event for event in ledger.events if event["to_state"] == to_state and event["transition"]]
        if len(events) != 1 or events[0]["payload"] != payload:
            raise CaptureError("INITIALIZATION_EVENT_CONFLICT", "staged initialization event differs")
        return
    if current_index != target_index - 1:
        raise CaptureError("INCOMPLETE_INITIALIZATION", "staged initialization has a lifecycle gap")
    append_transition(run_dir, to_state, observed_at=observed_at, payload=payload)


def initialize_run(
    *,
    campaign: dict[str, Any],
    lock: dict[str, Any],
    authorization: dict[str, Any],
    request_bytes: bytes,
    adapter: CaptureAdapter,
    repo_root: Path,
    output_root: Path,
    observed_at: str,
) -> Path:
    """Validate every precondition, reserve an ID, and bind execution authority."""
    validate_timestamp(observed_at, "$.observed_at")
    verify_governed_context(campaign, lock, repo_root)
    authorization_summary = validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=adapter,
    )
    execution_id = authorization["execution_id"]
    run_dir, final_run_dir = prepare_run_staging(output_root, campaign["campaign_id"], execution_id)
    request_blob = write_blob(
        run_dir,
        request_bytes,
        disposition="complete",
        media_type="application/octet-stream",
    )
    adapter_identity = validate_adapter_identity(adapter)
    run = {
        "schema_version": RUN_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "execution_id": execution_id,
        "benchmark_lock_digest": lock["lock_digest"],
        "benchmark_commit": lock["repository_commit"],
        "verifier_commit": lock["verifier_commit"],
        "release_identifier": lock["release_identifier"],
        "authorization_id": authorization_summary["authorization_id"],
        "authorization_digest": authorization_summary["authorization_digest"],
        "adapter": adapter_identity,
        "authorized_request_blob": request_blob,
        "prompt_reference": authorization["request"]["prompt_reference"],
        "case_reference": authorization["request"]["case_reference"],
        "retry_policy": authorization["retry_policy"],
        "ratification_status": "unratified",
        "authority_boundary": "execution_only_declared_artifact",
    }
    _write_or_match_record(run_dir / "run.json", run)
    _write_or_match_record(run_dir / "preregistration.json", campaign)
    _write_or_match_record(run_dir / "benchmark-lock.json", lock)
    _write_or_match_record(run_dir / "execution-authorization.json", authorization)
    _ensure_initial_transition(run_dir, "draft", observed_at=observed_at, payload={"campaign_id": campaign["campaign_id"]})
    _ensure_initial_transition(run_dir, "validated", observed_at=observed_at, payload={"validation": "passed"})
    _ensure_initial_transition(
        run_dir,
        "locked",
        observed_at=observed_at,
        payload={"benchmark_lock_digest": lock["lock_digest"]},
    )
    _ensure_initial_transition(
        run_dir,
        "execution_authorized",
        observed_at=observed_at,
        payload={
            "authorization_digest": authorization_summary["authorization_digest"],
            "scope": "execution_only",
            "ratification_status": "unratified",
        },
    )
    return publish_staged_run(run_dir, final_run_dir)


def _write_attempt(
    run_dir: Path,
    directory: Path,
    *,
    attempt_number: int,
    retry_reason: str | None,
    request_blob: dict[str, Any],
    response_blob: dict[str, Any] | None,
    transport_status: str,
    complete: bool,
    started_at: str,
    completed_at: str,
    metadata: dict[str, Any],
    diagnostic_code: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    run = _load_documents(run_dir)[0]
    attempt: dict[str, Any] = {
        "schema_version": ATTEMPT_SCHEMA,
        "execution_id": run["execution_id"],
        "attempt_number": attempt_number,
        "retry_reason": retry_reason,
        "request_blob": request_blob,
        "response_blob": response_blob,
        "transport_status": transport_status,
        "complete": complete,
        "capture_started_at": started_at,
        "capture_completed_at": completed_at,
        "allowlisted_transport_metadata": metadata,
        "diagnostic": (
            {"classification": "derived_redaction", "code": diagnostic_code}
            if diagnostic_code
            else None
        ),
        "warnings": sorted(set(warnings)),
        "provenance": {
            "request": "capture_observed",
            "response": "capture_observed",
            "transport_metadata": "provider_declared_unverified",
            "retry_reason": "operator_declared",
        },
    }
    attempt["attempt_digest"] = _attempt_digest(attempt)
    write_record(directory / "attempt.json", attempt)
    return attempt


def _retry_reason_for_current_state(run_dir: Path, attempt_number: int) -> str | None:
    if attempt_number == 1:
        return None
    ledger = verify_ledger(run_dir)
    for event in reversed(ledger.events):
        if event["event_type"] == "capture_resumed":
            reason = event["payload"].get("retry_reason")
            return reason if isinstance(reason, str) else None
    raise CaptureError("MISSING_RETRY_AUTHORIZATION", "successor attempt has no recovery retry reason")


def _reconcile_stored_attempt(
    run_dir: Path,
    attempt: dict[str, Any],
    *,
    observed_at: str,
) -> dict[str, Any] | None:
    """Commit a fully published attempt record without redispatching transport."""
    ledger = verify_ledger(run_dir)
    number = attempt["attempt_number"]
    terminal_events = [
        event
        for event in ledger.events
        if event["transition"]
        and event["to_state"] in {"captured", "interrupted"}
        and event["payload"].get("attempt_number") == number
    ]
    if terminal_events:
        return None
    if attempt["complete"]:
        response_events = [
            event
            for event in ledger.events
            if event["event_type"] == "response_preserved"
            and event["payload"].get("attempt_number") == number
        ]
        expected_response = {
            "attempt_number": number,
            "response_sha256": attempt["response_blob"]["sha256"],
        }
        if not response_events:
            append_occurrence(
                run_dir,
                "response_preserved",
                observed_at=observed_at,
                payload=expected_response,
            )
        elif len(response_events) != 1 or response_events[0]["payload"] != expected_response:
            raise CaptureError("RESPONSE_EVENT_MISMATCH", "stored response event is inconsistent")
        append_transition(
            run_dir,
            "captured",
            observed_at=observed_at,
            payload={"attempt_number": number, "complete": True},
        )
    else:
        append_occurrence(
            run_dir,
            "attempt_interrupted",
            observed_at=observed_at,
            payload={"attempt_number": number, "transport_status": attempt["transport_status"]},
        )
        append_transition(
            run_dir,
            "interrupted",
            observed_at=observed_at,
            payload={"attempt_number": number, "execution_outcome": "unknown"},
        )
    return attempt


def capture_attempt(
    run_dir: Path,
    *,
    request_bytes: bytes,
    adapter: CaptureAdapter,
    repo_root: Path,
    observed_at: str,
    attempt_number: int | None = None,
) -> dict[str, Any]:
    """Preserve request bytes before transport and one immutable terminal attempt."""
    validate_timestamp(observed_at, "$.observed_at")
    run, campaign, lock, authorization = _load_documents(run_dir)
    verify_governed_context(campaign, lock, repo_root)
    authorized_bytes = read_blob(run_dir, run["authorized_request_blob"])
    if request_bytes != authorized_bytes:
        raise CaptureError("REQUEST_BYTES_CHANGED", "outbound request differs from authorization")
    validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=adapter,
    )
    if validate_adapter_identity(adapter) != run["adapter"]:
        raise CaptureError("ADAPTER_SUBSTITUTION", "adapter identity differs from initialized run")
    ledger = verify_ledger(run_dir)
    if ledger.state == "execution_authorized":
        append_transition(run_dir, "capturing", observed_at=observed_at, payload={"attempt_number": 1})
    elif ledger.state != "capturing":
        raise CaptureError("CAPTURE_NOT_AUTHORIZED_STATE", "run is not ready to capture")
    existing = attempt_directories(run_dir)
    if existing:
        last_record = existing[-1] / "attempt.json"
        if not last_record.is_file():
            raise CaptureError(
                "PARTIAL_CAPTURE_DETECTED",
                "attempt directory has no terminal record; explicit recovery is required",
                str(last_record),
            )
        stored_attempts = _read_attempts(run_dir, allow_partial=False)
        reconciled = _reconcile_stored_attempt(
            run_dir,
            stored_attempts[-1],
            observed_at=observed_at,
        )
        if reconciled is not None:
            return reconciled
    expected_number = len(existing) + 1
    selected = expected_number if attempt_number is None else attempt_number
    if selected != expected_number:
        if 1 <= selected <= len(existing):
            record = existing[selected - 1] / "attempt.json"
            if record.is_file():
                prior = read_record(record)
                code = (
                    "ATTEMPT_ALREADY_EXISTS_IDENTICAL"
                    if prior.get("request_blob", {}).get("sha256") == sha256_bytes(request_bytes)
                    else "ATTEMPT_CONTENT_CONFLICT"
                )
                raise CaptureError(code, "attempt number already has immutable content")
        raise CaptureError("ATTEMPT_SEQUENCE_MISMATCH", "attempt number must be the next contiguous value")
    if selected > run["retry_policy"]["max_attempts"]:
        raise CaptureError("RETRY_BUDGET_EXHAUSTED", "attempt exceeds preregistered retry budget")
    retry_reason = _retry_reason_for_current_state(run_dir, selected)
    directory = create_attempt_dir(run_dir, selected)
    write_record(
        directory / "request.json",
        {
            "attempt_number": selected,
            "request_blob": run["authorized_request_blob"],
            "request_sha256": sha256_bytes(request_bytes),
            "byte_length": len(request_bytes),
            "preserved_before_transport": True,
        },
    )
    append_occurrence(
        run_dir,
        "request_preserved",
        observed_at=observed_at,
        payload={
            "attempt_number": selected,
            "request_sha256": sha256_bytes(request_bytes),
        },
    )
    locked_request = LockedCaptureRequest(
        campaign_id=run["campaign_id"],
        execution_id=run["execution_id"],
        attempt_number=selected,
        benchmark_lock_digest=run["benchmark_lock_digest"],
        request_bytes=request_bytes,
        prompt_reference=run["prompt_reference"],
        case_reference=run["case_reference"],
    )
    try:
        raw_result = adapter.transport(locked_request)
    except Exception as exc:  # adapter exceptions become redacted interruption evidence
        attempt = _write_attempt(
            run_dir,
            directory,
            attempt_number=selected,
            retry_reason=retry_reason,
            request_blob=run["authorized_request_blob"],
            response_blob=None,
            transport_status="adapter_error",
            complete=False,
            started_at=observed_at,
            completed_at=observed_at,
            metadata={},
            diagnostic_code=f"ADAPTER_EXCEPTION_{type(exc).__name__.upper()}",
            warnings=["EXECUTION_OUTCOME_UNKNOWN"],
        )
        append_occurrence(
            run_dir,
            "attempt_interrupted",
            observed_at=observed_at,
            payload={"attempt_number": selected, "diagnostic_code": attempt["diagnostic"]["code"]},
        )
        append_transition(
            run_dir,
            "interrupted",
            observed_at=observed_at,
            payload={"attempt_number": selected, "execution_outcome": "unknown"},
        )
        return attempt
    response_bytes = raw_result.response_bytes if hasattr(raw_result, "response_bytes") else None
    response_blob = None
    if isinstance(response_bytes, bytes):
        provisional_status = getattr(raw_result, "status", "invalid")
        response_blob = write_blob(
            run_dir,
            response_bytes,
            disposition="complete" if provisional_status == "completed" else "partial",
            media_type="application/octet-stream",
        )
    try:
        result = validate_transport_shape(raw_result)
    except CaptureError as exc:
        attempt = _write_attempt(
            run_dir,
            directory,
            attempt_number=selected,
            retry_reason=retry_reason,
            request_blob=run["authorized_request_blob"],
            response_blob=response_blob,
            transport_status="invalid_transport_result",
            complete=False,
            started_at=observed_at,
            completed_at=observed_at,
            metadata={},
            diagnostic_code=exc.code,
            warnings=["EXECUTION_OUTCOME_UNKNOWN"],
        )
        append_occurrence(run_dir, "attempt_interrupted", observed_at=observed_at, payload={"attempt_number": selected})
        append_transition(run_dir, "interrupted", observed_at=observed_at, payload={"attempt_number": selected})
        return attempt
    warnings: list[str] = []
    if response_bytes is not None and bytes_may_contain_secret(response_bytes):
        warnings.append("SENSITIVE_RAW_PAYLOAD_WITHHELD")
    try:
        metadata = sanitize_transport_metadata(result.metadata)
    except CaptureError as exc:
        attempt = _write_attempt(
            run_dir,
            directory,
            attempt_number=selected,
            retry_reason=retry_reason,
            request_blob=run["authorized_request_blob"],
            response_blob=response_blob,
            transport_status="metadata_rejected",
            complete=False,
            started_at=observed_at,
            completed_at=observed_at,
            metadata={},
            diagnostic_code=exc.code,
            warnings=warnings + ["UNTRUSTED_METADATA_REJECTED"],
        )
        append_occurrence(
            run_dir,
            "metadata_rejected",
            observed_at=observed_at,
            payload={"attempt_number": selected, "diagnostic_code": exc.code},
        )
        append_transition(run_dir, "interrupted", observed_at=observed_at, payload={"attempt_number": selected})
        return attempt
    provider_id = metadata.get("provider_request_id")
    if provider_id:
        for prior_dir in attempt_directories(run_dir)[:-1]:
            prior = read_record(prior_dir / "attempt.json")
            if prior["allowlisted_transport_metadata"].get("provider_request_id") == provider_id:
                warnings.append("PROVIDER_REQUEST_ID_REUSED")
                append_occurrence(
                    run_dir,
                    "provider_request_id_reused",
                    observed_at=observed_at,
                    payload={"attempt_number": selected},
                )
                break
    complete = result.status == "completed"
    attempt = _write_attempt(
        run_dir,
        directory,
        attempt_number=selected,
        retry_reason=retry_reason,
        request_blob=run["authorized_request_blob"],
        response_blob=response_blob,
        transport_status=result.status,
        complete=complete,
        started_at=observed_at,
        completed_at=observed_at,
        metadata=metadata,
        diagnostic_code=result.diagnostic_code,
        warnings=warnings,
    )
    if complete:
        append_occurrence(
            run_dir,
            "response_preserved",
            observed_at=observed_at,
            payload={
                "attempt_number": selected,
                "response_sha256": response_blob["sha256"] if response_blob else None,
            },
        )
        append_transition(
            run_dir,
            "captured",
            observed_at=observed_at,
            payload={"attempt_number": selected, "complete": True},
        )
    else:
        append_occurrence(
            run_dir,
            "attempt_interrupted",
            observed_at=observed_at,
            payload={"attempt_number": selected, "transport_status": result.status},
        )
        append_transition(
            run_dir,
            "interrupted",
            observed_at=observed_at,
            payload={"attempt_number": selected, "execution_outcome": "unknown"},
        )
    return attempt


def _exact_recovery_event(ledger, event_type: str, payload: dict[str, Any]) -> bool:
    matches = [
        event
        for event in ledger.events
        if event["event_type"] == event_type and event["payload"] == payload
    ]
    if len(matches) > 1:
        raise CaptureError("RECOVERY_EVENT_MISMATCH", f"{event_type} is duplicated")
    return bool(matches)


def _ensure_recovery_occurrence(
    run_dir: Path,
    event_type: str,
    *,
    observed_at: str,
    payload: dict[str, Any],
) -> None:
    ledger = verify_ledger(run_dir)
    if _exact_recovery_event(ledger, event_type, payload):
        return
    append_occurrence(run_dir, event_type, observed_at=observed_at, payload=payload)


def _ensure_recovery_transition(
    run_dir: Path,
    event_type: str,
    to_state: str,
    *,
    observed_at: str,
    payload: dict[str, Any],
) -> None:
    ledger = verify_ledger(run_dir)
    if _exact_recovery_event(ledger, event_type, payload):
        return
    event = append_transition(run_dir, to_state, observed_at=observed_at, payload=payload)
    if event["event_type"] != event_type:
        raise CaptureError("RECOVERY_EVENT_MISMATCH", "recovery transition type is inconsistent")


def _reconcile_recovery_record(run_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    digest = record["recovery_digest"]
    observed_at = record["observed_at"]
    if record["state_before"] == "capturing":
        _ensure_recovery_occurrence(
            run_dir,
            "attempt_interrupted",
            observed_at=observed_at,
            payload={"recovery_digest": digest},
        )
        _ensure_recovery_transition(
            run_dir,
            "capture_interrupted",
            "interrupted",
            observed_at=observed_at,
            payload={"execution_outcome": "unknown", "recovery_digest": digest},
        )
    elif record["state_before"] != "interrupted":
        raise CaptureError("RECOVERY_STATE_MISMATCH", "stored recovery predecessor state is invalid")
    _ensure_recovery_occurrence(
        run_dir,
        "recovery_declared",
        observed_at=observed_at,
        payload={
            "action": record["action"],
            "attempt_number": record["attempt_number"],
            "recovery_digest": digest,
        },
    )
    if record["partial_blob"] is not None:
        _ensure_recovery_occurrence(
            run_dir,
            "recovery_evidence_preserved",
            observed_at=observed_at,
            payload={
                "partial_sha256": record["partial_blob"]["sha256"],
                "recovery_digest": digest,
            },
        )
    if record["action"] == "resume":
        _ensure_recovery_transition(
            run_dir,
            "capture_resumed",
            "capturing",
            observed_at=observed_at,
            payload={"retry_reason": record["reason"], "recovery_digest": digest},
        )
    elif record["action"] == "abort":
        _ensure_recovery_transition(
            run_dir,
            "capture_aborted",
            "aborted",
            observed_at=observed_at,
            payload={"execution_outcome": "unknown", "recovery_digest": digest},
        )
    if not _recovery_record_complete(record, verify_ledger(run_dir)):
        raise CaptureError("INCOMPLETE_RECOVERY_RECORD", "recovery reconciliation did not reach a terminal binding")
    return record


def _recovery_request_matches(
    run_dir: Path,
    record: dict[str, Any],
    *,
    action: str,
    reason: str,
    partial_bytes: bytes | None,
) -> bool:
    if record["action"] != action or record["reason"] != reason:
        return False
    if partial_bytes is not None:
        if record["partial_blob"] is None or read_blob(run_dir, record["partial_blob"]) != partial_bytes:
            return False
    return True


def recover_run(
    run_dir: Path,
    *,
    action: str,
    reason: str,
    observed_at: str,
    partial_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Record interruption evidence, then explicitly resume or abort."""
    if action not in {"record_interruption", "resume", "abort"}:
        raise CaptureError("INVALID_RECOVERY_ACTION", "unknown recovery action")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 200:
        raise CaptureError("INVALID_RECOVERY_REASON", "recovery reason is required")
    assert_secret_free(reason, "$.reason")
    assert_no_governance_claims(reason, "$.reason")
    validate_timestamp(observed_at, "$.observed_at")
    run = _load_documents(run_dir)[0]
    ledger = verify_ledger(run_dir)
    records = _read_recovery_records(run_dir)
    incomplete = [record for record in records if not _recovery_record_complete(record, ledger)]
    if len(incomplete) > 1:
        raise CaptureError("AMBIGUOUS_RECOVERY_STATE", "multiple incomplete recovery records exist")
    if incomplete:
        record = incomplete[0]
        if not _recovery_request_matches(
            run_dir,
            record,
            action=action,
            reason=reason,
            partial_bytes=partial_bytes,
        ):
            raise CaptureError("RECOVERY_CONTENT_CONFLICT", "retry differs from immutable recovery record")
        return _reconcile_recovery_record(run_dir, record)
    attempt_number = len(attempt_directories(run_dir)) or None
    if records and _recovery_request_matches(
        run_dir,
        records[-1],
        action=action,
        reason=reason,
        partial_bytes=partial_bytes,
    ) and records[-1]["attempt_number"] == attempt_number:
        expected_state = {"resume": "capturing", "abort": "aborted", "record_interruption": "interrupted"}[action]
        if ledger.state == expected_state:
            return records[-1]
    if ledger.state not in {"capturing", "interrupted"}:
        raise CaptureError("RECOVERY_NOT_PERMITTED", "run is not capturing or interrupted")
    if action == "resume":
        if reason not in run["retry_policy"]["allowed_reasons"]:
            raise CaptureError("RETRY_POLICY_MISMATCH", "recovery reason is not preregistered")
        if len(attempt_directories(run_dir)) >= run["retry_policy"]["max_attempts"]:
            raise CaptureError("RETRY_BUDGET_EXHAUSTED", "no successor attempt is authorized")
    partial_blob = _recover_orphan_blob(run_dir, records, partial_bytes)
    record: dict[str, Any] = {
        "schema_version": "sfa_bench.campaign_capture.recovery.v1",
        "action": action,
        "reason": reason,
        "observed_at": observed_at,
        "state_before": ledger.state,
        "attempt_number": attempt_number,
        "partial_blob": partial_blob,
        "execution_outcome": "unknown",
        "provenance_class": "operator_declared",
    }
    record["recovery_digest"] = _recovery_digest(record)
    write_record(run_dir / "recovery" / f"{len(records):06d}.json", record)
    return _reconcile_recovery_record(run_dir, record)

def _capture_content(run: dict[str, Any], attempts: list[dict[str, Any]], state: str) -> dict[str, Any]:
    return {
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "benchmark_lock_digest": run["benchmark_lock_digest"],
        "verifier_commit": run["verifier_commit"],
        "authorization_digest": run["authorization_digest"],
        "adapter": run["adapter"],
        "capture_state": state,
        "attempts": [
            {
                "attempt_number": item["attempt_number"],
                "transport_status": item["transport_status"],
                "complete": item["complete"],
                "request_sha256": item["request_blob"]["sha256"],
                "response_sha256": (
                    item["response_blob"]["sha256"]
                    if isinstance(item["response_blob"], dict)
                    else None
                ),
                "retry_reason": item["retry_reason"],
                "warnings": item["warnings"],
            }
            for item in attempts
        ],
    }


def _raw_evidence_hashes(run_dir: Path, run: dict[str, Any], attempts: list[dict[str, Any]]) -> list[str]:
    hashes = {run["authorized_request_blob"]["sha256"]}
    for attempt in attempts:
        hashes.add(attempt["request_blob"]["sha256"])
        if isinstance(attempt["response_blob"], dict):
            hashes.add(attempt["response_blob"]["sha256"])
    for record in _read_recovery_records(run_dir):
        if isinstance(record["partial_blob"], dict):
            hashes.add(record["partial_blob"]["sha256"])
    return sorted(hashes)


def _verify_raw_blob_inventory(
    run_dir: Path,
    run: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> None:
    expected = set(_raw_evidence_hashes(run_dir, run, attempts))
    actual = set(_raw_blob_inventory(run_dir))
    if actual != expected:
        code = "UNBOUND_RAW_BLOB" if actual - expected else "MISSING_RAW_BLOB"
        raise CaptureError(code, "raw blob inventory differs from governed evidence descriptors")


def _capture_started_at(ledger) -> str | None:
    events = [event for event in ledger.events if event["event_type"] == "capture_started"]
    return events[0]["observed_at"] if events else None


def _validate_capture_manifest(
    run_dir: Path,
    *,
    run: dict[str, Any],
    attempts: list[dict[str, Any]],
    ledger,
    require_seal_event: bool,
) -> dict[str, Any]:
    manifest = read_record(run_dir / "capture-manifest.json")
    require_exact_fields(manifest, MANIFEST_FIELDS)
    if manifest["schema_version"] != CAPTURE_MANIFEST_SCHEMA:
        raise CaptureError("UNSUPPORTED_CAPTURE_MANIFEST", "unsupported capture manifest schema")
    if manifest["manifest_sha256"] != _manifest_digest(manifest):
        raise CaptureError("CAPTURE_MANIFEST_DIGEST_MISMATCH", "capture manifest was modified")
    bindings = {
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "benchmark_lock_digest": run["benchmark_lock_digest"],
        "benchmark_commit": run["benchmark_commit"],
        "verifier_commit": run["verifier_commit"],
        "release_identifier": run["release_identifier"],
        "authorization_digest": run["authorization_digest"],
        "adapter": run["adapter"],
        "prompt_reference": run["prompt_reference"],
        "case_reference": run["case_reference"],
        "attempts": [_attempt_summary(item) for item in attempts],
        "raw_evidence_hashes": _raw_evidence_hashes(run_dir, run, attempts),
        "capture_started_at": _capture_started_at(ledger),
        "warnings": sorted({warning for item in attempts for warning in item["warnings"]}),
        "provenance_classes": [
            "git_verified",
            "capture_observed",
            "provider_declared_unverified",
            "adapter_declared",
            "operator_declared",
        ],
        "ratification_status": "unratified",
    }
    for field, expected in bindings.items():
        if manifest[field] != expected:
            raise CaptureError("CAPTURE_MANIFEST_BINDING_MISMATCH", f"manifest {field} is inconsistent")
    if manifest["capture_state"] not in {"captured", "aborted"}:
        raise CaptureError("INVALID_CAPTURE_STATE", "manifest capture state is invalid")
    validate_timestamp(manifest["capture_completed_at"], "$.capture_completed_at")
    expected_content = sha256_value(_capture_content(run, attempts, manifest["capture_state"]))
    if manifest["capture_content_sha256"] != expected_content:
        raise CaptureError("CAPTURE_CONTENT_DIGEST_MISMATCH", "capture content identity changed")
    seal_events = [event for event in ledger.events if event["to_state"] == "sealed" and event["transition"]]
    if require_seal_event:
        if len(seal_events) != 1:
            raise CaptureError("CAPTURE_SEAL_MISMATCH", "lifecycle does not contain one capture seal")
        event = seal_events[0]
        if event["from_state"] != manifest["capture_state"]:
            raise CaptureError("CAPTURE_STATE_MISMATCH", "seal transition contradicts manifest state")
        if event["payload"] != {
            "manifest_sha256": manifest["manifest_sha256"],
            "capture_content_sha256": manifest["capture_content_sha256"],
        }:
            raise CaptureError("CAPTURE_SEAL_MISMATCH", "seal event does not bind the capture manifest")
        expected_preseal_root = event["previous_event_sha256"]
    else:
        if seal_events:
            raise CaptureError("CAPTURE_SEAL_MISMATCH", "unexpected seal event during reconciliation")
        expected_preseal_root = ledger.root_sha256
    if manifest["ledger_root_before_seal"] != expected_preseal_root:
        raise CaptureError("CAPTURE_LEDGER_ROOT_MISMATCH", "manifest binds the wrong pre-seal ledger root")
    assert_secret_free(manifest)
    return manifest


def seal_run(run_dir: Path, *, repo_root: Path, observed_at: str) -> dict[str, Any]:
    """Seal captured or explicitly aborted evidence without judging it."""
    validate_timestamp(observed_at, "$.observed_at")
    run, campaign, lock, authorization = _load_documents(run_dir)
    verify_governed_context(campaign, lock, repo_root)
    request_bytes = read_blob(run_dir, run["authorized_request_blob"])
    validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=_StoredAdapter(run["adapter"]),
    )
    ledger = verify_ledger(run_dir)
    target = run_dir / "capture-manifest.json"
    if ledger.state in {"sealed", "judged", "review_required"}:
        verify_run(run_dir, repo_root=repo_root)
        return read_record(target)
    if target.is_file() and ledger.state in {"captured", "aborted"}:
        attempts = _read_attempts(run_dir, allow_partial=ledger.state == "aborted")
        _verify_recovery_events(_read_recovery_records(run_dir), ledger)
        _verify_attempt_events(attempts, ledger)
        _verify_raw_blob_inventory(run_dir, run, attempts)
        manifest = _validate_capture_manifest(
            run_dir,
            run=run,
            attempts=attempts,
            ledger=ledger,
            require_seal_event=False,
        )
        append_transition(
            run_dir,
            "sealed",
            observed_at=manifest["capture_completed_at"],
            payload={
                "manifest_sha256": manifest["manifest_sha256"],
                "capture_content_sha256": manifest["capture_content_sha256"],
            },
        )
        return manifest
    if ledger.state not in {"captured", "aborted"}:
        raise CaptureError("CAPTURE_NOT_SEALABLE", "only captured or explicitly aborted evidence can seal")
    attempts = _read_attempts(run_dir, allow_partial=ledger.state == "aborted")
    _verify_recovery_events(_read_recovery_records(run_dir), ledger)
    _verify_attempt_events(attempts, ledger)
    _verify_raw_blob_inventory(run_dir, run, attempts)
    if ledger.state == "captured" and not any(item["complete"] for item in attempts):
        raise CaptureError("FALSE_CAPTURE_COMPLETION", "captured state has no complete attempt")
    warnings = sorted({warning for item in attempts for warning in item["warnings"]})
    summaries = [_attempt_summary(item) for item in attempts]
    raw_hashes = _raw_evidence_hashes(run_dir, run, attempts)
    content_hash = sha256_value(_capture_content(run, attempts, ledger.state))
    manifest: dict[str, Any] = {
        "schema_version": CAPTURE_MANIFEST_SCHEMA,
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "benchmark_lock_digest": run["benchmark_lock_digest"],
        "benchmark_commit": run["benchmark_commit"],
        "verifier_commit": run["verifier_commit"],
        "release_identifier": run["release_identifier"],
        "authorization_digest": run["authorization_digest"],
        "adapter": run["adapter"],
        "prompt_reference": run["prompt_reference"],
        "case_reference": run["case_reference"],
        "attempts": summaries,
        "raw_evidence_hashes": raw_hashes,
        "capture_state": ledger.state,
        "ledger_root_before_seal": ledger.root_sha256,
        "capture_started_at": _capture_started_at(ledger),
        "capture_completed_at": observed_at,
        "warnings": warnings,
        "provenance_classes": [
            "git_verified",
            "capture_observed",
            "provider_declared_unverified",
            "adapter_declared",
            "operator_declared",
        ],
        "ratification_status": "unratified",
        "capture_content_sha256": content_hash,
    }
    manifest["manifest_sha256"] = _manifest_digest(manifest)
    assert_secret_free(manifest)
    write_record(target, manifest)
    append_transition(
        run_dir,
        "sealed",
        observed_at=observed_at,
        payload={
            "manifest_sha256": manifest["manifest_sha256"],
            "capture_content_sha256": content_hash,
        },
    )
    return manifest


class _StoredAdapter:
    def __init__(self, identity: dict[str, str]) -> None:
        self.adapter_id = identity["adapter_id"]
        self.adapter_version = identity["adapter_version"]
        self.implementation_path = identity["implementation_path"]

    def transport(self, _request):  # pragma: no cover - identity-only verifier
        raise RuntimeError("stored adapter identity cannot transport")


def _verify_run_core(
    run_dir: Path,
    *,
    repo_root: Path,
    allow_uncommitted: str | None = None,
) -> dict[str, Any]:
    """Verify capture and lifecycle state without recursively verifying successors."""
    run, campaign, lock, authorization = _load_documents(run_dir)
    bindings = verify_governed_context(campaign, lock, repo_root)
    expected_run = {
        "campaign_id": campaign["campaign_id"],
        "benchmark_lock_digest": lock["lock_digest"],
        "benchmark_commit": lock["repository_commit"],
        "verifier_commit": lock["verifier_commit"],
        "release_identifier": lock["release_identifier"],
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["authorization_digest"],
        "ratification_status": "unratified",
        "authority_boundary": "execution_only_declared_artifact",
    }
    for field, expected in expected_run.items():
        if run[field] != expected:
            raise CaptureError("RUN_BINDING_MISMATCH", f"run {field} does not match governed artifacts")
    request_bytes = read_blob(run_dir, run["authorized_request_blob"])
    validate_authorization(
        authorization,
        campaign=campaign,
        lock=lock,
        request_bytes=request_bytes,
        adapter=_StoredAdapter(run["adapter"]),
    )
    require_bound_reference(lock, run["prompt_reference"], "$.prompt_reference")
    require_bound_reference(lock, run["case_reference"], "$.case_reference")
    ledger = verify_ledger(run_dir)
    manifest_path = run_dir / "capture-manifest.json"
    allow_partial_attempts = ledger.state in {"aborted", "interrupted", "capturing"}
    if manifest_path.is_file() and ledger.state in {"sealed", "judged", "review_required"}:
        allow_partial_attempts = read_record(manifest_path).get("capture_state") == "aborted"
    attempts = _read_attempts(run_dir, allow_partial=allow_partial_attempts)
    _verify_recovery_events(_read_recovery_records(run_dir), ledger)
    _verify_attempt_events(attempts, ledger)
    _verify_raw_blob_inventory(run_dir, run, attempts)
    if ledger.state in {None, "draft", "validated", "locked"}:
        raise CaptureError("INCOMPLETE_INITIALIZATION", "run initialization has no execution authorization state")
    if ledger.state == "capturing":
        raise CaptureError("UNRESOLVED_CAPTURE", "capturing state has no terminal capture event")
    verification_status = "recovery_required" if ledger.state == "interrupted" else "verified"
    manifest_path = run_dir / "capture-manifest.json"
    judgment_path = run_dir / "judgment.json"
    bundle_path = run_dir / "review-bundle.json"
    manifest_hash = None
    warnings = sorted({warning for item in attempts for warning in item["warnings"]})
    if ledger.state == "captured" and not any(item["complete"] for item in attempts):
        raise CaptureError("FALSE_CAPTURE_COMPLETION", "captured state has no complete attempt")
    if manifest_path.is_file():
        committed = ledger.state in {"sealed", "judged", "review_required"}
        if not committed and allow_uncommitted != "manifest":
            raise CaptureError("UNCOMMITTED_CAPTURE_MANIFEST", "capture manifest has no seal transition")
        manifest = _validate_capture_manifest(
            run_dir,
            run=run,
            attempts=attempts,
            ledger=ledger,
            require_seal_event=committed,
        )
        manifest_hash = manifest["manifest_sha256"]
        warnings = sorted(set(warnings) | set(manifest["warnings"]))
    elif ledger.state in {"sealed", "judged", "review_required"}:
        raise CaptureError("MISSING_CAPTURE_MANIFEST", "sealed lifecycle has no capture manifest")
    if judgment_path.is_file() and ledger.state == "sealed" and allow_uncommitted != "judgment":
        raise CaptureError("UNCOMMITTED_JUDGMENT", "judgment artifact has no judged transition")
    if ledger.state == "judged" and not judgment_path.is_file():
        raise CaptureError("MISSING_JUDGMENT", "judged lifecycle has no judgment artifact")
    if bundle_path.is_file() and ledger.state in {"sealed", "judged"} and allow_uncommitted != "bundle":
        raise CaptureError("UNCOMMITTED_REVIEW_BUNDLE", "review bundle has no review transition")
    if ledger.state == "review_required" and not bundle_path.is_file():
        raise CaptureError("MISSING_REVIEW_BUNDLE", "review lifecycle has no review bundle")
    report: dict[str, Any] = {
        "schema_version": INTEGRITY_REPORT_SCHEMA,
        "status": verification_status,
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "lifecycle_state": ledger.state,
        "ledger_events": len(ledger.events),
        "ledger_root": ledger.root_sha256,
        "attempt_count": len(attempts),
        "complete_attempts": sum(1 for item in attempts if item["complete"]),
        "capture_manifest_sha256": manifest_hash,
        "benchmark_lock_digest": run["benchmark_lock_digest"],
        "bound_implementation_files": len(bindings),
        "warnings": warnings,
        "ratification_status": "unratified",
    }
    report["integrity_report_sha256"] = sha256_value(report)
    return report


def verify_run(run_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    """Verify the complete stored capture without provider or network access."""
    report = _verify_run_core(run_dir, repo_root=repo_root)
    if report["lifecycle_state"] == "judged":
        from .judgment import _validate_judgment_artifact

        _validate_judgment_artifact(run_dir, repo_root=repo_root, integrity=report, require_event=True)
    elif report["lifecycle_state"] == "review_required":
        from .review import _validate_review_bundle_artifact

        _validate_review_bundle_artifact(
            run_dir,
            repo_root=repo_root,
            integrity=report,
            require_event=True,
        )
    return report
