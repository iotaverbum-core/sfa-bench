#!/usr/bin/env python3
"""SFA-Bench v1.1.0 AutoLab meta-ledger + circuit-breaker demo (Item 5).

Offline, deterministic. Inscribes loop outcomes into the append-only, hash-chained
meta-ledger, shows recurrence-fed caution directives and lineage wither, trips
each of the six circuit breakers against a fixture, and shows that a halt holds
until a human restart token clears it.

Run: python meta_ledger_demo.py
"""
from __future__ import annotations

from pathlib import Path
import sys

from autolab import controller as ctrl
from autolab import frozen_zone as fz
from autolab import meta_ledger as ml

ROOT = Path(__file__).resolve().parent


def _breaker_fixture(name):
    """Return a BreakerContext that trips exactly the named breaker."""
    good = ml.BreakerContext()  # nothing tripped
    if name == ml.HALT_ZONE_HASH_MISMATCH:
        return ml.BreakerContext(zone_ok=False)
    if name == ml.HALT_CHAIN_BREAK:
        entries = []
        ml.append_event(entries, event=ml.EVENT_REJECTED, patch_fingerprint="fp")
        ml.append_event(entries, event=ml.EVENT_REJECTED, patch_fingerprint="fp")
        entries[0]["detail"] = {"tampered": True}  # break the chain
        return ml.BreakerContext(entries=entries, max_consecutive_rejections=99)
    if name == ml.HALT_HOLDOUT_BUDGET_EXHAUSTED:
        return ml.BreakerContext(holdout_exhausted=True)
    if name == ml.HALT_CONSECUTIVE_REJECTIONS:
        entries = []
        for _ in range(3):
            ml.append_event(entries, event=ml.EVENT_REJECTED, patch_fingerprint="fp")
        return ml.BreakerContext(entries=entries, max_consecutive_rejections=3)
    if name == ml.HALT_GATE_POLICY_CHANGE:
        return ml.BreakerContext(proposed_changed_paths=["sfa/verifier.py"],
                                 frozen_paths={"sfa/verifier.py"})
    if name == ml.HALT_COST_TIME_BUDGET:
        return ml.BreakerContext(cost_spent=10.0, cost_budget=1.0)
    return good


def main() -> int:
    print("# SFA-Bench v1.1.0 AutoLab meta-ledger + circuit-breaker demo")
    print("=" * 60)
    failures: list[str] = []

    # Inscribe a gate-green iteration and three rejections of one lineage.
    entries: list = []
    green = ctrl.run_iteration({"seed": 20260706, "n": 30, "bootstrap": 500}).record
    ml.inscribe_from_loop(entries, green)
    for _ in range(3):
        ml.append_event(entries, event=ml.EVENT_REJECTED, patch_fingerprint="fp-bad",
                        detail={"reasons": ["protected metric regressed"]})
    ok, errors = ml.verify_chain(entries)
    print(f"meta-ledger: {len(entries)} events, chain ok={ok}")
    if not ok:
        failures.append(f"meta-ledger chain broken: {errors}")

    context = ml.next_proposal_context(entries)
    withered = context["withered_lineages"]
    print(f"caution directives: {len(context['cautions'])}; withered lineages: {withered}")
    print(f"caution advisory (excluded_from_gate): {context['excluded_from_gate']}")
    if "fp-bad" not in withered:
        failures.append("fp-bad lineage did not wither after K rejections")

    # Every breaker trips against its fixture.
    print("-" * 60)
    for name in ml.ALL_HALT_REASONS:
        report = ml.evaluate_breakers(_breaker_fixture(name))
        tripped = name in report["tripped_breakers"]
        print(f"  breaker {name}: {'HALT' if report['halted'] else 'ok'} "
              f"({'tripped' if tripped else 'NOT tripped'})")
        if not (report["halted"] and tripped):
            failures.append(f"breaker {name} did not trip against its fixture")

    # A clean context does not halt.
    clean = ml.evaluate_breakers(ml.BreakerContext())
    print(f"  clean context: {'HALT' if clean['halted'] else 'ok'}")
    if clean["halted"]:
        failures.append("clean context should not halt")

    # Halt-and-hold requires a human restart.
    print("-" * 60)
    report = ml.evaluate_breakers(_breaker_fixture(ml.HALT_CONSECUTIVE_REJECTIONS))
    state = ml.halt(report)
    held = ml.clear_halt(state, None)
    cleared = ml.clear_halt(state, "human-restart-token")
    print(f"halt held without token: {held.halted}")
    print(f"halt cleared with human token: {not cleared.halted} (cleared_by={cleared.cleared_by})")
    if not held.halted:
        failures.append("halt cleared itself without a human token")
    if cleared.halted:
        failures.append("valid human restart token did not clear the halt")

    print("=" * 60)
    if failures:
        for failure in failures:
            print(f"failure: {failure}")
        print("final status: FAIL")
        return 1
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
