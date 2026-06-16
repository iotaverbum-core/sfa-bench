"""Swappable model adapter surface for the SFA-Agent proof of concept.

The first adapter is deliberately deterministic. It makes no network calls and
has no LLM dependency; it exists only to prove the SFA loop can preserve a
failure, use history to warn the next attempt, and then pass.
"""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class CandidateOutput:
    """Adapter output plus source metadata kept outside the verifier."""

    candidate: dict[str, Any]
    raw_source: Any
    adapter_name: str
    adapter_kind: str
    adapter_version: str
    source_type: str
    source_path: str | None = None


class ModelAdapter(Protocol):
    """Minimal candidate generator contract."""

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> CandidateOutput:
        """Return a candidate_answer.json-compatible object."""


class DeterministicFakeAdapter:
    """Fake adapter that fails first and improves after a history warning."""

    adapter_name = "deterministic-fake"
    adapter_kind = "deterministic_fake"
    adapter_version = "0.2"
    source_type = "generated_json"

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> CandidateOutput:
        if warning is None:
            candidate = {
                "conclusion": "The contract has been approved.",
                "cited_evidence": ["f2"],
                "claims": [
                    {"subject": "approval_status", "value": "approved"},
                ],
            }

        else:
            candidate = {
                "conclusion": "The contract approval status is pending.",
                "cited_evidence": ["f2"],
                "claims": [
                    {"subject": "approval_status", "value": "pending"},
                ],
            }

        raw_source = {
            "adapter": self.adapter_name,
            "warning_used": warning is not None,
            "candidate": candidate,
        }
        return CandidateOutput(
            candidate=candidate,
            raw_source=raw_source,
            adapter_name=self.adapter_name,
            adapter_kind=self.adapter_kind,
            adapter_version=self.adapter_version,
            source_type=self.source_type,
        )
