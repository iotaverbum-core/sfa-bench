"""Crash-safe append-only storage for campaign capture evidence."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

from .canonical import (
    CaptureError,
    ensure_no_reparse_ancestors,
    require_exact_fields,
    safe_child,
    sha256_bytes,
    strict_json_file,
    validate_safe_id,
    write_exclusive_bytes,
    write_exclusive_json,
)


BLOB_DESCRIPTOR_SCHEMA = "sfa_bench.campaign_capture.raw_blob.v1"
BLOB_DESCRIPTOR_FIELDS = frozenset(
    {
        "schema_version",
        "representation",
        "path",
        "sha256",
        "byte_length",
        "media_type",
        "capture_disposition",
        "visibility",
        "provenance_class",
    }
)


def reserve_run(output_root: Path, campaign_id: str, execution_id: str) -> Path:
    validate_safe_id(campaign_id, "$.campaign_id")
    validate_safe_id(execution_id, "$.execution_id")
    output_root.mkdir(parents=True, exist_ok=True)
    ensure_no_reparse_ancestors(output_root, output_root)
    campaign_root = safe_child(output_root, campaign_id)
    campaign_root.mkdir(exist_ok=True)
    ensure_no_reparse_ancestors(output_root, campaign_root)
    run_dir = safe_child(output_root, campaign_id, execution_id)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise CaptureError(
            "DUPLICATE_EXECUTION_ID",
            "execution ID already has an immutable run directory",
            str(run_dir),
        ) from exc
    for relative in (
        Path("ledger/events"),
        Path("attempts"),
        Path("private/raw/blobs/sha256"),
        Path("recovery"),
    ):
        target = run_dir / relative
        target.mkdir(parents=True)
        ensure_no_reparse_ancestors(run_dir, target)
    return run_dir


def prepare_run_staging(
    output_root: Path,
    campaign_id: str,
    execution_id: str,
) -> tuple[Path, Path]:
    """Prepare a deterministic private staging directory for atomic initialization."""
    validate_safe_id(campaign_id, "$.campaign_id")
    validate_safe_id(execution_id, "$.execution_id")
    output_root.mkdir(parents=True, exist_ok=True)
    ensure_no_reparse_ancestors(output_root, output_root)
    campaign_root = safe_child(output_root, campaign_id)
    campaign_root.mkdir(exist_ok=True)
    ensure_no_reparse_ancestors(output_root, campaign_root)
    final = safe_child(output_root, campaign_id, execution_id)
    if final.exists():
        raise CaptureError(
            "DUPLICATE_EXECUTION_ID",
            "execution ID already has an immutable run directory",
            str(final),
        )
    identity = f"{campaign_id}/{execution_id}".encode("utf-8")
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".capture-init-{sha256_bytes(identity)[:16]}-",
            dir=campaign_root,
        )
    )
    ensure_no_reparse_ancestors(output_root, staging)
    for relative in (
        Path("ledger/events"),
        Path("attempts"),
        Path("private/raw/blobs/sha256"),
        Path("recovery"),
    ):
        target = staging / relative
        target.mkdir(parents=True, exist_ok=True)
        ensure_no_reparse_ancestors(staging, target)
    return staging, final


def publish_staged_run(staging: Path, final: Path) -> Path:
    """Atomically expose a fully initialized run without replacing any target."""
    if staging.parent != final.parent:
        raise CaptureError("PATH_ESCAPE", "staging and final run must share a parent")
    ensure_no_reparse_ancestors(staging.parent, staging)
    ensure_no_reparse_ancestors(final.parent, final)
    try:
        os.rename(staging, final)
    except FileExistsError as exc:
        raise CaptureError("DUPLICATE_EXECUTION_ID", "execution ID was concurrently published", str(final)) from exc
    except OSError as exc:
        if final.exists():
            raise CaptureError("DUPLICATE_EXECUTION_ID", "execution ID was concurrently published", str(final)) from exc
        raise CaptureError("ATOMIC_RUN_PUBLICATION_FAILED", "initialized run could not be published", str(final)) from exc
    return final


def write_blob(
    run_dir: Path,
    data: bytes,
    *,
    disposition: str,
    media_type: str = "application/octet-stream",
) -> dict[str, Any]:
    if disposition not in {"complete", "partial"}:
        raise CaptureError("INVALID_BLOB_DISPOSITION", "blob disposition is invalid")
    if not isinstance(media_type, str) or not media_type or len(media_type) > 128:
        raise CaptureError("INVALID_MEDIA_TYPE", "media type is invalid")
    digest = sha256_bytes(data)
    path = run_dir / "private" / "raw" / "blobs" / "sha256" / f"{digest}.bin"
    ensure_no_reparse_ancestors(run_dir, path)
    if path.exists():
        if path.read_bytes() != data:
            raise CaptureError("CONTENT_ADDRESS_COLLISION", "existing blob bytes differ", str(path))
    else:
        write_exclusive_bytes(path, data)
    return {
        "schema_version": BLOB_DESCRIPTOR_SCHEMA,
        "representation": "raw_file",
        "path": path.relative_to(run_dir).as_posix(),
        "sha256": digest,
        "byte_length": len(data),
        "media_type": media_type,
        "capture_disposition": disposition,
        "visibility": "private_raw",
        "provenance_class": "capture_observed",
    }


def read_blob(run_dir: Path, descriptor: Any) -> bytes:
    if not isinstance(descriptor, dict):
        raise CaptureError("INVALID_BLOB_DESCRIPTOR", "blob descriptor must be an object")
    require_exact_fields(descriptor, BLOB_DESCRIPTOR_FIELDS)
    if descriptor["schema_version"] != BLOB_DESCRIPTOR_SCHEMA:
        raise CaptureError("UNSUPPORTED_BLOB_SCHEMA", "unsupported blob descriptor schema")
    if descriptor["representation"] != "raw_file":
        raise CaptureError("INVALID_BLOB_REPRESENTATION", "unsupported blob representation")
    if descriptor["visibility"] != "private_raw":
        raise CaptureError("INVALID_BLOB_VISIBILITY", "raw blobs must remain private")
    if descriptor["provenance_class"] != "capture_observed":
        raise CaptureError("INVALID_PROVENANCE_CLASS", "raw blob provenance is invalid")
    relative = descriptor["path"]
    expected = f"private/raw/blobs/sha256/{descriptor['sha256']}.bin"
    if relative != expected:
        raise CaptureError("BLOB_PATH_MISMATCH", "blob path does not match its digest")
    path = run_dir.joinpath(*relative.split("/"))
    ensure_no_reparse_ancestors(run_dir, path)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise CaptureError("MISSING_RAW_BLOB", "referenced raw blob is missing", str(path)) from exc
    if sha256_bytes(data) != descriptor["sha256"] or len(data) != descriptor["byte_length"]:
        raise CaptureError("RAW_BLOB_DIGEST_MISMATCH", "raw blob bytes were modified", str(path))
    return data


def create_attempt_dir(run_dir: Path, attempt_number: int) -> Path:
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
        raise CaptureError("INVALID_ATTEMPT_NUMBER", "attempt number must be a positive integer")
    name = f"{attempt_number:06d}"
    target = safe_child(run_dir / "attempts", name)
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise CaptureError("DUPLICATE_ATTEMPT", "attempt directory already exists", str(target)) from exc
    return target


def attempt_directories(run_dir: Path) -> list[Path]:
    root = run_dir / "attempts"
    paths = sorted(root.iterdir(), key=lambda path: path.name) if root.is_dir() else []
    for index, path in enumerate(paths, start=1):
        expected = f"{index:06d}"
        if not path.is_dir() or path.name != expected:
            raise CaptureError("ATTEMPT_SEQUENCE_MISMATCH", "attempt directories are not contiguous", str(path))
        ensure_no_reparse_ancestors(run_dir, path)
    return paths


def write_record(path: Path, value: Any) -> Path:
    return write_exclusive_json(path, value)


def read_record(path: Path) -> dict[str, Any]:
    ensure_no_reparse_ancestors(path.parent, path)
    value = strict_json_file(path, require_canonical=True)
    if not isinstance(value, dict):
        raise CaptureError("MALFORMED_STORED_RECORD", "stored record must be an object", str(path))
    return value
