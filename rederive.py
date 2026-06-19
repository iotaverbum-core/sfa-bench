#!/usr/bin/env python3
"""Re-derive supported transcript fixture verdicts without model calls."""
import os
import sys

from sfa import rederive as rederive_mod


ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print("SFA-Bench v0.7 transcript replay / re-derivation")
    print("=" * 74)
    records = rederive_mod.discover_records(ROOT)
    if not records:
        print("No transcript replay records found.")
        return 1

    all_ok = True
    for record_path in records:
        result = rederive_mod.rederive_record(record_path, ROOT)
        all_ok = all_ok and result.passed
        status = "OK" if result.passed else "FAIL"
        family = result.family if result.family is not None else "none"
        print(f"{result.name:<34} {status:<4} {result.verdict.get('status')} / {family}")
        for issue in result.issues:
            print(f"  XX {issue['code']}: {issue['message']}")

    print("=" * 74)
    print("RE-DERIVED: supported transcript verdicts match sealed normalized inputs." if all_ok else "ALERT: transcript re-derivation mismatch.")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
