"""Deterministic free-text -> structured candidate extraction.

Most RAG assistants emit prose, not JSON. This module turns a free-text answer
plus the evidence it used into the structured ``{conclusion, cited_evidence,
claims}`` the verifier consumes - **deterministically**, so the same text always
yields the same candidate and an auditor can re-run the extraction during replay.

It is proposer-side only: its output crosses the verifier boundary, but it never
sees an answer key. v1 reliably surfaces the two highest-severity failures:

  * fabricated citations - citation-shaped tokens in the text that are not in the
    evidence; and
  * contradictions - a value asserted for an evidence-covered fact that disagrees
    with the evidence.

It is deliberately conservative: it does not invent claims about subjects the
evidence does not cover, so it under-reports rather than fabricates findings.
Absence of findings on free text is therefore not a proof of full grounding.
"""
from __future__ import annotations

import re
from typing import Any

from sfa.hashing import sha256_hex

EXTRACTOR_VERSION = "groundledger-extractor-v1"
EXTRACTION_SCHEMA = "groundledger.extraction.v1"

DEFAULT_CITATION_PATTERNS = (r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+\b", r"\[([^\]]+)\]")
DEFAULT_WINDOW = 60

_CURRENCY = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")
_PERCENT = re.compile(r"\d+(?:\.\d+)?\s?%")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_candidate(
    answer_text: str,
    evidence: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{candidate, provenance, trace}`` from a free-text answer."""
    if not isinstance(answer_text, str):
        raise ValueError("answer_text must be a string")
    config = config or {}
    patterns = tuple(config.get("citation_patterns", DEFAULT_CITATION_PATTERNS))
    window = int(config.get("value_window", DEFAULT_WINDOW))

    valid_ids = {d.get("id") for d in evidence.get("documents", []) if isinstance(d, dict)}
    cited, citation_trace = _extract_citations(answer_text, patterns, valid_ids)
    claims, claim_trace = _extract_claims(answer_text, evidence.get("facts", []), window)

    candidate = {
        "conclusion": answer_text.strip(),
        "cited_evidence": cited,
        "claims": claims,
    }
    provenance = {
        "schema": EXTRACTION_SCHEMA,
        "extractor_version": EXTRACTOR_VERSION,
        "answer_text_hash": sha256_hex(answer_text),
        "config_hash": sha256_hex({"citation_patterns": list(patterns), "value_window": window}),
        "candidate_hash": sha256_hex(candidate),
    }
    return {
        "candidate": candidate,
        "provenance": provenance,
        "trace": {"citations": citation_trace, "claims": claim_trace},
    }


def _extract_citations(text: str, patterns, valid_ids) -> tuple[list[str], list[dict[str, Any]]]:
    hits: list[tuple[int, str]] = []
    for pattern in patterns:
        compiled = re.compile(pattern)
        for match in compiled.finditer(text):
            token = match.group(1) if compiled.groups else match.group(0)
            token = token.strip()
            if token:
                hits.append((match.start(), token))
    hits.sort(key=lambda h: h[0])
    ordered: list[str] = []
    trace: list[dict[str, Any]] = []
    seen: set[str] = set()
    for start, token in hits:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        trace.append({"token": token, "at": start, "in_evidence": token in valid_ids})
    return ordered, trace


def _extract_claims(text: str, facts, window: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    low = text.lower()
    claims: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, dict) or "subject" not in fact:
            continue
        subject = fact["subject"]
        value = fact.get("value")
        position = _find_subject(low, _surface_forms(subject, fact.get("aliases")))
        if position is None:
            continue
        kind = _infer_kind(value)
        asserted = _read_value(text, position, window, kind, value)
        if asserted is None:
            trace.append({"subject": subject, "found_subject_at": position, "asserted": None,
                          "note": "subject mentioned but no value of the expected kind nearby"})
            continue
        if _values_equal(asserted, value, kind):
            claims.append({"subject": subject, "value": value})
            trace.append({"subject": subject, "asserted": asserted, "evidence_value": value,
                          "result": "matches"})
        else:
            claims.append({"subject": subject, "value": asserted})
            trace.append({"subject": subject, "asserted": asserted, "evidence_value": value,
                          "result": "differs"})
    return claims, trace


def _surface_forms(subject: str, aliases: Any) -> list[str]:
    forms = {subject.lower(), subject.replace("_", " ").lower()}
    if isinstance(aliases, list):
        forms.update(str(a).lower() for a in aliases if a)
    return sorted((f for f in forms if f), key=len, reverse=True)


def _find_subject(low: str, forms: list[str]) -> int | None:
    best: int | None = None
    for form in forms:
        idx = low.find(form)
        if idx != -1:
            end = idx + len(form)
            best = end if best is None else min(best, end)
    return best


def _infer_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        if value.startswith("$"):
            return "currency"
        if value.endswith("%"):
            return "percent"
        if _DATE.fullmatch(value.strip()):
            return "date"
    return "string"


def _read_value(text: str, start: int, window: int, kind: str, evidence_value: Any) -> str | None:
    segment = text[start:start + window]
    pattern = {"currency": _CURRENCY, "percent": _PERCENT, "date": _DATE, "number": _NUMBER}.get(kind)
    if pattern is not None:
        match = pattern.search(segment)
        return match.group(0).strip() if match else None
    # string kind: only assert when the evidence value itself appears nearby.
    needle = str(evidence_value).lower()
    return str(evidence_value) if needle and needle in segment.lower() else None


def _values_equal(asserted: str, value: Any, kind: str) -> bool:
    if kind in ("currency", "number", "percent"):
        return _digits(asserted) == _digits(str(value))
    return asserted.strip().lower() == str(value).strip().lower()


def _digits(text: str) -> str:
    return re.sub(r"[^0-9.]", "", text)
