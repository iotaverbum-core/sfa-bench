"""Deterministic tests for the meta-ledger + circuit breakers (Item 5).

Run from the repository root:

    python -m unittest discover -s tests -v

Covers the Item-5 acceptance criteria:
  * each of the six circuit breakers trips against a fixture (and a clean context
    does not halt);
  * a K-fail patch lineage withers (terminal);
  * the meta-ledger is append-only and hash-chained;
  * caution directives are advisory (excluded from the gate);
  * a halt holds until a human restart token clears it.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import controller as ctrl  # noqa: E402
from autolab import meta_ledger as ml  # noqa: E402


def _reject(entries, fp="fp", reasons=None):
    return ml.append_event(entries, event=ml.EVENT_REJECTED, patch_fingerprint=fp,
                           detail={"reasons": reasons or ["threshold not met"]})


class LedgerChainTests(unittest.TestCase):
    def test_append_and_verify_chain(self):
        entries: list = []
        ml.append_event(entries, event=ml.EVENT_PROPOSED, patch_fingerprint="a")
        _reject(entries, "b")
        ok, errors = ml.verify_chain(entries)
        self.assertTrue(ok, errors)
        self.assertEqual(entries[0]["prev_hash"], ml.GENESIS)
        self.assertEqual(entries[1]["prev_hash"], entries[0]["entry_hash"])

    def test_edit_breaks_chain(self):
        entries: list = []
        _reject(entries, "a")
        _reject(entries, "b")
        entries[0]["detail"] = {"reasons": ["EDITED"]}
        ok, errors = ml.verify_chain(entries)
        self.assertFalse(ok)
        self.assertTrue(any("hash mismatch" in e for e in errors))

    def test_reorder_breaks_chain(self):
        entries: list = []
        _reject(entries, "a")
        _reject(entries, "b")
        entries[0], entries[1] = entries[1], entries[0]
        self.assertFalse(ml.verify_chain(entries)[0])

    def test_inscribe_from_loop_records_outcome(self):
        entries: list = []
        green = ctrl.run_iteration({"seed": 1, "n": 30, "bootstrap": 300}).record
        entry = ml.inscribe_from_loop(entries, green)
        self.assertEqual(entry["event"], ml.EVENT_PROPOSED)
        self.assertEqual(entry["patch_fingerprint"], green["proposal"]["patch_fingerprint"])

        red = ctrl.run_iteration({"seed": 1, "n": 30, "bootstrap": 300, "arm_probabilities": {
            "candidate": 0.3, "incumbent": 0.7, "ancestor_anchor": 0.5}}).record
        entry2 = ml.inscribe_from_loop(entries, red)
        self.assertEqual(entry2["event"], ml.EVENT_REJECTED)
        self.assertTrue(entry2["detail"]["reasons"])


class WitherTests(unittest.TestCase):
    def test_lineage_withers_at_k(self):
        entries: list = []
        _reject(entries, "fp-A")
        _reject(entries, "fp-A")
        self.assertFalse(ml.is_withered(entries, "fp-A", k=3))
        _reject(entries, "fp-A")
        self.assertTrue(ml.is_withered(entries, "fp-A", k=3))

    def test_wither_is_terminal(self):
        entries: list = []
        for _ in range(5):
            _reject(entries, "fp-A")
        # More rejections keep it withered; there is no un-wither.
        self.assertTrue(ml.is_withered(entries, "fp-A", k=3))
        directive = next(d for d in ml.caution_directives(entries, k=3) if d["lineage_id"] == "fp-A")
        self.assertTrue(directive["withered"])
        self.assertIn("TERMINAL", directive["directive"])

    def test_distinct_lineages_counted_separately(self):
        entries: list = []
        _reject(entries, "fp-A")
        _reject(entries, "fp-B")
        self.assertEqual(ml.rejection_counts(entries), {"fp-A": 1, "fp-B": 1})
        self.assertFalse(ml.is_withered(entries, "fp-A", k=3))


class CautionContextTests(unittest.TestCase):
    def test_context_is_advisory_and_gate_excluded(self):
        entries: list = []
        _reject(entries, "fp-A", ["bad grounding"])
        context = ml.next_proposal_context(entries)
        self.assertTrue(context["advisory"])
        self.assertTrue(context["excluded_from_gate"])
        self.assertEqual(context["cautions"][0]["known_failure_reasons"], ["bad grounding"])

    def test_withered_lineages_listed(self):
        entries: list = []
        for _ in range(3):
            _reject(entries, "fp-A")
        self.assertIn("fp-A", ml.next_proposal_context(entries)["withered_lineages"])


class CircuitBreakerTests(unittest.TestCase):
    def test_clean_context_does_not_halt(self):
        self.assertFalse(ml.evaluate_breakers(ml.BreakerContext())["halted"])

    def test_zone_hash_mismatch_breaker(self):
        report = ml.evaluate_breakers(ml.BreakerContext(zone_ok=False))
        self.assertIn(ml.HALT_ZONE_HASH_MISMATCH, report["tripped_breakers"])
        self.assertTrue(report["requires_human_restart"])

    def test_chain_break_breaker(self):
        entries: list = []
        _reject(entries, "a")
        _reject(entries, "b")
        entries[0]["detail"] = {"x": 1}  # tamper
        report = ml.evaluate_breakers(ml.BreakerContext(entries=entries,
                                                        max_consecutive_rejections=99))
        self.assertIn(ml.HALT_CHAIN_BREAK, report["tripped_breakers"])

    def test_holdout_budget_exhausted_breaker(self):
        report = ml.evaluate_breakers(ml.BreakerContext(holdout_exhausted=True))
        self.assertIn(ml.HALT_HOLDOUT_BUDGET_EXHAUSTED, report["tripped_breakers"])

    def test_consecutive_rejections_breaker(self):
        entries: list = []
        for _ in range(3):
            _reject(entries, "fp")
        report = ml.evaluate_breakers(ml.BreakerContext(entries=entries,
                                                        max_consecutive_rejections=3))
        self.assertIn(ml.HALT_CONSECUTIVE_REJECTIONS, report["tripped_breakers"])

    def test_consecutive_rejections_reset_by_success(self):
        entries: list = []
        _reject(entries, "fp")
        _reject(entries, "fp")
        ml.append_event(entries, event=ml.EVENT_PROPOSED, patch_fingerprint="ok")
        _reject(entries, "fp")
        report = ml.evaluate_breakers(ml.BreakerContext(entries=entries,
                                                        max_consecutive_rejections=3))
        self.assertNotIn(ml.HALT_CONSECUTIVE_REJECTIONS, report["tripped_breakers"])

    def test_gate_policy_change_breaker(self):
        report = ml.evaluate_breakers(ml.BreakerContext(
            proposed_changed_paths=["sfa/verifier.py", "docs/x.md"],
            frozen_paths={"sfa/verifier.py", "release_gate.py"}))
        self.assertIn(ml.HALT_GATE_POLICY_CHANGE, report["tripped_breakers"])
        detail = next(t for t in report["tripped"] if t["breaker"] == ml.HALT_GATE_POLICY_CHANGE)
        self.assertEqual(detail["detail"]["frozen_paths_touched"], ["sfa/verifier.py"])

    def test_cost_and_time_budget_breakers(self):
        self.assertIn(ml.HALT_COST_TIME_BUDGET, ml.evaluate_breakers(
            ml.BreakerContext(cost_spent=5, cost_budget=1))["tripped_breakers"])
        self.assertIn(ml.HALT_COST_TIME_BUDGET, ml.evaluate_breakers(
            ml.BreakerContext(time_spent=99, time_budget=10))["tripped_breakers"])

    def test_multiple_breakers_trip_together(self):
        report = ml.evaluate_breakers(ml.BreakerContext(zone_ok=False, holdout_exhausted=True))
        self.assertIn(ml.HALT_ZONE_HASH_MISMATCH, report["tripped_breakers"])
        self.assertIn(ml.HALT_HOLDOUT_BUDGET_EXHAUSTED, report["tripped_breakers"])

    def test_breaker_report_is_deterministic(self):
        ctx = ml.BreakerContext(zone_ok=False)
        self.assertEqual(ml.evaluate_breakers(ctx)["report_hash"],
                         ml.evaluate_breakers(ctx)["report_hash"])


class HaltRestartTests(unittest.TestCase):
    def _halted(self):
        report = ml.evaluate_breakers(ml.BreakerContext(holdout_exhausted=True))
        return ml.halt(report)

    def test_halt_holds_without_token(self):
        held = ml.clear_halt(self._halted(), None)
        self.assertTrue(held.halted)
        self.assertIsNone(held.cleared_by)

    def test_halt_cleared_only_by_human_token(self):
        cleared = ml.clear_halt(self._halted(), "human-restart")
        self.assertFalse(cleared.halted)
        self.assertEqual(cleared.cleared_by, "human-restart")

    def test_no_halt_stays_no_halt(self):
        state = ml.halt(ml.evaluate_breakers(ml.BreakerContext()))
        self.assertFalse(state.halted)


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_meta_ledger_is_frozen(self):
        from autolab import frozen_zone as fz
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/meta_ledger.py", manifest["frozen_paths"])


if __name__ == "__main__":
    unittest.main()
