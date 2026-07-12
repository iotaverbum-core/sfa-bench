#!/usr/bin/env python3
"""SFA-Bench v2.0.0-alpha.1 AutoLab lineage + rollback demo (Item 5).

Offline, deterministic. Loads sealed pre-registration fixtures, appends a
human-ratified promotion, inscribes it into append-only lineage, then shows that
rollback requires a sealed human rollback record plus a matching rollback token.

Run: python lineage_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from autolab import controller as ctrl
from autolab import lineage as lin
from autolab import preregistration as pre
from autolab import ratification as rat

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "examples" / "preregistration"
RATIFY_TOKEN = "ratify-lineage-demo-0001"
ROLLBACK_TOKEN = "rollback-lineage-demo-0001"
TARGET_REF = {
    "type": "git_commit",
    "sha": "1111111111111111111111111111111111111111",
    "branch": "candidate/lineage-demo",
}
PREVIOUS_REF = {
    "type": "git_commit",
    "sha": "0000000000000000000000000000000000000000",
    "branch": "main",
}


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ratification_for(declaration: dict, report: dict) -> dict:
    gate = pre.evaluate_gate(declaration, report)
    return rat.seal_ratification(rat.build_ratification(
        ratification_id=RATIFY_TOKEN,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref=TARGET_REF,
        human_reviewer="human-reviewer",
        rationale="Demo approval: deterministic gate is green and target ref is reviewed.",
    ))


def _rollback() -> dict:
    return lin.seal_rollback(lin.build_rollback(
        rollback_id=ROLLBACK_TOKEN,
        target_ref=TARGET_REF,
        restore_ref=PREVIOUS_REF,
        human_reviewer="human-reviewer",
        reason="Demo rollback to the last reviewed baseline.",
    ))


def main() -> int:
    print("# SFA-Bench v2.0.0-alpha.1 AutoLab lineage + rollback demo")
    print("=" * 56)

    declaration = _load("declaration.json")
    report = _load("report_pass.json")
    record = _ratification_for(declaration, report)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "meta_ledger.jsonl"
        promotion = rat.append_promotion(
            ledger,
            run_id="lineage-demo-ratification",
            declaration=declaration,
            report=report,
            ratification=record,
            ratification_token=RATIFY_TOKEN,
        )
        inscription = lin.append_promotion_inscription(
            ledger,
            run_id="lineage-demo-inscription",
            promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
            previous_ref=PREVIOUS_REF,
            rationale="Demo inscription of the human-ratified target.",
        )
        state = lin.derive_lineage_state(ledger)
        print(f"promotion inscription -> event={inscription['event_type']} current={state.current_key[:12]}")
        if state.current_ref != TARGET_REF:
            failures.append("promotion inscription did not set the current target")

        try:
            lin.append_rollback(
                ledger,
                run_id="lineage-demo-rollback-missing-token",
                rollback=_rollback(),
                rollback_token=None,
            )
        except lin.LineageError as exc:
            print(f"rollback without token -> rejected ({exc})")
        else:
            failures.append("rollback without a human token was appended")

        rollback_entry = lin.append_rollback(
            ledger,
            run_id="lineage-demo-rollback",
            rollback=_rollback(),
            rollback_token=ROLLBACK_TOKEN,
        )
        state = lin.derive_lineage_state(ledger)
        ok, errors, count = ctrl.verify_meta_ledger(ledger)
        print(f"rollback with token    -> event={rollback_entry['event_type']} current={state.current_key[:12]}")
        print(f"meta-ledger            -> count={count} ok={ok}")
        if not ok:
            failures.append(f"meta-ledger failed verification: {errors}")
        if state.current_ref != PREVIOUS_REF:
            failures.append("rollback did not restore the previous ref")

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
