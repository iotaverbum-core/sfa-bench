"""The SFA-Bench verifier.

Hard rule: the verifier judges a candidate answer using ONLY the evidence and
the verifier rules. It never receives, reads, or imports the expected verdict.
The function signature makes that structural - there is no parameter through
which a gold label could enter `verify()`.

The verifier runs a small ordered set of rules. The first rule to fire decides
the primary failure category; every violation is still recorded for the
artifact, so a downstream learner sees the full picture.
"""
from dataclasses import dataclass, field
from typing import Optional

from . import categories

VERIFIER_VERSION = "sfa-verifier-0.1"


@dataclass
class Violation:
    rule_id: str
    category: str
    detail: str

    def to_dict(self):
        return {"rule_id": self.rule_id, "category": self.category, "detail": self.detail}


@dataclass
class Verdict:
    status: str                       # "PASS" or "FAIL"
    category: Optional[str]           # primary failure category, or None on PASS
    explanation: str
    violations: list = field(default_factory=list)

    def to_dict(self):
        return {
            "status": self.status,
            "category": self.category,
            "explanation": self.explanation,
            "violations": [v.to_dict() for v in self.violations],
        }


def _typecheck(value, typename) -> bool:
    return {
        "str": isinstance(value, str),
        "list": isinstance(value, list),
        "dict": isinstance(value, dict),
        "int": isinstance(value, int) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }.get(typename, False)


def _rule_field_types(rule, candidate, evidence):
    for fname, typename in rule.get("types", {}).items():
        if fname in candidate and not _typecheck(candidate[fname], typename):
            return Violation(rule["id"], categories.SCHEMA_VIOLATION,
                             f"field '{fname}' must be of type {typename}")
    return None


def _rule_required_fields(rule, candidate, evidence):
    missing = [f for f in rule.get("fields", []) if f not in candidate]
    if missing:
        return Violation(rule["id"], categories.MISSING_REQUIRED_FIELD,
                         f"missing required field(s): {', '.join(missing)}")
    return None


def _rule_citations_exist(rule, candidate, evidence):
    fname = rule["field"]
    cited = candidate.get(fname, [])
    if not isinstance(cited, list):
        return Violation(rule["id"], categories.SCHEMA_VIOLATION,
                         f"field '{fname}' must be a list of evidence ids")
    id_key = rule.get("id_key", "id")
    valid = {item.get(id_key) for item in evidence.get(rule["evidence_collection"], [])}
    fabricated = [c for c in cited if c not in valid]
    if fabricated:
        return Violation(rule["id"], categories.FABRICATED_ENTITY,
                         f"cited evidence id(s) not present in evidence: {', '.join(map(str, fabricated))}")
    return None


def _rule_claims_match_evidence(rule, candidate, evidence):
    claims = candidate.get(rule["claims_field"], [])
    if not isinstance(claims, list):
        return Violation(rule["id"], categories.SCHEMA_VIOLATION,
                         f"field '{rule['claims_field']}' must be a list of claims")
    match_on = rule.get("match_on", "subject")
    value_key = rule.get("value_key", "value")
    facts = evidence.get(rule["evidence_collection"], [])
    fact_by_key = {f[match_on]: f for f in facts if match_on in f}
    for claim in claims:
        subj = claim.get(match_on)
        if subj not in fact_by_key:
            return Violation(rule["id"], categories.UNSUPPORTED_CLAIM,
                             f"claim about '{subj}' is not supported by any evidence fact")
        ev_val = fact_by_key[subj].get(value_key)
        cl_val = claim.get(value_key)
        if cl_val != ev_val:
            return Violation(rule["id"], categories.CONTRADICTS_EVIDENCE,
                             f"claim '{subj}={cl_val}' contradicts evidence '{subj}={ev_val}'")
    return None


_RULE_HANDLERS = {
    "field_types": _rule_field_types,
    "required_fields": _rule_required_fields,
    "citations_exist": _rule_citations_exist,
    "claims_match_evidence": _rule_claims_match_evidence,
}


def verify(input_obj, evidence_obj, candidate_obj, rules_obj) -> Verdict:
    """Judge candidate_obj against evidence_obj using rules_obj only.

    There is deliberately no expected-verdict parameter. `input_obj` is the
    task statement and is available to rules but is not itself a source of
    truth - only `evidence_obj` is.
    """
    violations = []
    for rule in rules_obj.get("rules", []):
        handler = _RULE_HANDLERS.get(rule.get("type"))
        if handler is None:
            violations.append(Violation(rule.get("id", "?"), categories.SCHEMA_VIOLATION,
                                        f"unknown rule type: {rule.get('type')}"))
            continue
        v = handler(rule, candidate_obj, evidence_obj)
        if v is not None:
            violations.append(v)
    if not violations:
        return Verdict("PASS", None,
                       "candidate is consistent with evidence under all rules", [])
    primary = violations[0]
    return Verdict("FAIL", primary.category, primary.detail, violations)
