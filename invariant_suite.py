#!/usr/bin/env python3
"""SFA-Bench v1.0.0 verifier, fingerprint, and policy invariant suite.

Run: python invariant_suite.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
VERIFIER_PATH = ROOT / "sfa" / "verifier.py"
INVARIANTS_PATH = ROOT / "sfa" / "invariants.py"


def _load_invariants_module():
    spec = importlib.util.spec_from_file_location("sfa_invariants_standalone", INVARIANTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {INVARIANTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_case(case_id: str):
    case_dir = CASES_DIR / case_id
    return {
        "input_obj": _read_json(case_dir / "input.json"),
        "evidence_obj": _read_json(case_dir / "evidence.json"),
        "candidate_obj": _read_json(case_dir / "candidate_answer.json"),
        "rules_obj": _read_json(case_dir / "verifier_rules.json"),
    }


def _summarize_verdict(output):
    return json.dumps(output, sort_keys=True, separators=(",", ":"))


def main() -> int:
    invariants = _load_invariants_module()

    print("SFA-Bench v1.0.0 Verifier, Fingerprint & Policy Invariant Suite")
    print("=" * 74)

    invariants.assert_verifier_static_guard(VERIFIER_PATH)
    print("static guard: PASS")
    print("  sfa/verifier.py has no forbidden history-adjacent references")
    invariants.assert_verifier_callsite_guard(ROOT)
    print("call-site guard: PASS")
    print("  verifier call arguments exclude transcript/provenance/model metadata")

    cases = [
        ("PASS candidate", "case_001_grounded_pass"),
        ("FAIL candidate", "case_002_contradicts_evidence"),
    ]

    print("history-blindness:")
    for label, case_id in cases:
        result = invariants.run_history_blindness_case(
            name=label,
            repo_root=ROOT,
            **_load_case(case_id),
        )
        print(f"  {label}: PASS")
        print(f"    empty:     {_summarize_verdict(result.empty_output)}")
        print(f"    populated: {_summarize_verdict(result.populated_output)}")

    external_case = _load_case("external_candidate_001")
    isolation = invariants.run_normalization_isolation_case(
        input_obj=external_case["input_obj"],
        evidence_obj=external_case["evidence_obj"],
        rules_obj=external_case["rules_obj"],
    )
    print("normalization-isolation:")
    print("  transcript metadata differential: PASS")
    print(f"    transcript A: {_summarize_verdict(isolation.empty_output)}")
    print(f"    transcript B: {_summarize_verdict(isolation.populated_output)}")

    airlock = invariants.run_adapter_airlock_case(
        input_obj=external_case["input_obj"],
        evidence_obj=external_case["evidence_obj"],
        rules_obj=external_case["rules_obj"],
        repo_root=ROOT,
    )
    print("adapter-airlock:")
    print("  fixture adapter returns transcript-shaped raw_source: PASS")
    print("  verifier receives normalized candidate only: PASS")
    print(f"    baseline: {_summarize_verdict(airlock.empty_output)}")
    print(f"    metadata changed: {_summarize_verdict(airlock.populated_output)}")

    metadata = invariants.run_adapter_metadata_blindness_case(
        input_obj=external_case["input_obj"],
        evidence_obj=external_case["evidence_obj"],
        rules_obj=external_case["rules_obj"],
    )
    print("adapter-metadata-blindness:")
    print("  adapter/model metadata differential: PASS")
    print(f"    adapter A: {_summarize_verdict(metadata.empty_output)}")
    print(f"    adapter B: {_summarize_verdict(metadata.populated_output)}")

    fingerprint_blind = invariants.run_fingerprint_metadata_blindness_case(
        input_obj=external_case["input_obj"],
        evidence_obj=external_case["evidence_obj"],
        rules_obj=external_case["rules_obj"],
    )
    print("fingerprint-blindness:")
    print("  model/fingerprint/recurrence metadata differential: PASS")
    print(f"    baseline: {_summarize_verdict(fingerprint_blind.empty_output)}")
    print(f"    metadata changed: {_summarize_verdict(fingerprint_blind.populated_output)}")

    invariants.assert_fingerprint_determinism(ROOT)
    print("fingerprint determinism: PASS")
    print("  same sealed fixture inputs produce the same occurrences and fingerprint")

    invariants.assert_fingerprint_fixed_condition_guard(ROOT)
    print("fixed-condition comparison guard: PASS")
    print("  taxonomy, evidence-pack, and prompt-condition mismatches are refused")

    policy_blind = invariants.run_policy_metadata_blindness_case(
        input_obj=external_case["input_obj"],
        evidence_obj=external_case["evidence_obj"],
        candidate_obj=external_case["candidate_obj"],
        rules_obj=external_case["rules_obj"],
        repo_root=ROOT,
    )
    print("policy-blindness:")
    print("  generator-only directive differential: PASS")
    print(f"    baseline: {_summarize_verdict(policy_blind.empty_output)}")
    print(f"    guidance changed: {_summarize_verdict(policy_blind.populated_output)}")

    invariants.assert_policy_determinism(ROOT)
    print("policy determinism: PASS")
    print("  same sealed recurrence input produces byte-identical decision output")
    invariants.assert_policy_composition_determinism(ROOT)
    print("policy composition determinism: PASS")
    print("  multiple recurring families follow the fixed family priority order")
    invariants.assert_policy_escalation_determinism(ROOT)
    print("policy escalation determinism: PASS")
    print("  prior remediation history deterministically selects levels 2 and 3")

    invariants.assert_ci_live_adapter_unreachable()
    print("CI live-adapter unreachability: PASS")
    print("  CI registry exposes no live adapters and rejects live opt-in")

    print("=" * 74)
    print("PASS: verifier blindness, fingerprints, and generator-side policy invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
