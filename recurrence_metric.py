#!/usr/bin/env python3
"""SFA-Bench Recurrence-Decline Metric CLI.

Computes the continual-learning score - the per-fingerprint recurrence-rate
decline across ledger epochs - entirely offline, as a pure function of the
hash-chained occurrence ledger. No model call, no network.

  python recurrence_metric.py                       # score the synthetic fixture + self-check
  python recurrence_metric.py --ledger history/occurrences.jsonl
  python recurrence_metric.py --ledger my.jsonl --no-verify   # skip chain attestation
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sfa import recurrence_metric as metric

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "examples" / "recurrence" / "synthetic_ledger.jsonl"

# Hand-verifiable expectations for the committed synthetic fixture.
_EXPECTED = {
    "continual_learning_score": 0.375,
    "occurrence_weighted_score": 0.4,
    "eliminated_fingerprints": ["contradicts_evidence"],
}


def _print_report(report: dict) -> None:
    print(f"epochs: {report['epochs']}  occurrences: {report['total_occurrences']}  "
          f"fingerprints: {report['fingerprint_count']}")
    print(f"{'fingerprint':<26} {'series':<16} {'peak':>4} {'final':>5} {'decline':>8} "
          f"{'eliminated':>10} {'monotone':>9}")
    for family in sorted(report["fingerprints"]):
        decline = report["fingerprints"][family]
        series = ",".join(str(c) for c in decline["recurrence_series"])
        print(f"{family:<26} {series:<16} {decline['peak_rate']:>4} {decline['final_rate']:>5} "
              f"{decline['decline_score']:>8.3f} {str(decline['eliminated']):>10} "
              f"{str(decline['monotone_post_peak']):>9}")
    print(f"continual-learning score (mean decline): {report['continual_learning_score']}")
    print(f"occurrence-weighted score:               {report['occurrence_weighted_score']}")
    print(f"eliminated fingerprints: {report['eliminated_fingerprints'] or 'none'}")
    print(f"metric_hash: {report['metric_hash']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", help="path to an occurrence ledger (defaults to the synthetic fixture)")
    parser.add_argument("--no-verify", action="store_true",
                        help="do not attest the ledger hash chain before scoring")
    args = parser.parse_args(argv)

    print("SFA-Bench v1.0.0 Recurrence-Decline Metric")
    print("=" * 58)

    ledger_path = args.ledger or str(FIXTURE)
    is_fixture = args.ledger is None
    try:
        report = metric.compute_from_path(ledger_path, verify=not args.no_verify)
    except metric.RecurrenceMetricError as exc:
        print(f"ledger not scored: {exc}")
        print("=" * 58)
        print("final status: FAIL")
        return 2

    _print_report(report)

    ok = True
    if is_fixture:
        # Determinism + expected-value self-check on the committed fixture.
        again = metric.compute_from_path(ledger_path)
        deterministic = again["metric_hash"] == report["metric_hash"]
        matches = all(report[k] == v for k, v in _EXPECTED.items())
        print(f"determinism: {'PASS' if deterministic else 'FAIL'}")
        print(f"expected fixture values: {'PASS' if matches else 'FAIL'}")
        ok = deterministic and matches

    print("=" * 58)
    print(f"final status: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
