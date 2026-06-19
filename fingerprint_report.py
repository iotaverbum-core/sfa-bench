#!/usr/bin/env python3
"""Re-derive and print the v1.0.0 illustrative failure fingerprint report."""
from __future__ import annotations

from pathlib import Path
import sys

from sfa import fingerprints


ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "examples" / "fingerprints" / "demo_pack"
FIXTURE_SET = FIXTURE_DIR / "fixture_set.json"
EXPECTED = FIXTURE_DIR / "expected_fingerprint.json"


def main() -> int:
    report, occurrences, issues = fingerprints.verify_fixture_set(
        FIXTURE_SET, EXPECTED, ROOT
    )
    conditions = report["conditions"]
    print("# SFA-Bench v1.0.0 - Failure Fingerprint Report")
    print()
    print(f"fixture set: {FIXTURE_SET.relative_to(ROOT).as_posix()}")
    print(f"fixture set id: {report['fixture_set_id']}")
    print(f"taxonomy: {conditions['taxonomy_version']}")
    print(f"evidence pack: {conditions['evidence_pack_id']}")
    print(f"case set: {conditions['case_set_id']}")
    print(f"prompt condition: {conditions['prompt_condition_id']}")
    print(f"adapter condition: {conditions['adapter_id']}")
    print(f"fingerprint input hash: {report['input_hash']}")
    print()
    print("## Model fingerprints")
    print()
    print(f"{'model_id':<18} {'attempts':>8} {'pass':>5} {'fail':>5}  {'dominant_failure':<24} distribution")
    for model in report["models"]:
        distribution = ", ".join(
            f"{family}={count}" for family, count in model["family_counts"].items()
        ) or "none"
        dominant = model["dominant_family"] or "none"
        print(
            f"{model['model_id']:<18} {model['attempts']:>8} "
            f"{model['pass_count']:>5} {model['fail_count']:>5}  "
            f"{dominant:<24} {distribution}"
        )
    print()
    print("## Interpretation")
    print()
    print("Fingerprints are conditioned on this fixture pack, prompt/adapter condition, and taxonomy.")
    print("These are illustrative fixture results, not live model benchmark claims or absolute model behaviour.")
    print(f"sealed occurrences re-derived: {len(occurrences)}")
    if issues:
        for issue in issues:
            print(f"integrity issue: {issue['code']} - {issue['detail']}")
    print()
    print(f"final status: {'PASS' if not issues else 'FAIL'}")
    return 0 if not issues else 2


if __name__ == "__main__":
    sys.exit(main())
