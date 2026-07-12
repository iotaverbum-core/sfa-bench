#!/usr/bin/env python3
"""SFA-Bench Deferred-Consequence Task Family CLI.

Offline and deterministic. Generates sealed deferred-consequence cases (premise at
T, update at T+u, query binding at T+k) and demonstrates that the deterministic
verifier scores them with zero LLM involvement: the propagated answer passes and
the stale answer fails as the ``deferred_consequence_stale`` family.

  python deferred_consequence.py                       # generate + determinism + scoring demo
  python deferred_consequence.py --seed 20260301 --per-cell 2 --out pack.json
  python deferred_consequence.py replay pack.json      # offline deterministic replay
"""
from __future__ import annotations

import argparse
import json
import sys

from sfa import deferred_consequence as dc


def _print_summary(pack: dict, correct_pass: int, stale_fail: int, stale_family_ok: bool) -> None:
    cfg = pack["config"]
    print(f"seed: {cfg['seed']}  skins: {cfg['skins']}  horizons: {cfg['horizons']}  "
          f"per_cell: {cfg['per_cell']}")
    print(f"cases: {pack['case_count']}  cases_root_hash: {pack['cases_root_hash']}")
    print(f"scoring (verifier, zero LLM): correct->PASS {correct_pass}/{pack['case_count']}  "
          f"stale->FAIL {stale_fail}/{pack['case_count']}")
    print(f"stale answers classify to deferred_consequence_stale: {stale_family_ok}")
    print(f"pack_hash: {pack['pack_hash']}")


def _run_replay(path: str) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        pack = json.load(fh)
    result = dc.replay(pack)
    print("SFA-Bench v2.0.0-alpha.1 Deferred-Consequence Task Family - replay")
    print("=" * 58)
    print(f"pack_hash (re-derived): {result['pack_hash']}")
    for issue in result["issues"]:
        print(f"  - {issue}")
    print("=" * 58)
    print(f"final status: {'ATTESTED' if result['attested'] else 'FAILED'}")
    return 0 if result["attested"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="run", choices=["run", "replay"])
    parser.add_argument("report", nargs="?", help="pack path (for replay)")
    parser.add_argument("--seed", type=int, default=dc.DEFAULT_SEED)
    parser.add_argument("--per-cell", type=int, default=1,
                        help="cases per (skin, horizon) cell")
    parser.add_argument("--out", help="write the sealed pack JSON to this path")
    args = parser.parse_args(argv)

    if args.mode == "replay":
        if not args.report:
            parser.error("replay requires a pack path")
        return _run_replay(args.report)

    print("SFA-Bench v2.0.0-alpha.1 Deferred-Consequence Task Family")
    print("=" * 58)

    config = {"seed": args.seed, "per_cell": args.per_cell}
    pack = dc.generate_pack(config)

    # Determinism check (the CI dry-run assertion): same config -> same bytes.
    again = dc.generate_pack(config)
    deterministic = again["pack_hash"] == pack["pack_hash"]
    replayed = dc.replay(pack)

    # Zero-LLM scoring demonstration + gold isolation over every sealed case.
    correct_pass = 0
    stale_fail = 0
    stale_family_ok = True
    gold_isolated = True
    for case in pack["cases"]:
        if not dc.proposer_view_is_gold_isolated(case):
            gold_isolated = False
        if dc.score_candidate(case, dc.correct_candidate(case))["status"] == "PASS":
            correct_pass += 1
        stale = dc.score_candidate(case, dc.stale_candidate(case))
        if stale["status"] == "FAIL":
            stale_fail += 1
        if stale["family"] != dc.STALE_FAMILY:
            stale_family_ok = False

    _print_summary(pack, correct_pass, stale_fail, stale_family_ok)
    print(f"determinism: {'PASS' if deterministic else 'FAIL'}")
    print(f"replay: {'PASS' if replayed['attested'] else 'FAIL'}")
    print(f"gold isolation (proposer view carries no scoring fact): {'PASS' if gold_isolated else 'FAIL'}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(pack, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        print(f"wrote {args.out}")

    print("=" * 58)
    ok = (
        deterministic
        and replayed["attested"]
        and gold_isolated
        and stale_family_ok
        and correct_pass == pack["case_count"]
        and stale_fail == pack["case_count"]
    )
    print(f"final status: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
