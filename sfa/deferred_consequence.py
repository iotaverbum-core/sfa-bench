"""Deferred-consequence task family v0 (research core).

Episode ``T`` establishes a premise whose consequence binds only at horizon
``T+k``. An update between ``T`` and ``T+k`` changes the premise. The correct
output at ``T+k`` requires *propagating* the change through the deferred
consequence; the **characteristic failure** is preserving the stale consequence
(answering with the pre-update value). This is the HOP3-03-class probe.

Concretely, a quantity ``X`` (the consequence variable) has value ``v0`` at ``T``.
An update at ``T+u`` (with ``1 <= u <= k``) sets ``X := v1`` (``v1 != v0``).
Neutral distractor episodes fill the remaining offsets and never touch ``X``.
The query binds at ``T+k``: the correct answer is the propagated ``v1``; the
stale failure is ``v0``.

Invariant compliance:
  * **Deterministic replay.** All content is derived from an integer seed via
    SHA-256 (no ``random`` module), so ``generate_pack(config)`` is a pure
    function of ``config`` and seals byte-for-byte across machines. No wall-clock
    time enters a sealed case.
  * **Gold isolation.** ``proposer_view(case)`` contains only the ordered episodes
    and the query - never the labelled scoring fact or the correct/stale values as
    answers. The gold-bearing scoring evidence (the propagated final value) is
    verifier-side only and is never handed to a proposer. The update episode
    legitimately narrates the new value; deriving that it is the answer at the
    horizon is the task, not a leak.
  * **Proposer cannot be verifier.** Scoring is ``verifier.verify`` - a pure
    deterministic function of (input, scoring evidence, candidate, rules). No LLM
    output participates in the verdict. The stale answer deterministically fails
    as ``CONTRADICTS_EVIDENCE`` and classifies to the registered
    ``deferred_consequence_stale`` failure family.
  * **Horizon.** ``k`` is parameterised (default ``{1, 3, 5}``); at least three
    surface skins rotate over one invariant logical core.

The skins are illustrative fixture surfaces, not observations of real systems.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from . import families as families_mod
from . import verifier as verifier_mod
from .hashing import sha256_hex

CASE_SCHEMA = "sfa.deferred_consequence_case.v0"
PACK_SCHEMA = "sfa.deferred_consequence_pack.v0"
OCCURRENCE_SCHEMA = "sfa.deferred_consequence_occurrence.v0"
TASK_FAMILY = "deferred_consequence"
STALE_FAMILY = "deferred_consequence_stale"
GENESIS = "GENESIS"

DEFAULT_SEED = 20260301
HORIZONS = (1, 3, 5)

# Surface skins over one invariant logical core (a value that must be propagated
# from an update episode to the horizon query). ``kind`` selects the value domain.
_SKINS = (
    {
        "id": "inventory",
        "subject": "units_in_stock",
        "kind": "numeric",
        "entity": "SKU",
        "premise": "Inventory snapshot: {entity} {ref} recorded at {value} units in stock.",
        "update": "Stock movement posted: {entity} {ref} adjusted to {value} units in stock.",
        "distractor": "Note {n}: {entity} {ref} was relabelled to a new aisle; stock level unchanged.",
        "query": "After all episodes above, how many units_in_stock does {entity} {ref} currently have?",
    },
    {
        "id": "ledger_balance",
        "subject": "balance",
        "kind": "numeric",
        "entity": "account",
        "premise": "Opening record: {entity} {ref} balance is {value}.",
        "update": "Posting applied: {entity} {ref} balance is now {value}.",
        "distractor": "Note {n}: a statement was filed for {entity} {ref}; the balance is unaffected.",
        "query": "After all episodes above, what is the current balance of {entity} {ref}?",
    },
    {
        "id": "access_policy",
        "subject": "access_level",
        "kind": "status",
        "entity": "principal",
        "values": ("read_only", "standard", "elevated", "restricted", "suspended"),
        "premise": "Provisioning: {entity} {ref} is granted access_level {value}.",
        "update": "Policy change: {entity} {ref} access_level is updated to {value}.",
        "distractor": "Note {n}: an audit log was rotated for {entity} {ref}; access_level unchanged.",
        "query": "After all episodes above, what is the current access_level of {entity} {ref}?",
    },
    {
        "id": "document_status",
        "subject": "review_status",
        "kind": "status",
        "entity": "document",
        "values": ("draft", "in_review", "approved", "rejected", "archived"),
        "premise": "Filing: {entity} {ref} review_status is {value}.",
        "update": "Workflow event: {entity} {ref} review_status changed to {value}.",
        "distractor": "Note {n}: {entity} {ref} was re-tagged for search; review_status unchanged.",
        "query": "After all episodes above, what is the current review_status of {entity} {ref}?",
    },
)
_SKIN_BY_ID = {skin["id"]: skin for skin in _SKINS}
_PROPOSER_VIEW_KEYS = {"task", "episodes", "query", "answer_subject"}
# Structured scoring material must never appear inside a proposer-facing view.
_FORBIDDEN_VIEW_TOKENS = (
    '"facts"',
    '"scoring_evidence"',
    '"correct_value"',
    '"stale_value"',
    '"rules"',
    '"claims"',
)


def _uniform(*parts: Any) -> float:
    """Deterministic uniform in [0, 1) derived from SHA-256 of the parts."""
    digest = sha256_hex([str(p) for p in parts])
    return int(digest[:16], 16) / float(1 << 64)


def _randint(lo: int, hi: int, *parts: Any) -> int:
    """Deterministic integer in the inclusive range [lo, hi]."""
    if hi <= lo:
        return lo
    return lo + int(_uniform(*parts) * (hi - lo + 1))


def _fmt(value: Any) -> str:
    return str(value)


def _rules(subject: str) -> dict[str, Any]:
    """Scoring contract: the reported value must match the propagated fact."""
    return {
        "verifier_version": verifier_mod.VERIFIER_VERSION,
        "rules": [
            {"id": "schema", "type": "field_types", "types": {"claims": "list"}},
            {"id": "required", "type": "required_fields", "fields": ["claims"]},
            {"id": "grounding", "type": "claims_match_evidence",
             "claims_field": "claims", "evidence_collection": "facts",
             "match_on": "subject", "value_key": "value"},
        ],
    }


def _values(skin: dict[str, Any], seed: int, coord: tuple[Any, ...]) -> tuple[Any, Any]:
    """Deterministically derive distinct (v0, v1) for a skin. v1 != v0 always."""
    if skin["kind"] == "numeric":
        v0 = _randint(100, 900, seed, *coord, "v0")
        delta = _randint(1, 99, seed, *coord, "delta")
        direction = 1 if _uniform(seed, *coord, "dir") < 0.5 else -1
        v1 = v0 + direction * delta  # v0>=100, delta<=99 => v1>=1, and v1 != v0
        return v0, v1
    pool = skin["values"]
    i0 = _randint(0, len(pool) - 1, seed, *coord, "v0")
    step = _randint(1, len(pool) - 1, seed, *coord, "step")
    i1 = (i0 + step) % len(pool)  # step in [1, len-1] => i1 != i0
    return pool[i0], pool[i1]


def generate_case(seed: int, *, skin: str, k: int, replicate: int = 0) -> dict[str, Any]:
    """Build one sealed deferred-consequence case (pure function of its coordinates)."""
    if skin not in _SKIN_BY_ID:
        raise ValueError(f"unknown skin: {skin!r}")
    if k < 1:
        raise ValueError(f"horizon k must be >= 1, got {k}")
    spec = _SKIN_BY_ID[skin]
    subject = spec["subject"]
    coord = (skin, k, replicate)

    ref = f"{_randint(1000, 9999, seed, *coord, 'ref'):04d}"
    v0, v1 = _values(spec, seed, coord)
    update_offset = _randint(1, k, seed, *coord, "u")

    episodes = [{
        "offset": 0,
        "episode": "T",
        "kind": "premise",
        "text": spec["premise"].format(entity=spec["entity"], ref=ref, value=_fmt(v0)),
    }]
    for offset in range(1, k + 1):
        if offset == update_offset:
            episodes.append({
                "offset": offset,
                "episode": f"T+{offset}",
                "kind": "update",
                "text": spec["update"].format(entity=spec["entity"], ref=ref, value=_fmt(v1)),
            })
        else:
            episodes.append({
                "offset": offset,
                "episode": f"T+{offset}",
                "kind": "distractor",
                "text": spec["distractor"].format(entity=spec["entity"], ref=ref, n=offset),
            })

    case_id = f"dc_{skin}_k{k}_r{replicate:02d}"
    query = spec["query"].format(entity=spec["entity"], ref=ref)

    case = {
        "schema": CASE_SCHEMA,
        "case_id": case_id,
        "task_family": TASK_FAMILY,
        "skin": skin,
        "horizon_k": k,
        "replicate": replicate,
        "update_offset": update_offset,
        "subject": subject,
        "reference": ref,
        # Proposer-facing view: ordered episodes + query, no labelled gold.
        "proposer_view": {
            "task": "Read the episodes in order and report the current value of the tracked subject at the final horizon.",
            "episodes": episodes,
            "query": query,
            "answer_subject": subject,
        },
        # Verifier-side scoring bundle: gold-bearing, never handed to a proposer.
        "scoring": {
            "input": {"case_id": case_id, "question": query},
            "scoring_evidence": {
                "facts": [{"id": "x1", "subject": subject, "value": v1}],
                # Routes classify_family to the deferred_consequence_stale leaf.
                "task_family": TASK_FAMILY,
            },
            "rules": _rules(subject),
            "correct_value": v1,
            "stale_value": v0,
        },
    }
    case["case_hash"] = sha256_hex({k_: v for k_, v in case.items() if k_ != "case_hash"})
    return case


def proposer_view(case: dict[str, Any]) -> dict[str, Any]:
    """Return the gold-free proposer-facing view of a case (deep copy)."""
    return deepcopy(case["proposer_view"])


def proposer_view_is_gold_isolated(case: dict[str, Any]) -> bool:
    """True iff the proposer view carries only narrative episodes + query.

    The propagated value may appear inside episode prose (that is the task), but no
    labelled scoring fact, rule, claim, or correct/stale value may leak in.
    """
    view = proposer_view(case)
    if set(view) != _PROPOSER_VIEW_KEYS:
        return False
    blob = json.dumps(view, sort_keys=True, ensure_ascii=False)
    return not any(token in blob for token in _FORBIDDEN_VIEW_TOKENS)


def correct_candidate(case: dict[str, Any]) -> dict[str, Any]:
    """The propagated (correct) answer at the horizon."""
    return {"claims": [{"subject": case["subject"], "value": case["scoring"]["correct_value"]}]}


def stale_candidate(case: dict[str, Any]) -> dict[str, Any]:
    """The characteristic failure: the pre-update (stale) value."""
    return {"claims": [{"subject": case["subject"], "value": case["scoring"]["stale_value"]}]}


def score_candidate(case: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Score a candidate with the deterministic verifier (zero LLM involvement)."""
    bundle = case["scoring"]
    verdict = verifier_mod.verify(
        bundle["input"], bundle["scoring_evidence"], candidate, bundle["rules"]
    )
    family = None
    if verdict.status == "FAIL":
        family = families_mod.classify_family(
            verdict.category, candidate, bundle["scoring_evidence"]
        )
    return {
        "status": verdict.status,
        "category": verdict.category,
        "family": family,
        "verdict_hash": sha256_hex(verdict.to_dict()),
    }


