#!/usr/bin/env python3
"""Run SFA-Bench v0.9 tamper and contamination checks."""
import os
import sys

from sfa import tamper


ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print("SFA-Bench v0.9 Tamper & Contamination Suite")
    print("=" * 48)
    results = []
    total = len(tamper.CHECKS)
    for index, check in enumerate(tamper.CHECKS, start=1):
        label = _progress_label(check)
        print(f"[{index}/{total}] {label}...", flush=True)
        try:
            result = check(ROOT)
        except Exception as exc:  # noqa: BLE001 - report failed checks without hiding later results.
            result = tamper.TamperResult(check.__name__.replace("_", " "), False, str(exc))
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        line = f"{status} {result.name}"
        if result.detail:
            line += f" - {result.detail}"
        print(line)
    print("=" * 48)
    passed = sum(1 for result in results if result.passed)
    print(f"{passed}/{total} tamper checks passed")
    return 0 if passed == total else 2


def _progress_label(check):
    label = check.__name__
    for suffix in ("_detected", "_guard_passed"):
        if label.endswith(suffix):
            label = label[: -len(suffix)]
    return label.replace("_", " ")


if __name__ == "__main__":
    sys.exit(main())
