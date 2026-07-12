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
    assert_secret_free,
    bytes_may_contain_secret,
    canonical_bytes,
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
    read_blob,
    read_record,
    reserve_run,
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


def _read_attempts(run_dir: Path, *, allow_partial: bool) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    recovery_records = list((run_dir / "recovery").glob("*.json"))
    for number, directory in enumerate(attempt_directories(run_dir), start=1):
        record_path = directory / "attempt.json"
        if not record_path.is_file():
            if allow_partial and recovery_records:
                attempts.append(
                    {
                        "schema_version": ATTEMPT_SCHEMA,
                        "execution_id": _load_documents(run_dir)[0]["execution_id"],
                        "attempt_number": number,
                        "retry_reason": None,
                        "request_blob": _load_documents(run_dir)[0]["authorized_request_blob"],
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
        assert_secret_free(attempt["allowlisted_transport_metadata"])
        attempts.append(attempt)
    return attempts


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
    run_dir = reserve_run(output_root, campaign["campaign_id"], execution_id)
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
    write_record(run_dir / "run.json", run)
    write_record(run_dir / "preregistration.json", campaign)
    write_record(run_dir / "benchmark-lock.json", lock)
    write_record(run_dir / "execution-authorization.json", authorization)
    append_transition(run_dir, "draft", observed_at=observed_at, payload={"campaign_id": campaign["campaign_id"]})
    append_transition(run_dir, "validated", observed_at=observed_at, payload={"validation": "passed"})
    append_transition(
        run_dir,
        "locked",
        observed_at=observed_at,
        payload={"benchmark_lock_digest": lock["lock_digest"]},
    )
    append_transition(
        run_dir,
        "execution_authorized",
        observed_at=observed_at,
        payload={
            "authorization_digest": authorization_summary["authorization_digest"],
            "scope": "execution_only",
            "ratification_status": "unratified",
        },
    )
    return run_dir


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
    validate_timestamp(observed_at, "$.observed_at")
    run = _load_documents(run_dir)[0]
    ledger = verify_ledger(run_dir)
    if ledger.state not in {"capturing", "interrupted"}:
        raise CaptureError("RECOVERY_NOT_PERMITTED", "run is not capturing or interrupted")
    if action == "resume":
        if reason not in run["retry_policy"]["allowed_reasons"]:
            raise CaptureError("RETRY_POLICY_MISMATCH", "recovery reason is not preregistered")
        if len(attempt_directories(run_dir)) >= run["retry_policy"]["max_attempts"]:
            raise CaptureError("RETRY_BUDGET_EXHAUSTED", "no successor attempt is authorized")
    record: dict[str, Any] = {
        "schema_version": "sfa_bench.campaign_capture.recovery.v1",
        "action": action,
        "reason": reason,
        "observed_at": observed_at,
        "state_before": ledger.state,
        "partial_blob": None,
        "execution_outcome": "unknown",
        "provenance_class": "operator_declared",
    }
    if partial_bytes is not None:
        record["partial_blob"] = write_blob(run_dir, partial_bytes, disposition="partial")
    existing = sorted((run_dir / "recovery").glob("*.json"))
    record["recovery_digest"] = sha256_value(record)
    write_record(run_dir / "recovery" / f"{len(existing):06d}.json", record)
    if ledger.state == "capturing":
        append_occurrence(
            run_dir,
            "attempt_interrupted",
            observed_at=observed_at,
            payload={"recovery_digest": record["recovery_digest"]},
        )
        append_transition(
            run_dir,
            "interrupted",
            observed_at=observed_at,
            payload={"execution_outcome": "unknown", "recovery_digest": record["recovery_digest"]},
        )
    elif ledger.state != "interrupted":
        raise CaptureError("RECOVERY_NOT_PERMITTED", "run is not capturing or interrupted")
    if record["partial_blob"] is not None:
        append_occurrence(
            run_dir,
            "recovery_evidence_preserved",
            observed_at=observed_at,
            payload={"partial_sha256": record["partial_blob"]["sha256"]},
        )
    if action == "resume":
        if reason not in run["retry_policy"]["allowed_reasons"]:
            raise CaptureError("RETRY_POLICY_MISMATCH", "recovery reason is not preregistered")
        if len(attempt_directories(run_dir)) >= run["retry_policy"]["max_attempts"]:
            raise CaptureError("RETRY_BUDGET_EXHAUSTED", "no successor attempt is authorized")
        append_occurrence(
            run_dir,
            "recovery_declared",
            observed_at=observed_at,
            payload={"action": "resume", "retry_reason": reason},
        )
        append_transition(
            run_dir,
            "capturing",
            observed_at=observed_at,
            payload={"retry_reason": reason},
        )
    elif action == "abort":
        append_transition(
            run_dir,
            "aborted",
            observed_at=observed_at,
            payload={"reason": reason, "execution_outcome": "unknown"},
        )
    return record


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
    if ledger.state not in {"captured", "aborted"}:
        raise CaptureError("CAPTURE_NOT_SEALABLE", "only captured or explicitly aborted evidence can seal")
    attempts = _read_attempts(run_dir, allow_partial=ledger.state == "aborted")
    if ledger.state == "captured" and not any(item["complete"] for item in attempts):
        raise CaptureError("FALSE_CAPTURE_COMPLETION", "captured state has no complete attempt")
    warnings = sorted({warning for item in attempts for warning in item["warnings"]})
    summaries = [_attempt_summary(item) for item in attempts]
    raw_hashes = sorted(
        {
            item["request_blob"]["sha256"]
            for item in attempts
        }
        | {
            item["response_blob"]["sha256"]
            for item in attempts
            if isinstance(item["response_blob"], dict)
        }
    )
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
        "capture_started_at": ledger.events[4]["observed_at"] if len(ledger.events) > 4 else None,
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
    write_record(run_dir / "capture-manifest.json", manifest)
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


def verify_run(run_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    """Verify the complete stored capture without provider or network access."""
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
    attempts = _read_attempts(run_dir, allow_partial=ledger.state in {"aborted", "interrupted", "capturing"})
    manifest_path = run_dir / "capture-manifest.json"
    manifest_hash = None
    warnings = sorted({warning for item in attempts for warning in item["warnings"]})
    if manifest_path.is_file():
        manifest = read_record(manifest_path)
        require_exact_fields(manifest, MANIFEST_FIELDS)
        if manifest["schema_version"] != CAPTURE_MANIFEST_SCHEMA:
            raise CaptureError("UNSUPPORTED_CAPTURE_MANIFEST", "unsupported capture manifest schema")
        if manifest["manifest_sha256"] != _manifest_digest(manifest):
            raise CaptureError("CAPTURE_MANIFEST_DIGEST_MISMATCH", "capture manifest was modified")
        manifest_hash = manifest["manifest_sha256"]
        seal_events = [event for event in ledger.events if event["to_state"] == "sealed" and event["transition"]]
        if len(seal_events) != 1 or seal_events[0]["payload"].get("manifest_sha256") != manifest_hash:
            raise CaptureError("CAPTURE_SEAL_MISMATCH", "ledger does not bind the capture manifest")
        if manifest["ledger_root_before_seal"] != seal_events[0]["previous_event_sha256"]:
            raise CaptureError("CAPTURE_LEDGER_ROOT_MISMATCH", "manifest binds the wrong pre-seal ledger root")
        expected_content = sha256_value(_capture_content(run, attempts, manifest["capture_state"]))
        if manifest["capture_content_sha256"] != expected_content:
            raise CaptureError("CAPTURE_CONTENT_DIGEST_MISMATCH", "capture content identity changed")
        warnings = sorted(set(warnings) | set(manifest["warnings"]))
    elif ledger.state in {"sealed", "judged", "review_required"}:
        raise CaptureError("MISSING_CAPTURE_MANIFEST", "sealed lifecycle has no capture manifest")
    report: dict[str, Any] = {
        "schema_version": INTEGRITY_REPORT_SCHEMA,
        "status": "verified",
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
