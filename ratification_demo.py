#!/usr/bin/env python3
"""SFA-Bench v1.1.0 AutoLab human ratification demo (Item 4).

Offline, deterministic. Loads the sealed pre-registration fixtures, recomputes
the deterministic gate, then requires a sealed human ratification record and
matching token before appending a promotion event to a temporary meta-ledger.

Run: python ratification_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from autolab import controller as ctrl
from autolab import preregistration as pre
from autolab import ratification as rat

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "examples" / "preregistration"
TOKEN = "ratify-demo-0001"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ratification_for(declaration: dict, report: dict) -> dict:
    gate = pre.evaluate_gate(declaration, report)
    return rat.seal_ratification(rat.build_ratification(
        ratification_id=TOKEN,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref={
            "type": "git_commit",
            "sha": "0123456789abcdef0123456789abcdef01234567",
            "branch": "candidate/ratification-demo",
        },
        human_reviewer="human-reviewer",
        rationale="Demo approval: deterministic gate is green and target ref is reviewed.",
    ))


def main() -> int:
    print("# SFA-Bench v1.1.0 AutoLab human ratification demo")
    print("=" * 56)

    declaration = _load("declaration.json")
    report_pass = _load("report_pass.json")
    report_regression = _load("report_regression.json")
    record = _ratification_for(declaration, report_pass)

    failures: list[str] = []

    no_token = rat.evaluate_promotion(declaration, report_pass, record, ratification_token=None)
    print(f"gate-green without token -> promoted={no_token.promoted}")
    if no_token.promoted:
        failures.append("gate-green report promoted without a human token")

    approved = rat.evaluate_promotion(declaration, report_pass, record, ratification_token=TOKEN)
    print(f"gate-green with token    -> promoted={approved.promoted}")
    if not approved.promoted:
        failures.append(f"approved report was not promoted: {approved.reasons}")

    red_record = _ratification_for(declaration, report_regression)
    red = rat.evaluate_promotion(declaration, report_regression, red_record, ratification_token=TOKEN)
    print(f"gate-red with token      -> promoted={red.promoted}")
    if red.promoted:
        failures.append("red gate was promoted by human token")

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "meta_ledger.jsonl"
        entry = rat.append_promotion(
            ledger,
            run_id="ratification-demo-run",
            declaration=declaration,
            report=report_pass,
            ratification=record,
            ratification_token=TOKEN,
        )
        ok, errors, count = ctrl.verify_meta_ledger(ledger)
        print(f"meta-ledger append       -> event={entry['event_type']} count={count} ok={ok}")
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
