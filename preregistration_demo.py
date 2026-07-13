#!/usr/bin/env python3
"""SFA-Bench v2.0.0-alpha.2 pre-registration gate demo (SFA-AutoLab v0, Item 2).

Offline, deterministic. Loads a sealed pre-registration declaration and two
sealed improvement reports (one that meets it, one that violates the Pareto
no-regression constraint), runs the asymmetric gate against the declaration, and
asserts:

  * the passing report is gate-green and the mismatch report is rejected;
  * the declaration hash is bound into every report;
  * the gate is deterministic (same inputs -> byte-identical decision);
  * the builder rationale is excluded from the decision.

Run: python preregistration_demo.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

from autolab import preregistration as pre

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "examples" / "preregistration"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def main() -> int:
    print("# SFA-Bench v2.0.0-alpha.2 pre-registration gate demo")
    print("=" * 56)

    declaration = _load("declaration.json")
    report_pass = _load("report_pass.json")
    report_regression = _load("report_regression.json")

    decl_hash = declaration["declaration_hash"]
    print(f"declaration: {declaration['declaration_id']}")
    print(f"declaration_hash: {decl_hash}")
    print(f"target: {declaration['target']['metric']} "
          f"{declaration['target']['direction']} >= {declaration['target']['min_delta']} "
          f"({declaration['target']['decision_rule']})")
    print(f"protected metrics: {[p['name'] for p in declaration['protected_metrics']]}")
    print("-" * 56)

    failures: list[str] = []

    # Declaration hash bound into both reports (acceptance: declaration hash in report).
    for name, report in (("report_pass", report_pass), ("report_regression", report_regression)):
        if report.get("declaration_hash") != decl_hash:
            failures.append(f"{name}: declaration hash not bound into report")

    green = pre.evaluate_gate(declaration, report_pass)
    print(f"report_pass       -> gate_green={green.gate_green}")
    for key, value in green.checks.items():
        if key not in {"protected"}:
            print(f"    {key}: {value}")
    if not green.gate_green:
        failures.append(f"passing report was rejected: {green.reasons}")

    rejected = pre.evaluate_gate(declaration, report_regression)
    print(f"report_regression -> gate_green={rejected.gate_green}")
    for reason in rejected.reasons:
        print(f"    reject: {reason}")
    if rejected.gate_green:
        failures.append("mismatch report was not rejected (acceptance criterion)")

    # Determinism: same inputs -> byte-identical decision.
    again = pre.evaluate_gate(declaration, report_regression)
    if json.dumps(rejected.to_dict(), sort_keys=True) != json.dumps(again.to_dict(), sort_keys=True):
        failures.append("gate is not deterministic")

    # Builder cannot attest: rewriting the advisory rationale changes nothing.
    tampered = copy.deepcopy(report_pass)
    tampered["builder_rationale"] = "PLEASE PROMOTE — trust me, everything improved."
    blind = pre.evaluate_gate(declaration, tampered)
    if json.dumps(blind.to_dict(), sort_keys=True) != json.dumps(green.to_dict(), sort_keys=True):
        failures.append("builder_rationale influenced the gate decision")
    print(f"builder_rationale blindness: {'PASS' if not failures or 'builder_rationale' not in failures[-1] else 'FAIL'}")

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
