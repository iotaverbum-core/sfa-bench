"""Swappable model adapter surface for the SFA-Agent proof of concept.

The first adapter is deliberately deterministic. It makes no network calls and
has no LLM dependency; it exists only to prove the SFA loop can preserve a
failure, use history to warn the next attempt, and then pass.
"""
from typing import Any, Protocol


class ModelAdapter(Protocol):
    """Minimal candidate generator contract."""

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a candidate_answer.json-compatible object."""


class DeterministicFakeAdapter:
    """Fake adapter that fails first and improves after a history warning."""

    def produce_candidate(self, task: dict[str, Any], evidence: dict[str, Any], warning: dict[str, Any] | None = None) -> dict[str, Any]:
        if warning is None:
            return {
                "conclusion": "The contract has been approved.",
                "cited_evidence": ["f2"],
                "claims": [
                    {"subject": "approval_status", "value": "approved"},
                ],
            }

        return {
            "conclusion": "The contract approval status is pending.",
            "cited_evidence": ["f2"],
            "claims": [
                {"subject": "approval_status", "value": "pending"},
            ],
        }
