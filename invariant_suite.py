#!/usr/bin/env python3
"""Verifier invariant suite.

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

    print("SFA verifier invariant suite")
    print("=" * 74)

    invariants.assert_verifier_static_guard(VERIFIER_PATH)
    print("static guard: PASS")
    print("  sfa/verifier.py has no forbidden history-adjacent references")

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

    print("=" * 74)
    print("PASS: fixed verifier inputs produced identical output with empty and populated surrounding history")
    return 0


if __name__ == "__main__":
    sys.exit(main())