def _chain_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev = GENESIS
    chained = []
    for seq, case in enumerate(cases):
        entry = dict(case)
        entry["seq"] = seq
        entry["prev_hash"] = prev
        entry["chain_hash"] = sha256_hex({k: v for k, v in entry.items() if k != "chain_hash"})
        prev = entry["chain_hash"]
        chained.append(entry)
    return chained


def generate_pack(config: dict[str, Any]) -> dict[str, Any]:
    """Pure function of ``config``; returns a sealed, hash-chained case pack."""
    seed = int(config.get("seed", DEFAULT_SEED))
    horizons = tuple(config.get("horizons", HORIZONS))
    skins = tuple(config.get("skins", tuple(s["id"] for s in _SKINS)))
    per_cell = int(config.get("per_cell", 1))

    cases = []
    for skin in skins:
        for k in horizons:
            for replicate in range(per_cell):
                cases.append(generate_case(seed, skin=skin, k=k, replicate=replicate))

    chained = _chain_cases(cases)
    pack = {
        "schema": PACK_SCHEMA,
        "config": {
            "seed": seed,
            "horizons": list(horizons),
            "skins": list(skins),
            "per_cell": per_cell,
            "task_family": TASK_FAMILY,
        },
        "case_count": len(chained),
        "cases": chained,
        "cases_root_hash": chained[-1]["chain_hash"] if chained else GENESIS,
    }
    pack["pack_hash"] = sha256_hex({k: v for k, v in pack.items() if k != "pack_hash"})
    return pack


