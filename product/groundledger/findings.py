"""Customer-facing interpretation of verifier results.

The verifier emits a deterministic category/family. This module turns that into
language an insurance or compliance buyer understands: a title, a severity, why
it matters, and the recommended next action. It is presentation only - it never
influences the verdict.
"""
from __future__ import annotations

from typing import Any

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_CATALOG: dict[str, dict[str, str]] = {
    "fabricated_entity": {
        "title": "Fabricated citation",
        "severity": "critical",
        "plain_language": "The assistant cited a source document that does not exist in the provided evidence.",
        "why_it_matters": "A fabricated citation makes a wrong answer look authoritative. It is the least defensible failure in a regulated workflow and the hardest to explain in an audit or dispute.",
        "recommended_action": "Block the answer from reaching the customer and route to human review. Constrain the assistant to cite only retrieved document ids.",
    },
    "contradicts_evidence": {
        "title": "Contradicts the source",
        "severity": "critical",
        "plain_language": "The assistant stated a value that conflicts with the evidence it cited.",
        "why_it_matters": "A contradicted fact - a wrong deductible, limit, or premium - is a direct liability and a likely complaint or claim dispute.",
        "recommended_action": "Block the answer and correct it against the evidence value before responding.",
    },
    "unsupported_claim": {
        "title": "Unsupported claim",
        "severity": "high",
        "plain_language": "The assistant asserted a fact that no provided evidence supports.",
        "why_it_matters": "Unsupported claims are guesses presented as fact. Even when they happen to be right, you cannot prove they were grounded.",
        "recommended_action": "Remove the unsupported claim or add the evidence that supports it. Prefer fewer claims over ungrounded ones.",
    },
    "missing_required_field": {
        "title": "Incomplete answer",
        "severity": "medium",
        "plain_language": "The answer is missing a field your schema requires (for example, citations or claims).",
        "why_it_matters": "An answer without citations or structured claims cannot be checked for grounding at all - it is unverifiable by construction.",
        "recommended_action": "Require the assistant to return the full answer schema before the answer is shown.",
    },
    "schema_violation": {
        "title": "Malformed answer",
        "severity": "medium",
        "plain_language": "A field in the answer was the wrong type or shape.",
        "why_it_matters": "Malformed answers break downstream automation and indicate the assistant is not following its output contract.",
        "recommended_action": "Validate and reject malformed answers before they are stored or shown.",
    },
}

_DEFAULT = {
    "title": "Ungrounded answer",
    "severity": "high",
    "plain_language": "The answer did not pass the groundedness rules.",
    "why_it_matters": "Ungrounded answers create liability and erode trust in the assistant.",
    "recommended_action": "Route the answer to human review.",
}


def describe(category: str | None, family: str | None) -> dict[str, str]:
    """Return customer-facing finding content for a verdict.

    Resolution order: exact family, then the family's root prefix (e.g. an
    ``unsupported_number`` refinement maps to ``unsupported_claim``), then a
    safe default.
    """
    if family and family in _CATALOG:
        return dict(_CATALOG[family])
    if family and family.startswith("unsupported"):
        return dict(_CATALOG["unsupported_claim"])
    if category:
        lowered = category.lower()
        if lowered in _CATALOG:
            return dict(_CATALOG[lowered])
    return dict(_DEFAULT)


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, len(SEVERITY_ORDER))


def summarize_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Count findings by severity (highest first)."""
    counts: dict[str, int] = {}
    for finding in findings:
        sev = finding.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: severity_rank(kv[0])))
