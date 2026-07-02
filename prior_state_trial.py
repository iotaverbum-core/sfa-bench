#!/usr/bin/env python3
"""SFA-Bench Prior State Trial CLI.

Offline by default (deterministic stub proposer). Live model runs are only
performed behind an explicit --live flag with a user-supplied adapter/key, never
in CI.

  python prior_state_trial.py                      # deterministic stub dry-run + determinism check
  python prior_state_trial.py --n 30 --arms true,placebo,baseline --out report.json
  python prior_state_trial.py replay report.json   # offline deterministic replay
  python prior_state_trial.py --model gpt-x --live # requires a user-supplied live adapter (not in CI)
"""
from __future__ import annotations

import argparse
import json
import sys

from sfa import prior_state_trial as trial

_ARM_ALIASES = {"true": "true_prior", "placebo": "placebo_prior", "baseline": "baseline"}


def _parse_arms(raw: str) -> list[str]:
    arms = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        arms.append(_ARM_ALIASES.get(token, token))
    return arms


def _print_summary(report: dict) -> None:
    print(f"model: {report['config']['model_id']}  seed: {report['config']['seed']}  "
          f"n: {report['config']['n']}")
    for arm, stats in report["arms"].items():
        print(f"  {arm:<14} mean_score={stats['mean_score']:.3f}  passes={stats['passes']}/{stats['n']}")
    head = report.get("headline")
    if head:
        print(f"headline (true_prior - placebo): delta={head['delta_mean']:.3f}  "
              f"95% CI [{head['ci95_low']:.3f}, {head['ci95_high']:.3f}]  "
              f"significant={head['significant']}")
    print(f"report_sha: {report['report_sha']}")


def _run_replay(path: str) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    result = trial.replay(report)
    print("SFA-Bench v1.1.0 Prior State Trial - replay")
    print("=" * 56)
    print(f"report_sha (re-derived): {result['report_sha']}")
    for issue in result["issues"]:
        print(f"  - {issue}")
    print("=" * 56)
    print(f"final status: {'ATTESTED' if result['attested'] else 'FAILED'}")
    return 0 if result["attested"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="run", choices=["run", "replay"])
    parser.add_argument("report", nargs="?", help="report path (for replay)")
    parser.add_argument("--model", default=trial.STUB_MODEL_ID)
    parser.add_argument("--n", type=int, default=trial.DEFAULT_N)
    parser.add_argument("--arms", default="true,placebo,baseline")
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--bootstrap", type=int, default=trial.DEFAULT_BOOTSTRAP)
    parser.add_argument("--out", help="write the sealed report JSON to this path")
    parser.add_argument("--live", action="store_true",
                        help="use a live model (requires a user-supplied adapter/key; never in CI)")
    args = parser.parse_args(argv)

    if args.mode == "replay":
        if not args.report:
            parser.error("replay requires a report path")
        return _run_replay(args.report)

    print("SFA-Bench v1.1.0 Prior State Trial")
    print("=" * 56)

    if args.live:
        # Fail closed: no live provider is bundled; live runs are the caller's, offline CI stays green.
        print("live mode requested but no live adapter is configured.")
        print("Provide a user-supplied model adapter + key (see docs/prior-state-trial.md);")
        print("live runs are never executed in CI.")
        return 2

    config = {
        "model_id": args.model,
        "seed": args.seed,
        "n": args.n,
        "arms": _parse_arms(args.arms),
        "bootstrap": args.bootstrap,
    }
    report = trial.run_trial(config)

    # Determinism check (this is the CI dry-run assertion): same config -> same bytes.
    again = trial.run_trial(config)
    deterministic = again["report_sha"] == report["report_sha"]
    replayed = trial.replay(report)

    _print_summary(report)
    print(f"determinism: {'PASS' if deterministic else 'FAIL'}")
    print(f"replay: {'PASS' if replayed['attested'] else 'FAIL'}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        print(f"wrote {args.out}")

    print("=" * 56)
    ok = deterministic and replayed["attested"]
    print(f"final status: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