def stale_occurrences(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Score the stale candidate for every case, yielding fingerprint-ready occurrences.

    Each occurrence carries the ``deferred_consequence_stale`` family so the
    fingerprint and recurrence machinery can aggregate this task family.
    """
    occurrences = []
    for case in pack["cases"]:
        result = score_candidate(case, stale_candidate(case))
        occurrences.append({
            "schema": OCCURRENCE_SCHEMA,
            "case_id": case["case_id"],
            "task_family": TASK_FAMILY,
            "skin": case["skin"],
            "horizon_k": case["horizon_k"],
            "status": result["status"],
            "category": result["category"],
            "family": result["family"],
            "case_hash": case["case_hash"],
            "verdict_hash": result["verdict_hash"],
        })
    return occurrences


def replay(pack: dict[str, Any]) -> dict[str, Any]:
    """Re-derive a pack from its sealed config and confirm byte-identical output."""
    rebuilt = generate_pack(pack["config"])
    issues = []
    if rebuilt["pack_hash"] != pack.get("pack_hash"):
        issues.append("pack_hash mismatch: pack is not reproducible from its config")
    if rebuilt["cases_root_hash"] != pack.get("cases_root_hash"):
        issues.append("cases_root_hash mismatch: sealed case chain differs")
    return {"attested": not issues, "issues": issues, "pack_hash": rebuilt["pack_hash"]}
