#!/usr/bin/env python3
"""SFA-Bench v1.1.0 AutoLab loop-controller demo (SFA-AutoLab v0, Item 3).

Offline, deterministic full dry-run of one loop iteration on the stub builder:

    propose -> public suite -> budgeted holdout -> paired comparison
    -> sealed improvement report -> gate -> PR payload (no promotion)

Asserts: the pipeline runs; the gate decides (a rejecting variant is also shown);
no autonomous promotion path is taken; the frozen zone is intact pre/post; and
the iteration replays byte-for-byte.

Run: python loop_controller_demo.py
"""
from __future__ import annotations

from pathlib import Path
import sys

from autolab import controller as ctrl

ROOT = Path(__file__).resolve().parent
CONFIG = {"seed": 20260706, "n": 30, "bootstrap": 500,
          "min_delta": 0.05, "decision_rule": "ci95_low_gt_0"}


def main() -> int:
    print("# SFA-Bench v1.1.0 AutoLab loop-controller demo")
    print("=" * 56)

    failures: list[str] = []
    result = ctrl.run_iteration(CONFIG, repo_root=ROOT)
    record = result.record

    print(f"builder: {record['proposal']['builder_id']}")
    print(f"patch fingerprint: {record['proposal']['patch_fingerprint']}")
    print("pipeline stages:")
    for stage in record["stages"]:
        print(f"  [{stage['seq']}] {stage['stage']}")
    paired = record["paired_comparison"]
    print(f"paired arms: {paired['arms']}")
    print(f"  arm means: {paired['arm_means']}")
    ci = paired["candidate_minus_incumbent"]
    print(f"  candidate - incumbent: delta={ci['delta_mean']} "
          f"ci95=[{ci['ci95_low']}, {ci['ci95_high']}]")
    holdout = record["budgeted_holdout"]
    print(f"holdout ({holdout['suite_version']}, {holdout['granularity']}):")
    print(f"  lane_pass_count={holdout['lane_pass_count']}/{holdout['lanes']} "
          f"aggregate_delta={holdout['aggregate_delta']}")
    print(f"  seeds_consumed={holdout['seeds_consumed']} "
          f"budget_remaining={holdout['budget_remaining']}")
    print(f"gate_green: {record['gate']['gate_green']}")
    print(f"promotion: promoted={record['promotion']['promoted']} "
          f"awaiting_human_ratification={record['promotion']['awaiting_human_ratification']}")
    print(f"zone intact (pre==post): {record['zone_attestation']['zone_intact']}")
    print(f"loop_hash: {record['loop_hash']}")
    print("-" * 56)

    # Assertions (acceptance criteria).
    if not record["gate"]["gate_green"]:
        failures.append(f"stub happy-path iteration was rejected: {record['gate']['reasons']}")
    if record["promotion"]["promoted"]:
        failures.append("controller took an autonomous promotion path (invariant 2)")
    if not record["promotion"]["awaiting_human_ratification"]:
        failures.append("iteration did not defer to human ratification")
    if not record["zone_attestation"]["zone_intact"]:
        failures.append("frozen zone changed during the iteration")
    if "improvement_report" not in record["pr_payload"]["attachments"]:
        failures.append("PR payload does not attach the improvement report")

    # Byte-identical replay.
    replayed = ctrl.replay(record, repo_root=ROOT)
    print(f"replay attested: {replayed['attested']}")
    if not replayed["attested"]:
        failures.append("iteration did not replay byte-for-byte: " + "; ".join(replayed["issues"]))

    # The gate is not a rubber stamp: an underperforming candidate is rejected.
    rejecting = ctrl.run_iteration({**CONFIG, "arm_probabilities": {
        "candidate": 0.30, "incumbent": 0.70, "ancestor_anchor": 0.50}})
    print(f"rejecting variant gate_green: {rejecting.gate_green} "
          f"(promoted={rejecting.record['promotion']['promoted']})")
    if rejecting.gate_green:
        failures.append("an underperforming candidate was not rejected")
    if rejecting.record["promotion"]["promoted"]:
        failures.append("a rejected candidate was promoted")

    print("=" * 56)
    if failures:
        for failure in failures:
            print(f"failure: {failure}")
        print("final status: FAIL")
        return 1
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
