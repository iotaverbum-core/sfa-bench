"""Local external candidate adapter.

This adapter reads a candidate from a local JSON file and normalizes it into
the verifier's candidate_answer.json shape. It performs no network calls and
does not import external services.
"""
from copy import deepcopy
import json
import os
from typing import Any

from .model_adapter import CandidateOutput


class ExternalCandidateAdapter:
    """Manual adapter for externally produced local JSON candidates."""

    adapter_name = "manual-json-candidate"
    adapter_kind = "external_manual"
    adapter_version = "0.1"
    source_type = "local_json_file"

    def __init__(self, source_path: str):
        self.source_path = os.path.abspath(source_path)

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> CandidateOutput:
        raw_source = self._read_source()
        candidate = normalize_external_candidate(raw_source)
        return CandidateOutput(
            candidate=candidate,
            raw_source=raw_source,
            adapter_name=self.adapter_name,
            adapter_kind=self.adapter_kind,
            adapter_version=self.adapter_version,
            source_type=self.source_type,
            source_path=self.source_path,
        )

    def _read_source(self):
        with open(self.source_path, "r", encoding="utf-8") as fh:
            return json.load(fh)


def normalize_external_candidate(raw_source: dict[str, Any]) -> dict[str, Any]:
    """Normalize supported manual JSON shapes to candidate_answer.json format."""
    if not isinstance(raw_source, dict):
        raise ValueError("external candidate source must be a JSON object")

    if isinstance(raw_source.get("candidate"), dict):
        return normalize_external_candidate(raw_source["candidate"])

    if _looks_like_candidate(raw_source):
        return {
            "conclusion": deepcopy(raw_source["conclusion"]),
            "cited_evidence": deepcopy(raw_source["cited_evidence"]),
            "claims": deepcopy(raw_source["claims"]),
        }

    conclusion = raw_source.get("conclusion", raw_source.get("answer"))
    cited_evidence = raw_source.get("cited_evidence", raw_source.get("evidence_ids"))
    claims = raw_source.get("claims")
    if claims is None and isinstance(raw_source.get("claims_by_subject"), dict):
        claims = [
            {"subject": subject, "value": value}
            for subject, value in raw_source["claims_by_subject"].items()
        ]

    return {
        "conclusion": deepcopy(conclusion),
        "cited_evidence": deepcopy(cited_evidence),
        "claims": deepcopy(claims),
    }


def _looks_like_candidate(raw_source: dict[str, Any]) -> bool:
    return all(key in raw_source for key in ("conclusion", "cited_evidence", "claims"))
