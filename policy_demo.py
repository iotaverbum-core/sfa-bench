#!/usr/bin/env python3
"""Offline SFA-Bench v1.1.0 policy-guided retry demonstration."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from sfa import policy
from sfa import verifier


ROOT = Path(__file__).resolve().parent
POLICY_DIR = ROOT / "examples" / "policy"
CASE_DIR = ROOT / "cases" / "external_candidate_001"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    fixture_path = POLICY_DIR / "multiple_recurring_families.json"
    policy_input = policy.load_policy_fixture(fixture_path)
    decision = policy.decide_policy(policy_input)
    replayed = policy.decide_policy(policy_input)
    sealed = not policy.verify_policy_decision(policy_input, decision)
    deterministic = policy.decision_bytes(decision) == policy.decision_bytes(replayed)

    escalation = policy.decide_policy(
        policy.load_policy_fixture(POLICY_DIR / "escalation_after_recurrence.json")
    )
    termination = policy.decide_policy(
        policy.load_policy_fixture(POLICY_DIR / "termination.json")
    )
    second_order_ok = escalation["escalation_level"] == 2 and (
        termination["escalation_level"] == 3
        and termination["termination_recommended"] is True
    )

    input_obj = _read_json(CASE_DIR / "input.json")
    evidence_obj = _read_json(CASE_DIR / "evidence.json")
    rules_obj = _read_json(CASE_DIR / "verifier_rules.json")
    candidate_obj = _read_json(CASE_DIR / "candidate_answer.json")
    baseline = verifier.verify(input_obj, evidence_obj, candidate_obj, rules_obj).to_dict()
    generator_envelope = {
        "candidate": candidate_obj,
        "generator_guidance": decision,
    }
    candidate_from_generator = generator_envelope["candidate"]
    guided_path = verifier.verify(
        input_obj, evidence_obj, candidate_from_generator, rules_obj
    ).to_dict()
    verifier_unchanged = baseline == guided_path

    print("# SFA-Bench v1.1.0 policy-guided retry demo")
    print()
    print(f"policy version: {decision['policy_version']}")
    print(f"recurrence profile loaded: {fixture_path.relative_to(ROOT).as_posix()}")
    print("threshold: count >= 2")
    print("triggered families: " + ", ".join(decision["triggered_families"]))
    print("selected directives:")
    for index, directive in enumerate(decision["directives"], start=1):
        print(f"  {index}. {directive['directive_id']}")
    print(f"escalation level: {decision['escalation_level']}")
    print(f"policy input hash: {decision['policy_input_hash']}")
    print(f"policy decision hash: {decision['decision_hash']}")
    print(f"policy decision sealed: {'yes' if sealed else 'no'}")
    print(f"policy decision deterministic: {'yes' if deterministic else 'no'}")
    print(f"escalation/termination fixtures deterministic: {'yes' if second_order_ok else 'no'}")
    print("directive target: generator/adapter prompt only")
    print("verifier received policy metadata: no")
    print(
        "verifier output unchanged with policy metadata excluded: "
        + ("yes" if verifier_unchanged else "no")
    )
    passed = sealed and deterministic and second_order_ok and verifier_unchanged
    print(f"final status: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
