"""Integrity-first offline judgment of sealed campaign evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sfa_bench.frontier_delta import candidate_adapter

from .canonical import (
    CaptureError,
    assert_secret_free,
    require_exact_fields,
    sha256_bytes,
    sha256_value,
    strict_json_file,
    validate_repo_relative_path,
    validate_timestamp,
)
from .context import lock_binding_map, require_bound_reference
from .lifecycle import append_transition, verify_ledger
from .run import verify_run
from .storage import read_blob, read_record, write_record


JUDGMENT_SCHEMA = "sfa_bench.campaign_capture.judgment.v1"
JUDGMENT_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "execution_id",
        "benchmark_lock_digest",
        "verifier_commit",
        "capture_manifest_sha256",
        "response_blob_sha256",
        "task_reference",
        "task_sha256",
        "candidate_decode_status",
        "candidate_validity",
        "deterministic_result",
        "judgment_input_projection",
        "judged_at",
        "provenance_class",
        "ratification_status",
        "judgment_content_sha256",
        "judgment_sha256",
    }
)


def _digest(artifact: dict[str, Any]) -> str:
    content = dict(artifact)
    content.pop("judgment_sha256", None)
    return sha256_value(content)


def _content_digest(artifact: dict[str, Any]) -> str:
    return sha256_value(
        {
            key: value
            for key, value in artifact.items()
            if key not in {"judged_at", "judgment_content_sha256", "judgment_sha256"}
        }
    )


def _complete_attempt(run_dir: Path) -> dict[str, Any]:
    directories = sorted((run_dir / "attempts").iterdir(), key=lambda path: path.name)
    complete: list[dict[str, Any]] = []
    for directory in directories:
        attempt = read_record(directory / "attempt.json")
        if attempt.get("complete") is True:
            complete.append(attempt)
    if not complete:
        raise CaptureError("NO_COMPLETE_CAPTURE", "sealed evidence has no complete response")
    return complete[-1]


def judge_run(
    run_dir: Path,
    *,
    repo_root: Path,
    task_reference: str,
    observed_at: str,
) -> dict[str, Any]:
    """Verify all provenance, then invoke the existing fixed candidate path."""
    validate_timestamp(observed_at, "$.observed_at")
    integrity = verify_run(run_dir, repo_root=repo_root)
    if integrity["lifecycle_state"] != "sealed":
        raise CaptureError("JUDGMENT_REQUIRES_SEALED_CAPTURE", "run must be sealed and unjudged")
    run = read_record(run_dir / "run.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    if manifest["capture_state"] != "captured":
        raise CaptureError("ABORTED_CAPTURE_NOT_JUDGABLE", "aborted evidence cannot be judged")
    relative = validate_repo_relative_path(task_reference, "$.task_reference")
    if relative != run["case_reference"]:
        raise CaptureError("TASK_REFERENCE_SUBSTITUTION", "judgment task differs from authorization")
    _, bound_digest = require_bound_reference(lock, relative, "$.task_reference")
    task_path = repo_root.joinpath(*relative.split("/"))
    if not task_path.is_file() or sha256_bytes(task_path.read_bytes()) != bound_digest:
        raise CaptureError("TASK_BINDING_MISMATCH", "task bytes do not match benchmark lock")
    task = strict_json_file(task_path)
    if not isinstance(task, dict):
        raise CaptureError("MALFORMED_TASK", "judgment task must be an object")
    attempt = _complete_attempt(run_dir)
    response_bytes = read_blob(run_dir, attempt["response_blob"])
    try:
        response_text = response_bytes.decode("utf-8")
        decode_status = "utf8"
    except UnicodeDecodeError:
        response_text = "\x00"
        decode_status = "binary_non_utf8"
    deterministic_result = candidate_adapter.score_response(task, response_text)
    validity = deterministic_result.get("parse_notes", {}).get("candidate_validity")
    if not isinstance(validity, str):
        failures = deterministic_result.get("detected_failure_modes", [])
        validity = failures[0] if failures else "valid_object"
    artifact: dict[str, Any] = {
        "schema_version": JUDGMENT_SCHEMA,
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "benchmark_lock_digest": run["benchmark_lock_digest"],
        "verifier_commit": run["verifier_commit"],
        "capture_manifest_sha256": manifest["manifest_sha256"],
        "response_blob_sha256": attempt["response_blob"]["sha256"],
        "task_reference": relative,
        "task_sha256": bound_digest,
        "candidate_decode_status": decode_status,
        "candidate_validity": validity,
        "deterministic_result": deterministic_result,
        "judgment_input_projection": {
            "provider_metadata": {},
            "adapter_metadata": {},
            "authorization_metadata": {},
            "retry_metadata": {},
        },
        "judged_at": observed_at,
        "provenance_class": "derived_deterministic",
        "ratification_status": "unratified",
    }
    artifact["judgment_content_sha256"] = _content_digest(artifact)
    artifact["judgment_sha256"] = _digest(artifact)
    assert_secret_free(artifact)
    target = run_dir / "judgment.json"
    if target.exists():
        existing = read_record(target)
        if existing != artifact:
            raise CaptureError("JUDGMENT_NO_OVERWRITE", "different judgment artifact already exists")
    else:
        write_record(target, artifact)
    append_transition(
        run_dir,
        "judged",
        observed_at=observed_at,
        payload={
            "judgment_sha256": artifact["judgment_sha256"],
            "verifier_commit": run["verifier_commit"],
        },
    )
    return artifact


def verify_judgment(run_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    integrity = verify_run(run_dir, repo_root=repo_root)
    if integrity["lifecycle_state"] not in {"judged", "review_required"}:
        raise CaptureError("MISSING_JUDGMENT_STATE", "lifecycle does not contain a sealed judgment")
    artifact = read_record(run_dir / "judgment.json")
    require_exact_fields(artifact, JUDGMENT_FIELDS)
    if artifact["schema_version"] != JUDGMENT_SCHEMA:
        raise CaptureError("UNSUPPORTED_JUDGMENT_SCHEMA", "unsupported judgment schema")
    if artifact["judgment_content_sha256"] != _content_digest(artifact):
        raise CaptureError("JUDGMENT_CONTENT_MISMATCH", "judgment content identity changed")
    if artifact["judgment_sha256"] != _digest(artifact):
        raise CaptureError("JUDGMENT_DIGEST_MISMATCH", "judgment artifact was modified")
    ledger = verify_ledger(run_dir)
    events = [event for event in ledger.events if event["to_state"] == "judged" and event["transition"]]
    if len(events) != 1 or events[0]["payload"].get("judgment_sha256") != artifact["judgment_sha256"]:
        raise CaptureError("JUDGMENT_SEAL_MISMATCH", "lifecycle does not bind judgment artifact")
    run = read_record(run_dir / "run.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    if (
        artifact["campaign_id"] != run["campaign_id"]
        or artifact["execution_id"] != run["execution_id"]
        or artifact["benchmark_lock_digest"] != lock["lock_digest"]
        or artifact["verifier_commit"] != lock["verifier_commit"]
        or artifact["capture_manifest_sha256"] != manifest["manifest_sha256"]
    ):
        raise CaptureError("JUDGMENT_BINDING_MISMATCH", "judgment binds different governed evidence")
    bindings = lock_binding_map(lock)
    if bindings.get(artifact["task_reference"]) != artifact["task_sha256"]:
        raise CaptureError("JUDGMENT_TASK_BINDING_MISMATCH", "judgment task is not lock-bound")
    assert_secret_free(artifact)
    return artifact
