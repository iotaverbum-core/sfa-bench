"""Deterministic generator-side remediation policy for SFA-Bench v0.9.

Policy decisions are derived from sealed recurrence inputs.  They are proposer
metadata only: callers may pass the resulting caution to a generator or
adapter, but must never pass it to the verifier.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .hashing import canonical_bytes, sha256_hex


POLICY_VERSION = "sfa-policy-v0.1"
POLICY_INPUT_SCHEMA = "sfa.policy_input.v0.1"
POLICY_DECISION_SCHEMA = "sfa.policy_decision.v0.1"

FAMILY_PRIORITY = (
    "fabricated_entity",
    "contradicts_evidence",
    "unsupported_claim",
    "missing_required_field",
)

DIRECTIVES = {
    "fabricated_entity": {
        "directive_id": "closed_world_entity",
        "text": (
            "Only reference entities, citations, fields, and values that explicitly "
            "resolve to the evidence pack. Do not introduce new entities. If the "
            "evidence does not contain the entity, omit it."
        ),
        "level_2": (
            "Use only evidence-present entities. If uncertain, output "
            "`insufficient_evidence` rather than inventing."
        ),
    },
    "contradicts_evidence": {
        "directive_id": "claim_by_claim_evidence_check",
        "text": (
            "Before finalizing, check each claim value directly against the cited "
            "evidence. If a claim conflicts with evidence, revise it or omit it."
        ),
        "level_2": "Return a claim/evidence table before the final answer.",
    },
    "unsupported_claim": {
        "directive_id": "evidence_required",
        "text": (
            "Remove claims that cannot be directly supported by the evidence pack. "
            "Prefer fewer claims over unsupported claims."
        ),
        "level_2": "Output only claims with direct evidence references.",
    },
    "missing_required_field": {
        "directive_id": "schema_first",
        "text": (
            "Populate the required schema structure first. Do not finalize until "
            "every required field is present. Field presence does not permit "
            "invention; values must still be evidence-grounded."
        ),
        "level_2": "Emit the schema skeleton first, then fill its fields.",
    },
}

DEFAULT_CONFIG = {
    "config_version": "sfa-policy-config-v0.1",
    "recurrence_metric": "count",
    "recurrence_threshold": 2,
    "family_priority": list(FAMILY_PRIORITY),
    "composition_rule": "compose_all_triggered",
    "max_policy_retries": 2,
}


class PolicyError(ValueError):
    """Raised when a policy input is invalid or fails its seal."""


def make_policy_input(
    *,
    model_id: str,
    recurrence_profile: dict[str, Any],
    current_failure_family: str,
    retry_attempt_number: int,
    prior_remediation_history: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
    illustrative_fixture_data: bool = False,
) -> dict[str, Any]:
    """Build and seal canonical policy input from reportable recurrence data."""
    policy_config = _normalize_config(config or DEFAULT_CONFIG)
    profile = _normalize_profile(recurrence_profile)
    if not isinstance(model_id, str) or not model_id.strip():
        raise PolicyError("model_id is required")
    if not isinstance(current_failure_family, str) or not current_failure_family:
        raise PolicyError("current_failure_family is required")
    if not isinstance(retry_attempt_number, int) or retry_attempt_number < 1:
        raise PolicyError("retry_attempt_number must be a positive integer")
    history = _normalize_history(prior_remediation_history or [])
    policy_input = {
        "schema": POLICY_INPUT_SCHEMA,
        "policy_version": POLICY_VERSION,
        "illustrative_fixture_data": bool(illustrative_fixture_data),
        "model_id": model_id,
        "recurrence_profile": profile,
        "recurrence_profile_hash": sha256_hex(profile),
        "current_failure_family": current_failure_family,
        "retry_attempt_number": retry_attempt_number,
        "prior_remediation_history": history,
        "config": policy_config,
    }
    policy_input["input_hash"] = _hash_without(policy_input, "input_hash")
    return policy_input


def load_policy_input(path: str | Path) -> dict[str, Any]:
    """Load a stored policy input and verify all deterministic seals."""
    with open(path, "r", encoding="utf-8") as fh:
        stored = json.load(fh)
    rebuilt = make_policy_input(
        model_id=stored.get("model_id"),
        recurrence_profile=stored.get("recurrence_profile", {}),
        current_failure_family=stored.get("current_failure_family"),
        retry_attempt_number=stored.get("retry_attempt_number"),
        prior_remediation_history=stored.get("prior_remediation_history", []),
        config=stored.get("config"),
        illustrative_fixture_data=stored.get("illustrative_fixture_data", False),
    )
    if stored != rebuilt:
        raise PolicyError("stored policy input failed deterministic seal/replay")
    return rebuilt


def load_policy_fixture(path: str | Path) -> dict[str, Any]:
    """Load a clearly illustrative fixture and turn it into a sealed input."""
    with open(path, "r", encoding="utf-8") as fh:
        fixture = json.load(fh)
    if fixture.get("schema") != "sfa.policy_fixture.v0.1":
        raise PolicyError("unsupported policy fixture schema")
    if fixture.get("illustrative_fixture_data") is not True:
        raise PolicyError("policy fixture must be labelled illustrative")
    return make_policy_input(
        model_id=fixture.get("model_id"),
        recurrence_profile=fixture.get("recurrence_profile", {}),
        current_failure_family=fixture.get("current_failure_family"),
        retry_attempt_number=fixture.get("retry_attempt_number"),
        prior_remediation_history=fixture.get("prior_remediation_history", []),
        config=fixture.get("config", DEFAULT_CONFIG),
        illustrative_fixture_data=True,
    )


def decide_policy(policy_input: dict[str, Any]) -> dict[str, Any]:
    """Return the unique policy decision for one sealed input."""
    _assert_policy_input(policy_input)
    config = policy_input["config"]
    profile = policy_input["recurrence_profile"]
    threshold = config["recurrence_threshold"]
    priority = config["family_priority"]
    recurring = {
        family
        for family, metrics in profile["families"].items()
        if metrics["count"] >= threshold and family in DIRECTIVES
    }
    triggered = [family for family in priority if family in recurring]

    directives = []
    for family in triggered:
        mapping = DIRECTIVES[family]
        prior_applications = sum(
            1
            for item in policy_input["prior_remediation_history"]
            if item["family"] == family
            and item["directive_id"] == mapping["directive_id"]
            and item["applied"] is True
        )
        escalation_level = min(3, prior_applications + 1)
        if policy_input["retry_attempt_number"] > config["max_policy_retries"]:
            escalation_level = 3
        if escalation_level == 1:
            directive_text = mapping["text"]
        elif escalation_level == 2:
            directive_text = mapping["text"] + " " + mapping["level_2"]
        else:
            directive_text = (
                mapping["text"]
                + f" Stop automated retry for `{family}` and require human review."
            )
        metrics = profile["families"][family]
        directives.append(
            {
                "family": family,
                "directive_id": mapping["directive_id"],
                "base_directive_text": mapping["text"],
                "directive_text": directive_text,
                "recurrence_count": metrics["count"],
                "recurrence_rate": metrics["rate"],
                "prior_applications": prior_applications,
                "escalation_level": escalation_level,
            }
        )

    max_retries_exceeded = (
        policy_input["retry_attempt_number"] > config["max_policy_retries"]
    )
    escalation_level = max((item["escalation_level"] for item in directives), default=0)
    if max_retries_exceeded:
        escalation_level = 3
    termination = max_retries_exceeded or any(
        item["escalation_level"] == 3 for item in directives
    )
    if max_retries_exceeded:
        termination_reason = "maximum policy-guided retry count exceeded"
    elif termination:
        termination_reason = "a remediation directive recurred after level 2"
    else:
        termination_reason = None
    caution = "\n\n".join(
        f"{index}. [{item['directive_id']}] {item['directive_text']}"
        for index, item in enumerate(directives, start=1)
    )
    decision = {
        "schema": POLICY_DECISION_SCHEMA,
        "policy_version": POLICY_VERSION,
        "policy_input_hash": policy_input["input_hash"],
        "recurrence_profile_hash": policy_input["recurrence_profile_hash"],
        "config_hash": sha256_hex(config),
        "model_id": policy_input["model_id"],
        "current_failure_family": policy_input["current_failure_family"],
        "retry_attempt_number": policy_input["retry_attempt_number"],
        "threshold": {
            "metric": config["recurrence_metric"],
            "operator": ">=",
            "value": threshold,
        },
        "composition_rule": config["composition_rule"],
        "family_priority": priority,
        "triggered_families": triggered,
        "directives": directives,
        "generated_caution": caution,
        "escalation_level": escalation_level,
        "termination_recommended": termination,
        "termination_reason": termination_reason,
        "directive_target": "generator_or_adapter_input_only",
        "verifier_received_policy_metadata": False,
    }
    decision["decision_hash"] = _hash_without(decision, "decision_hash")
    return decision


def verify_policy_decision(
    policy_input: dict[str, Any], decision: dict[str, Any]
) -> list[dict[str, str]]:
    """Replay a decision and report seal, input, or derivation mismatches."""
    issues: list[dict[str, str]] = []
    stored_hash = decision.get("decision_hash")
    if stored_hash != _hash_without(decision, "decision_hash"):
        issues.append({"code": "decision_hash_mismatch", "detail": "decision content changed"})
    try:
        _assert_policy_input(policy_input)
    except PolicyError as exc:
        issues.append({"code": "policy_input_seal_mismatch", "detail": str(exc)})
        return issues
    if decision.get("policy_input_hash") != policy_input["input_hash"]:
        issues.append({"code": "policy_input_hash_mismatch", "detail": "decision/input link changed"})
    if decision.get("recurrence_profile_hash") != policy_input["recurrence_profile_hash"]:
        issues.append({"code": "recurrence_profile_hash_mismatch", "detail": "recurrence link changed"})
    expected = decide_policy(policy_input)
    if canonical_bytes(decision) != canonical_bytes(expected):
        issues.append({"code": "policy_replay_mismatch", "detail": "stored decision differs from replay"})
    return issues


def decision_bytes(decision: dict[str, Any]) -> bytes:
    """Canonical byte representation used by determinism checks."""
    return canonical_bytes(decision)


def _assert_policy_input(policy_input: dict[str, Any]) -> None:
    if policy_input.get("schema") != POLICY_INPUT_SCHEMA:
        raise PolicyError("unsupported policy input schema")
    if policy_input.get("policy_version") != POLICY_VERSION:
        raise PolicyError("unsupported policy version")
    if policy_input.get("recurrence_profile_hash") != sha256_hex(policy_input.get("recurrence_profile")):
        raise PolicyError("recurrence profile seal mismatch")
    if policy_input.get("input_hash") != _hash_without(policy_input, "input_hash"):
        raise PolicyError("policy input seal mismatch")
    _normalize_config(policy_input.get("config", {}))
    _normalize_profile(policy_input.get("recurrence_profile", {}))
    _normalize_history(policy_input.get("prior_remediation_history", []))


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise PolicyError("policy config must be an object")
    out = deepcopy(config)
    if out.get("config_version") != DEFAULT_CONFIG["config_version"]:
        raise PolicyError("unsupported policy config version")
    if out.get("recurrence_metric") != "count":
        raise PolicyError("v0.9 policy supports count recurrence only")
    threshold = out.get("recurrence_threshold")
    if not isinstance(threshold, int) or threshold < 1:
        raise PolicyError("recurrence threshold must be a positive integer")
    if out.get("family_priority") != list(FAMILY_PRIORITY):
        raise PolicyError("family priority must match the versioned v0.9 order")
    if out.get("composition_rule") != "compose_all_triggered":
        raise PolicyError("unsupported composition rule")
    if not isinstance(out.get("max_policy_retries"), int) or out["max_policy_retries"] < 1:
        raise PolicyError("max_policy_retries must be a positive integer")
    return out


def _normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise PolicyError("recurrence profile must be an object")
    scope = profile.get("scope")
    families = profile.get("families")
    total = profile.get("total_failures")
    if not isinstance(scope, str) or not scope:
        raise PolicyError("recurrence profile scope is required")
    if not isinstance(families, dict):
        raise PolicyError("recurrence profile families must be an object")
    if not isinstance(total, int) or total < 0:
        raise PolicyError("total_failures must be a non-negative integer")
    normalized: dict[str, dict[str, int | float]] = {}
    for family in sorted(families):
        metrics = families[family]
        if isinstance(metrics, int):
            count = metrics
            rate = round(count / total, 6) if total else 0.0
        elif isinstance(metrics, dict):
            count = metrics.get("count")
            rate = metrics.get("rate", round(count / total, 6) if isinstance(count, int) and total else 0.0)
        else:
            raise PolicyError(f"invalid recurrence metrics for {family}")
        if not isinstance(count, int) or count < 0:
            raise PolicyError(f"invalid recurrence count for {family}")
        if not isinstance(rate, (int, float)) or rate < 0 or rate > 1:
            raise PolicyError(f"invalid recurrence rate for {family}")
        normalized[str(family)] = {"count": count, "rate": round(float(rate), 6)}
    return {"scope": scope, "total_failures": total, "families": normalized}


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        raise PolicyError("prior remediation history must be a list")
    normalized = []
    for item in history:
        if not isinstance(item, dict):
            raise PolicyError("prior remediation item must be an object")
        family = item.get("family")
        directive_id = item.get("directive_id")
        applied = item.get("applied")
        if not isinstance(family, str) or not isinstance(directive_id, str) or not isinstance(applied, bool):
            raise PolicyError("prior remediation item requires family, directive_id, and applied")
        normalized.append({"family": family, "directive_id": directive_id, "applied": applied})
    return normalized


def _hash_without(obj: dict[str, Any], field: str) -> str:
    return sha256_hex({key: value for key, value in obj.items() if key != field})
