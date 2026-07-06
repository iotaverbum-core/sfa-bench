#!/usr/bin/env python3
"""SFA-Bench v1.1.0 AutoLab controller demo (SFA-AutoLab v0, Item 3).

Offline, deterministic. Runs one controller iteration with a temporary
meta-ledger and a fake builder callback. The demo asserts:

  * the pre-registration declaration is sealed into the meta-ledger before the
    builder callback runs;
  * the holdout budget receipt is also appended before builder invocation;
  * the bounded holdout budget rejects a second attempted consumption; and
  * the frozen-zone hash is equal before and after the iteration.

Run: python autolab_controller_demo.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

from autolab import controller as ctrl
from autolab import preregistration as pre

ROOT = Path(__file__).resolve().parent


def _declaration() -> dict:
    return pre.build_declaration(
        declaration_id="controller-demo-0001",
        target_metric="continual_learning_score",
        direction="increase",
        min_delta=0.05,
        decision_rule="ci95_low_gt_0",
        comparator="incumbent",
        eval_plan={
            "suite": "public+holdout",
            "arms": ["candidate", "incumbent", "ancestor_anchor"],
            "seeds": [101, 102, 103],
            "n": 12,
            "bootstrap": 200,
            "harness": "sfa.prior_state_trial.v1",
            "holdout": {
                "budget_id": "frontier-delta-holdout:hd-v0.1.0",
                "suite": "frontier-delta-holdout",
                "version": "hd-v0.1.0",
                "units": 1,
            },
        },
        protected_metrics=[
            {"name": "public_suite_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "holdout_lane_pass_count", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "verifier_latency_ms", "direction": "no_increase", "tolerance": 5.0},
        ],
    )


def _budget(max_uses: int = 1) -> dict:
    return ctrl.build_holdout_budget(
        budget_id="frontier-delta-holdout:hd-v0.1.0",
        suite="frontier-delta-holdout",
        version="hd-v0.1.0",
        max_uses=max_uses,
    )


def _events(path: Path) -> list[str]:
    return [entry["event_type"] for entry in ctrl.read_meta_ledger(path)]


def main() -> int:
    print("# SFA-Bench v1.1.0 AutoLab controller demo")
    print("=" * 56)

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "meta_ledger.jsonl"
        seen_inside_builder: list[str] = []

        def builder(sealed_declaration: dict) -> dict:
            seen_inside_builder.extend(_events(ledger))
            return {
                "patch_id": "demo-candidate",
                "declaration_hash": sealed_declaration["declaration_hash"],
                "files_changed": [],
            }

        result = ctrl.run_iteration(
            repo_root=ROOT,
            ledger_path=ledger,
            run_id="controller-demo-run",
            declaration=_declaration(),
            builder=builder,
            holdout_budget=_budget(max_uses=1),
        )

        print(f"declaration_hash: {result.declaration['declaration_hash']}")
        print(f"builder_result_hash: {result.builder_result_hash}")
        print(f"pre_zone_hash: {result.pre_zone_hash}")
        print(f"post_zone_hash: {result.post_zone_hash}")
        print(f"events before builder returned: {seen_inside_builder}")
        print(f"final events: {_events(ledger)}")

        if "declaration_sealed" not in seen_inside_builder:
            failures.append("builder ran before declaration was sealed into the meta-ledger")
        if "holdout_budget_consumed" not in seen_inside_builder:
            failures.append("builder ran before holdout budget was consumed")
        if result.pre_zone_hash != result.post_zone_hash:
            failures.append("frozen-zone hash changed during controller iteration")

        second_builder_called = False

        def second_builder(_sealed_declaration: dict) -> dict:
            nonlocal second_builder_called
            second_builder_called = True
            return {}

        try:
            ctrl.run_iteration(
                repo_root=ROOT,
                ledger_path=ledger,
                run_id="controller-demo-run-2",
                declaration=_declaration(),
                builder=second_builder,
                holdout_budget=_budget(max_uses=1),
            )
            failures.append("second holdout consumption unexpectedly passed")
        except ctrl.ControllerError as exc:
            print(f"bounded holdout rejection: {exc}")
        if second_builder_called:
            failures.append("builder ran after holdout budget was exhausted")

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
