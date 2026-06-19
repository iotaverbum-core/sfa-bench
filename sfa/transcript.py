"""Offline transcript normalization for SFA-Bench.

Transcripts are local fixtures that resemble model output captures. They are
not live calls. The normalizer extracts exactly one fenced JSON candidate block
from `raw_response` and returns that object unchanged except for canonical JSON
encoding used for hashing.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from .hashing import canonical_bytes, sha256_hex
from .model_adapter import CandidateOutput


TRANSCRIPT_SCHEMA = "sfa.transcript.v0.1"
NORMALIZER_ID = "sfa.transcript_json_block_normalizer"
NORMALIZER_VERSION = "0.1"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


class TranscriptNormalizationError(ValueError):
    """Raised when a transcript cannot be normalized deterministically."""


@dataclass(frozen=True)
class NormalizedTranscript:
    transcript: dict[str, Any]
    candidate: dict[str, Any]
    candidate_bytes: bytes
    provenance: dict[str, Any]


class TranscriptCandidateAdapter:
    """ModelAdapter-compatible wrapper for local transcript fixtures."""

    adapter_name = "offline-transcript-fixture"
    adapter_kind = "offline_transcript"
    adapter_version = "0.1"
    source_type = "local_transcript_fixture"

    def __init__(self, source_path: str):
        self.source_path = source_path

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> CandidateOutput:
        transcript = load_transcript(self.source_path)
        normalized = normalize_transcript(transcript, input_obj=task, evidence_obj=evidence)
        metadata = transcript.get("metadata", {})
        return CandidateOutput(
            candidate=normalized.candidate,
            raw_source=transcript,
            adapter_name=metadata.get("adapter_id", self.adapter_name),
            adapter_kind=self.adapter_kind,
            adapter_version=metadata.get("prompt_template_id", self.adapter_version),
            source_type=self.source_type,
            source_path=self.source_path,
        )


def load_transcript(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_transcript(
    transcript: dict[str, Any],
    *,
    input_obj: dict[str, Any] | None = None,
    evidence_obj: dict[str, Any] | None = None,
    rules_obj: dict[str, Any] | None = None,
) -> NormalizedTranscript:
    """Normalize one transcript fixture into a candidate object.

    The normalizer extracts only. It does not infer fields, repair JSON, or use
    any model.
    """
    _validate_transcript(transcript)
    raw_response = transcript["raw_response"]
    candidate = extract_candidate_json(raw_response)
    candidate_bytes = canonical_bytes(candidate)
    provenance = build_transcript_provenance(
        transcript,
        candidate,
        candidate_bytes,
        input_obj=input_obj,
        evidence_obj=evidence_obj,
        rules_obj=rules_obj,
    )
    return NormalizedTranscript(transcript, candidate, candidate_bytes, provenance)


def extract_candidate_json(raw_response: str) -> dict[str, Any]:
    blocks = _JSON_BLOCK_RE.findall(raw_response)
    if len(blocks) != 1:
        raise TranscriptNormalizationError(
            f"expected exactly one fenced JSON candidate block, found {len(blocks)}"
        )
    try:
        candidate = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise TranscriptNormalizationError(f"candidate block is invalid JSON: {exc}") from exc
    if not isinstance(candidate, dict):
        raise TranscriptNormalizationError("candidate block must decode to a JSON object")
    return candidate


def build_transcript_provenance(
    transcript: dict[str, Any],
    candidate: dict[str, Any],
    candidate_bytes: bytes,
    *,
    input_obj: dict[str, Any] | None = None,
    evidence_obj: dict[str, Any] | None = None,
    rules_obj: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = transcript.get("metadata", {})
    out = {
        "normalizer_id": NORMALIZER_ID,
        "normalizer_version": NORMALIZER_VERSION,
        "transcript_schema_version": transcript.get("schema"),
        "raw_source_hash": sha256_hex(transcript),
        "normalized_candidate_hash": sha256_hex(candidate),
        "extraction_method": "single_fenced_json_block",
        "candidate_byte_length": len(candidate_bytes),
        "case_id": transcript.get("case_id"),
        "model_id": metadata.get("model_id") or "unknown",
        "adapter_id": metadata.get("adapter_id"),
        "prompt_template_id": metadata.get("prompt_template_id"),
        "verifier_blind_to_transcript": True,
    }
    if input_obj is not None and evidence_obj is not None and rules_obj is not None:
        out["verifier_input_hash"] = verifier_input_hash(input_obj, evidence_obj, candidate, rules_obj)
    return out


def verifier_input_hash(input_obj: dict[str, Any], evidence_obj: dict[str, Any], candidate_obj: dict[str, Any], rules_obj: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "input": input_obj,
            "evidence": evidence_obj,
            "candidate": candidate_obj,
            "rules": rules_obj,
        }
    )


def _validate_transcript(transcript: dict[str, Any]) -> None:
    if not isinstance(transcript, dict):
        raise TranscriptNormalizationError("transcript must be a JSON object")
    if transcript.get("schema") != TRANSCRIPT_SCHEMA:
        raise TranscriptNormalizationError(
            f"unsupported transcript schema: {transcript.get('schema')!r}"
        )
    required = ("case_id", "metadata", "prompt", "raw_response", "captured_at")
    missing = [field for field in required if field not in transcript]
    if missing:
        raise TranscriptNormalizationError("missing transcript field(s): " + ", ".join(missing))
    if not isinstance(transcript["metadata"], dict):
        raise TranscriptNormalizationError("metadata must be a JSON object")
    if not isinstance(transcript["prompt"], dict):
        raise TranscriptNormalizationError("prompt must be a JSON object")
    if not isinstance(transcript["raw_response"], str):
        raise TranscriptNormalizationError("raw_response must be a string")
