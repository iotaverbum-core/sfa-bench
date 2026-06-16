"""Candidate provenance records for SFA-Agent attempts.

Provenance is deliberately outside the verifier boundary. It can attest where a
candidate came from and whether local run files still match their recorded
hashes, but it is never passed into `verifier.verify()`.
"""
from datetime import datetime, timezone
import json
import os
from typing import Any

from .hashing import sha256_hex
from .model_adapter import CandidateOutput


def build_provenance(
    adapter_output: CandidateOutput,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    *,
    warning_used: bool,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a provenance record for one attempt."""
    return {
        "adapter_name": adapter_output.adapter_name,
        "adapter_kind": adapter_output.adapter_kind,
        "adapter_version": adapter_output.adapter_version,
        "source_type": adapter_output.source_type,
        "source_path": adapter_output.source_path,
        "source_hash": sha256_hex(adapter_output.raw_source),
        "normalized_candidate_hash": sha256_hex(adapter_output.candidate),
        "input_hash": sha256_hex(input_obj),
        "evidence_hash": sha256_hex(evidence_obj),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "warning_used": bool(warning_used),
        "verifier_blind_to_provenance": True,
    }


def verify_provenance_hashes(
    provenance: dict[str, Any],
    *,
    raw_source: Any | None = None,
    normalized_candidate: dict[str, Any] | None = None,
    input_obj: dict[str, Any] | None = None,
    evidence_obj: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """Compare current objects to the hashes stored in provenance."""
    checks = {}
    if raw_source is not None:
        checks["source_hash"] = provenance.get("source_hash") == sha256_hex(raw_source)
    if normalized_candidate is not None:
        checks["normalized_candidate_hash"] = provenance.get("normalized_candidate_hash") == sha256_hex(normalized_candidate)
    if input_obj is not None:
        checks["input_hash"] = provenance.get("input_hash") == sha256_hex(input_obj)
    if evidence_obj is not None:
        checks["evidence_hash"] = provenance.get("evidence_hash") == sha256_hex(evidence_obj)
    return checks


def verify_attempt_files(run_dir: str, attempt_no: int) -> dict[str, bool]:
    """Verify raw-source and normalized-candidate hashes for an attempt folder."""
    prefix = f"attempt_{attempt_no:03d}"
    provenance_path = os.path.join(run_dir, f"{prefix}_provenance.json")
    candidate_path = os.path.join(run_dir, f"{prefix}_candidate.json")
    raw_source_path = os.path.join(run_dir, f"{prefix}_raw_source.json")

    with open(provenance_path, encoding="utf-8") as fh:
        provenance = json.load(fh)
    with open(candidate_path, encoding="utf-8") as fh:
        candidate = json.load(fh)
    raw_source = None
    if os.path.exists(raw_source_path):
        with open(raw_source_path, encoding="utf-8") as fh:
            raw_source = json.load(fh)

    return verify_provenance_hashes(
        provenance,
        raw_source=raw_source,
        normalized_candidate=candidate,
    )
