"""Property-based verifier contract for gold-absent tasks.

The core SFA verifier decides accept/reject by comparing a candidate against
*gold* evidence facts. Some tasks have no gold answer to store - but their
correctness is still a **decidable property** of the candidate and the sealed task
structure. This module provides that gold-absent verdict path: a versioned,
sealed contract of decidable properties whose deterministic conjunction is the
verdict.

Invariant compliance:
  * **Proposer cannot be verifier.** Every property is a pure, deterministic
    predicate over structured data. No LLM output participates in any verdict; the
    verdict is ``all(property_holds)``. The fixed ``sfa/verifier.py`` is untouched;
    this is a sibling mechanism, not a change to it.
  * **Gold isolation generalised.** For gold-absent tasks there is no stored gold
    answer. The correctness criterion lives in the sealed **property definitions**
    (for example, "the reported value equals the latest update in the timeline"),
    which are versioned and hashed. The contract and its evaluation context are
    verifier-side; the verdict logic never enters a proposer prompt.
  * **Deterministic + sealed.** ``build_contract`` seals a ``contract_hash`` over
    the canonical contract; ``evaluate`` seals a ``verdict_hash``. Same contract +
    same candidate + same context -> byte-identical verdict.

Decidable property families
---------------------------
* ``schema_validity``       - required fields are present and correctly typed.
* ``citation_grounding``    - every cited id exists in the evaluation context.
* ``internal_consistency``  - the candidate does not assert a subject as two
                              different values (self-contradiction).
* ``invariant_preservation`` - a named domain invariant holds. Shipped invariants:
    - ``temporal_recency``     - the reported value equals the value of the latest
                                 update episode in the sealed timeline (decides the
                                 deferred-consequence family without a gold label).
    - ``value_admissibility``  - the reported value is one that actually appears in
                                 the timeline (the answer is not fabricated).
"""
from __future__ import annotations

from typing import Any, Callable

from .hashing import sha256_hex

CONTRACT_SCHEMA = "sfa.property_contract.v0"
CONTRACT_VERSION = "sfa.property_contract.v0"
VERDICT_SCHEMA = "sfa.property_verdict.v0"

PROPERTY_FAMILIES = (
    "schema_validity",
    "citation_grounding",
    "internal_consistency",
    "invariant_preservation",
)


class PropertyContractError(ValueError):
    """Raised when a contract is malformed or uses an unsupported combinator."""


def _typecheck(value: Any, typename: str) -> bool:
    return {
        "str": isinstance(value, str),
        "list": isinstance(value, list),
        "dict": isinstance(value, dict),
        "int": isinstance(value, int) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }.get(typename, False)


def _reported_value(candidate: dict[str, Any], params: dict[str, Any]) -> tuple[bool, Any]:
    """Return (found, value) for the candidate's claim about ``params['subject']``."""
    claims_field = params.get("claims_field", "claims")
    subject_key = params.get("subject_key", "subject")
    value_key = params.get("value_key", "value")
    subject = params.get("subject")
    found = False
    value = None
    for claim in candidate.get(claims_field, []) or []:
        if isinstance(claim, dict) and claim.get(subject_key) == subject:
            value = claim.get(value_key)
            found = True
    return found, value


def _prop_schema_validity(candidate, context, params):
    required = params.get("required", {})
    missing = sorted(field for field in required if field not in candidate)
    if missing:
        return False, f"missing field(s): {', '.join(missing)}"
    for field, typename in required.items():
        if not _typecheck(candidate.get(field), typename):
            return False, f"field '{field}' must be of type {typename}"
    return True, "schema valid"


def _prop_citation_grounding(candidate, context, params):
    field = params["field"]
    collection = params["collection"]
    id_key = params.get("id_key", "id")
    cited = candidate.get(field, [])
    if not isinstance(cited, list):
        return False, f"field '{field}' must be a list of ids"
    valid = {
        item.get(id_key)
        for item in context.get(collection, [])
        if isinstance(item, dict)
    }
    ungrounded = [c for c in cited if c not in valid]
    if ungrounded:
        return False, f"ungrounded citation(s): {', '.join(map(str, ungrounded))}"
    return True, "all citations grounded"


