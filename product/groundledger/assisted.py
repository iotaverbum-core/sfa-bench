"""Optional LLM-assisted claim extraction (proposer-side, sealed, re-checked).

The deterministic rule extractor (``extraction.py``) is conservative: it only
looks for claims about subjects the evidence covers, so it can miss a novel
unsupported claim in free text. This module lets a model widen recall - safely.

The design keeps every product guarantee:

  * The model is a **proposer**. It only nominates ``{subject, value}`` claims; it
    never judges groundedness and never sees an answer key.
  * Its output is **sealed** into the submission as ``extraction_proposal`` and
    then **deterministically re-checked**: a nominated claim survives only if its
    subject and value literally appear in the answer text (``extraction.py``). A
    model therefore cannot fabricate a finding - it can only surface claims that
    are really in the text.
  * The model is called **once, at ingest**. Replay re-derives from the sealed
    proposal and never calls a model, so replay stays deterministic and offline.
  * The path is **opt-in and disabled under CI**. The caller supplies the model
    call (a ``suggest`` function); no provider integration or network dependency
    is added to the product. The default deterministic path is unchanged.

``suggest`` has signature ``suggest(answer_text, evidence) -> list[{subject, value}]``.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from sfa.hashing import sha256_hex

Suggester = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


class AssistedExtractionError(RuntimeError):
    """Raised when the LLM-assisted proposer is used where it is not allowed."""


def _ci_active() -> bool:
    return os.environ.get("CI", "").strip().lower() == "true"


def propose(
    answer_text: str,
    evidence: dict[str, Any],
    *,
    suggest: Suggester,
    allow_in_ci: bool = False,
) -> list[dict[str, Any]]:
    """Call the caller-supplied model once and return a normalized proposal.

    Disabled under CI unless ``allow_in_ci=True`` is passed explicitly (only do so
    with a deterministic, offline ``suggest``, e.g. in tests). The returned list is
    the sealed, deterministic input the verifier boundary re-checks.
    """
    if suggest is None:
        raise AssistedExtractionError("a suggest(answer_text, evidence) callable is required")
    if _ci_active() and not allow_in_ci:
        raise AssistedExtractionError(
            "LLM-assisted extraction is disabled under CI; pass allow_in_ci=True only "
            "with a deterministic offline suggester"
        )
    raw = suggest(answer_text, evidence)
    return normalize_proposal(raw)


def normalize_proposal(raw: Any) -> list[dict[str, Any]]:
    """Deterministically normalize a model's raw output into sealed claims."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        value = item.get("value")
        if not isinstance(subject, str) or not subject or subject in seen:
            continue
        seen.add(subject)
        out.append({"subject": subject, "value": value})
    out.sort(key=lambda claim: claim["subject"])
    return out


def proposal_hash(proposal: list[dict[str, Any]]) -> str:
    return sha256_hex(proposal)


def build_text_submission(
    *,
    answer_id: str,
    answer_text: str,
    evidence: dict[str, Any],
    suggest: Suggester,
    rule_pack: str = "insurance_v1",
    task_input: dict[str, Any] | None = None,
    allow_in_ci: bool = False,
) -> dict[str, Any]:
    """Build a submission carrying the sealed proposal, ready for the deterministic engine.

    The model runs here (wherever this code runs - the customer's environment). The
    resulting submission is ordinary data: the engine and API seal and judge it
    deterministically, and never call a model themselves.
    """
    proposal = propose(answer_text, evidence, suggest=suggest, allow_in_ci=allow_in_ci)
    submission: dict[str, Any] = {
        "answer_id": answer_id,
        "rule_pack": rule_pack,
        "answer_text": answer_text,
        "evidence": evidence,
        "extraction_proposal": proposal,
    }
    if task_input is not None:
        submission["task_input"] = task_input
    return submission
