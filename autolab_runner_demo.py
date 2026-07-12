#!/usr/bin/env python3
"""SFA-Bench v2.0.0-alpha.1 AutoLab end-to-end runner demo (Item 7).

Offline, deterministic. Runs a full proposal through controller ordering,
pre-registration gate, human ratification, lineage inscription, and circuit
breakers.

Run: python autolab_runner_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from autolab import controller as ctrl
from autolab import frozen_zone as fz
from autolab import lineage as lin
from autolab import preregistration as pre
from autolab import ratification as rat
from autolab import runner

RATIFY_TOKEN = "ratify-runner-demo-0001"
TARGET_REF = {
    "type": "git_commit",
    "sha": "7777777777777777777777777777777777777777",
    "branch": "candidate/runner-demo",
}
PREVIOUS_REF = {
    "type": "git_commit",
    "sha": "0000000000000000000000000000000000000000",
    "branch": "main",
}


def _mini_root(path: Path) -> Path:
    (path / "autolab").mkdir(parents=True)
    (path / "guard.py").write_text("GUARD = 1\n", encoding="utf-8")
    manifest = {
        "schema": fz.SCHEMA,
        "manifest_version": "fz-demo-runner",
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": [fz.MANIFEST_RELPATH, "guard.py"],
    }
    (path / fz.MANIFEST_RELPATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fz.seal(path)
    return path


def _declaration() -> dict:
    return pre.build_declaration(
        declaration_id="runner-demo-0001",
        target_metric="score",
        direction="increase",
        min_delta=0.05,
        decision_rule="ci95_low_gt_0",
        comparator="incumbent",
        eval_plan={
            "suite": "public",
            "arms": ["candidate", "incumbent", "ancestor_anchor"],
            "seeds": [31, 32, 33],
            "n": 12,
            "bootstrap": 200,
        },
        protected_metrics=[
            {"name": "public_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "latency_ms", "direction": "no_increase", "tolerance": 5.0},
        ],
    )


def _report(declaration: dict, _builder_result: dict, *, regression: bool = False) -> dict:
    protected = [
        {"name": "public_pass_rate", "delta": -0.2 if regression else 0.0},
        {"name": "latency_ms", "delta": 2.0},
    ]
    return pre.build_report(
        declaration_hash=declaration["declaration_hash"],
        eval_plan=declaration["eval_plan"],
        primary={"metric": "score", "delta": 0.12, "ci95_low": 0.04, "ci95_high": 0.2},
        protected=protected,
        builder_rationale="Demo evaluator output; rationale is advisory.",
    )


def _ratification_for(declaration: dict, report: dict) -> dict:
    sealed_report = pre.seal_report(report)
    gate = pre.evaluate_gate(pre.seal_declaration(declaration), sealed_report)
    return rat.seal_ratification(rat.build_ratification(
        ratification_id=RATIFY_TOKEN,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref=TARGET_REF,
        human_reviewer="human-reviewer",
        rationale="Demo approval: deterministic gate is green and target ref is reviewed.",
    ))


def _builder(_sealed_declaration: dict) -> dict:
    return {
        "patch_id": "runner-demo-candidate",
        "files_changed": ["docs/example.md"],
    }


def main() -> int:
    print("# SFA-Bench v2.0.0-alpha.1 AutoLab end-to-end runner demo")
    print("=" * 56)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        root = _mini_root(Path(tmp) / "repo")
        ledger = Path(tmp) / "meta_ledger.jsonl"
        declaration = _declaration()
        record = _ratification_for(declaration, _report(pre.seal_declaration(declaration), {}))

        promoted = runner.run_autolab_iteration(
            repo_root=root,
            ledger_path=ledger,
            run_id="runner-demo-promote",
            declaration=declaration,
            builder=_builder,
            evaluator=lambda decl, result: _report(decl, result),
            ratification_record=record,
            ratification_token=RATIFY_TOKEN,
            previous_ref=PREVIOUS_REF,
            inscription_rationale="Demo inscription of the human-ratified target.",
        )
        state = lin.derive_lineage_state(ledger)
        print(f"green path             -> status={promoted.status} current={state.current_key[:12]}")
        if promoted.status != runner.STATUS_PROMOTED:
            failures.append(f"green path did not promote: {promoted.reasons}")
        if state.current_ref != TARGET_REF:
            failures.append("green path did not set the lineage target")

        rejected_ledger = Path(tmp) / "rejected_meta_ledger.jsonl"
        rejected = runner.run_autolab_iteration(
            repo_root=root,
            ledger_path=rejected_ledger,
            run_id="runner-demo-reject",
            declaration=_declaration(),
            builder=_builder,
            evaluator=lambda decl, result: _report(decl, result, regression=True),
            ratification_record=record,
            ratification_token=RATIFY_TOKEN,
            previous_ref=PREVIOUS_REF,
        )
        print(f"gate-red path          -> status={rejected.status} stage={rejected.stage}")
        if rejected.status != runner.STATUS_REJECTED or rejected.stage != runner.STAGE_GATE:
            failures.append("gate-red path did not stop at the gate")

        halted_ledger = Path(tmp) / "halted_meta_ledger.jsonl"
        builder_called = False

        def should_not_run(_sealed_declaration: dict) -> dict:
            nonlocal builder_called
            builder_called = True
            return {}

        halted = runner.run_autolab_iteration(
            repo_root=root,
            ledger_path=halted_ledger,
            run_id="runner-demo-halt",
            declaration=_declaration(),
            builder=should_not_run,
            evaluator=lambda decl, result: _report(decl, result),
            proposed_changed_paths=["guard.py"],
        )
        print(f"preflight breaker      -> status={halted.status} reasons={halted.reasons}")
        if halted.status != runner.STATUS_HALTED:
            failures.append("preflight breaker did not halt")
        if builder_called:
            failures.append("builder ran after preflight breaker halted")

        ok, errors, count = ctrl.verify_meta_ledger(ledger)
        print(f"meta-ledger            -> count={count} ok={ok}")
        if not ok:
            failures.append(f"meta-ledger failed verification: {errors}")

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