def _prop_internal_consistency(candidate, context, params):
    claims_field = params.get("claims_field", "claims")
    subject_key = params.get("subject_key", "subject")
    value_key = params.get("value_key", "value")
    claims = candidate.get(claims_field, [])
    if not isinstance(claims, list):
        return False, f"field '{claims_field}' must be a list of claims"
    seen: dict[Any, Any] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            return False, "claim is not an object"
        subject = claim.get(subject_key)
        value = claim.get(value_key)
        if subject in seen and seen[subject] != value:
            return False, f"subject '{subject}' asserted as both {seen[subject]!r} and {value!r}"
        seen[subject] = value
    return True, "internally consistent"


def _inv_temporal_recency(candidate, context, params):
    timeline = context.get("timeline", [])
    updates = [ep for ep in timeline if isinstance(ep, dict) and ep.get("kind") == "update"]
    if not updates:
        return False, "no update episode in the sealed timeline"
    latest = max(updates, key=lambda ep: ep.get("offset", -1))
    expected = latest.get("value")
    found, reported = _reported_value(candidate, params)
    if not found:
        return False, f"no claim about subject '{params.get('subject')}'"
    if reported != expected:
        return False, f"reported {reported!r} != latest-update value {expected!r}"
    return True, "reported value matches the latest update (temporal recency preserved)"


def _inv_value_admissibility(candidate, context, params):
    timeline = context.get("timeline", [])
    admissible = {ep.get("value") for ep in timeline if isinstance(ep, dict)}
    found, reported = _reported_value(candidate, params)
    if not found:
        return False, f"no claim about subject '{params.get('subject')}'"
    if reported not in admissible:
        return False, f"reported {reported!r} is not an admissible timeline value"
    return True, "reported value appears in the timeline (not fabricated)"


_INVARIANTS: dict[str, Callable[..., tuple[bool, str]]] = {
    "temporal_recency": _inv_temporal_recency,
    "value_admissibility": _inv_value_admissibility,
}


def _prop_invariant_preservation(candidate, context, params):
    name = params.get("invariant")
    checker = _INVARIANTS.get(name)
    if checker is None:
        return False, f"unknown invariant: {name!r}"
    return checker(candidate, context, params)


PROPERTY_CHECKERS: dict[str, Callable[..., tuple[bool, str]]] = {
    "schema_validity": _prop_schema_validity,
    "citation_grounding": _prop_citation_grounding,
    "internal_consistency": _prop_internal_consistency,
    "invariant_preservation": _prop_invariant_preservation,
}


def build_contract(
    contract_id: str,
    task_family: str,
    properties: list[dict[str, Any]],
    *,
    conjunction: str = "all",
) -> dict[str, Any]:
    """Build and seal a versioned property contract."""
    if conjunction != "all":
        raise PropertyContractError(f"unsupported conjunction: {conjunction!r}")
    for prop in properties:
        if prop.get("family") not in PROPERTY_CHECKERS:
            raise PropertyContractError(f"unknown property family: {prop.get('family')!r}")
        if not prop.get("id"):
            raise PropertyContractError("each property requires an id")
    contract = {
        "schema": CONTRACT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "contract_id": contract_id,
        "task_family": task_family,
        "conjunction": conjunction,
        "properties": properties,
    }
    contract["contract_hash"] = sha256_hex({k: v for k, v in contract.items() if k != "contract_hash"})
    return contract


def evaluate(contract: dict[str, Any], candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a candidate against a sealed contract via deterministic conjunction."""
    if contract.get("conjunction") != "all":
        raise PropertyContractError(f"unsupported conjunction: {contract.get('conjunction')!r}")
    results = []
    for prop in contract.get("properties", []):
        checker = PROPERTY_CHECKERS.get(prop.get("family"))
        if checker is None:
            holds, detail = False, f"unknown property family: {prop.get('family')!r}"
        else:
            holds, detail = checker(candidate, context, prop.get("params", {}))
        results.append({
            "id": prop.get("id"),
            "family": prop.get("family"),
            "holds": bool(holds),
            "detail": detail,
        })
    passed = all(result["holds"] for result in results)  # deterministic conjunction
    verdict = {
        "schema": VERDICT_SCHEMA,
        "contract_id": contract.get("contract_id"),
        "contract_hash": contract.get("contract_hash"),
        "status": "PASS" if passed else "FAIL",
        "failed_properties": [result["id"] for result in results if not result["holds"]],
        "results": results,
    }
    verdict["verdict_hash"] = sha256_hex({k: v for k, v in verdict.items() if k != "verdict_hash"})
    return verdict
