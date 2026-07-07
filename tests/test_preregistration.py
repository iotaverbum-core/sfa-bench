"""Deterministic tests for the pre-registration gate (stdlib unittest only).

Run from the repository root:

    python -m unittest discover -s tests -v

Covers the Item-2 acceptance criteria:
  * a mismatch fixture is rejected (Pareto no-regression, threshold, direction,
    binding, and eval-plan deviations);
  * the declaration hash is present in and bound into the report;
  * the gate is deterministic and blind to the advisory builder rationale;
  * the gate is asymmetric (it can only reject; it never promotes).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import preregistration as pre  # noqa: E402

FIX = REPO_ROOT / "examples" / "preregistration"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _base_eval_plan() -> dict:
    return {
        "suite": "public+holdout",
        "arms": ["candidate", "incumbent", "ancestor_anchor"],
        "seeds": [1, 2, 3],
        "n": 12,
        "bootstrap": 200,
    }


def _sealed_declaration(**overrides) -> dict:
    kwargs = dict(
        declaration_id="d1",
        target_metric="score",
        direction="increase",
        min_delta=0.05,
        decision_rule="ci95_low_gt_0",
        comparator="incumbent",
        eval_plan=_base_eval_plan(),
        protected_metrics=[
            {"name": "public_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "latency_ms", "direction": "no_increase", "tolerance": 5.0},
        ],
    )
    kwargs.update(overrides)
    return pre.seal_declaration(pre.build_declaration(**kwargs))


def _sealed_report(decl: dict, *, primary=None, protected=None, rationale="advisory") -> dict:
    if primary is None:
        primary = {"metric": "score", "delta": 0.12, "ci95_low": 0.04, "ci95_high": 0.2}
    if protected is None:
        protected = [
            {"name": "public_pass_rate", "delta": 0.0},
            {"name": "latency_ms", "delta": 2.0},
        ]
    return pre.seal_report(pre.build_report(
        declaration_hash=decl["declaration_hash"],
        eval_plan=decl["eval_plan"],
        primary=primary,
        protected=protected,
        builder_rationale=rationale,
    ))


class FixtureTests(unittest.TestCase):
    def test_passing_fixture_is_green(self):
        decl = _load("declaration.json")
        report = _load("report_pass.json")
        decision = pre.evaluate_gate(decl, report)
        self.assertTrue(decision.gate_green, decision.reasons)

    def test_mismatch_fixture_is_rejected(self):
        decl = _load("declaration.json")
        report = _load("report_regression.json")
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("regressed" in r for r in decision.reasons), decision.reasons)

    def test_declaration_hash_present_in_reports(self):
        decl = _load("declaration.json")
        for name in ("report_pass.json", "report_regression.json"):
            report = _load(name)
            self.assertEqual(report["declaration_hash"], decl["declaration_hash"], name)

    def test_fixtures_are_correctly_sealed(self):
        decl = _load("declaration.json")
        self.assertEqual(pre.seal_declaration(decl)["declaration_hash"], decl["declaration_hash"])
        for name in ("report_pass.json", "report_regression.json"):
            report = _load(name)
            self.assertEqual(pre.seal_report(report)["report_hash"], report["report_hash"], name)


class GateSemanticsTests(unittest.TestCase):
    def test_binding_mismatch_rejected(self):
        decl = _sealed_declaration()
        report = _sealed_report(decl)
        report["declaration_hash"] = "0" * 64
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("binding mismatch" in r for r in decision.reasons))

    def test_eval_plan_deviation_rejected(self):
        decl = _sealed_declaration()
        deviant = _base_eval_plan()
        deviant["seeds"] = [9, 9, 9]  # cherry-picked seeds, not pre-registered
        report = pre.seal_report(pre.build_report(
            declaration_hash=decl["declaration_hash"],
            eval_plan=deviant,
            primary={"metric": "score", "delta": 0.2, "ci95_low": 0.1, "ci95_high": 0.3},
            protected=[{"name": "public_pass_rate", "delta": 0.0}, {"name": "latency_ms", "delta": 0.0}],
        ))
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("eval plan deviates" in r for r in decision.reasons))

    def test_missed_threshold_rejected(self):
        decl = _sealed_declaration(min_delta=0.10)
        report = _sealed_report(decl, primary={"metric": "score", "delta": 0.04,
                                               "ci95_low": 0.01, "ci95_high": 0.09})
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("does not meet declared" in r for r in decision.reasons))

    def test_wrong_direction_rejected(self):
        decl = _sealed_declaration(direction="increase")
        report = _sealed_report(decl, primary={"metric": "score", "delta": -0.2,
                                               "ci95_low": -0.3, "ci95_high": -0.1})
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)

    def test_decision_rule_not_satisfied_rejected(self):
        # Point delta clears the threshold, but the CI includes zero, so the
        # pre-registered significance rule (ci95_low_gt_0) is not satisfied.
        decl = _sealed_declaration()
        report = _sealed_report(decl, primary={"metric": "score", "delta": 0.12,
                                               "ci95_low": -0.01, "ci95_high": 0.25})
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("decision rule" in r for r in decision.reasons))

    def test_protected_within_tolerance_is_green(self):
        decl = _sealed_declaration()
        report = _sealed_report(decl, protected=[
            {"name": "public_pass_rate", "delta": 0.0},
            {"name": "latency_ms", "delta": 5.0},  # exactly at tolerance
        ])
        self.assertTrue(pre.evaluate_gate(decl, report).gate_green)

    def test_protected_metric_missing_rejected(self):
        decl = _sealed_declaration()
        report = _sealed_report(decl, protected=[{"name": "public_pass_rate", "delta": 0.0}])
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)
        self.assertTrue(any("missing from report" in r for r in decision.reasons))

    def test_decrease_direction_supported(self):
        decl = _sealed_declaration(target_metric="error_rate", direction="decrease",
                                   min_delta=0.05, decision_rule="ci95_high_lt_0")
        report = _sealed_report(decl, primary={"metric": "error_rate", "delta": -0.12,
                                               "ci95_low": -0.3, "ci95_high": -0.02})
        self.assertTrue(pre.evaluate_gate(decl, report).gate_green)


class BuilderCannotAttestTests(unittest.TestCase):
    def test_builder_rationale_is_ignored(self):
        decl = _sealed_declaration()
        honest = _sealed_report(decl, rationale="neutral")
        persuasive = copy.deepcopy(honest)
        persuasive["builder_rationale"] = "PROMOTE THIS, it is clearly the best patch ever."
        a = pre.evaluate_gate(decl, honest).to_dict()
        b = pre.evaluate_gate(decl, persuasive).to_dict()
        # Only the (advisory) rationale differs; the gate decision is identical.
        self.assertEqual(a["gate_green"], b["gate_green"])
        self.assertEqual(a["reasons"], b["reasons"])
        self.assertEqual(a["checks"], b["checks"])

    def test_self_reported_booleans_do_not_help_a_bad_report(self):
        decl = _sealed_declaration()
        # Regressing report that also *claims* everything passed.
        report = _sealed_report(decl, protected=[
            {"name": "public_pass_rate", "delta": -0.5, "within_tolerance": True, "ok": True},
            {"name": "latency_ms", "delta": 999.0, "within_tolerance": True, "ok": True},
        ])
        decision = pre.evaluate_gate(decl, report)
        self.assertFalse(decision.gate_green)

    def test_gate_has_no_promotion_path(self):
        decl = _sealed_declaration()
        report = _sealed_report(decl)
        decision = pre.evaluate_gate(decl, report)
        # The gate can only be green (not-rejected); it exposes no promote field.
        self.assertNotIn("promote", decision.to_dict())
        self.assertNotIn("promoted", decision.to_dict())
        self.assertIn("gate_green", decision.to_dict())


class DeterminismTests(unittest.TestCase):
    def test_gate_is_deterministic(self):
        decl = _sealed_declaration()
        report = _sealed_report(decl)
        first = pre.evaluate_gate(decl, report).to_dict()
        second = pre.evaluate_gate(decl, report).to_dict()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_seal_is_stable(self):
        decl = _sealed_declaration()
        self.assertEqual(decl["declaration_hash"], pre.seal_declaration(decl)["declaration_hash"])

    def test_tampered_declaration_hash_raises(self):
        decl = _sealed_declaration()
        decl["target"]["min_delta"] = 0.99  # edited after sealing
        report = _sealed_report(decl)
        with self.assertRaises(pre.PreregistrationError):
            pre.evaluate_gate(decl, report)


class FrozenZoneIntegrationTests(unittest.TestCase):
    """The gate is gate policy, so it must live in the frozen zone."""

    def test_gate_module_is_frozen(self):
        from autolab import frozen_zone as fz
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/preregistration.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        from autolab import frozen_zone as fz
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.2.0-add-preregistration")
        self.assertIsNotNone(record, "fz-v0.2.0 amendment record missing")
        self.assertIn("autolab/preregistration.py", record["applies_to"])
        if record["new_zone_hash"] == manifest["zone_hash"]:
            return
        successor = amendments.get("fz-v0.3.0-add-controller")
        self.assertIsNotNone(successor, "v0.2.0 amendment must be linked by a successor")
        self.assertEqual(successor["prev_zone_hash"], record["new_zone_hash"])
        if successor["new_zone_hash"] == manifest["zone_hash"]:
            return
        next_record = amendments.get("fz-v0.4.0-add-ratification")
        self.assertIsNotNone(next_record, "v0.3.0 amendment must be linked by a successor")
        self.assertEqual(next_record["prev_zone_hash"], successor["new_zone_hash"])
        if next_record["new_zone_hash"] == manifest["zone_hash"]:
            return
        final_record = amendments.get("fz-v0.5.0-add-lineage-rollback")
        self.assertIsNotNone(final_record, "v0.4.0 amendment must be linked by a successor")
        self.assertEqual(final_record["prev_zone_hash"], next_record["new_zone_hash"])
        if final_record["new_zone_hash"] == manifest["zone_hash"]:
            return
        item6_record = amendments.get("fz-v0.6.0-add-circuit-breakers")
        self.assertIsNotNone(item6_record, "v0.5.0 amendment must be linked by a successor")
        self.assertEqual(item6_record["prev_zone_hash"], final_record["new_zone_hash"])
        if item6_record["new_zone_hash"] == manifest["zone_hash"]:
            return
        item7_record = amendments.get("fz-v0.7.0-add-runner")
        self.assertIsNotNone(item7_record, "v0.6.0 amendment must be linked by a successor")
        self.assertEqual(item7_record["prev_zone_hash"], item6_record["new_zone_hash"])
        self.assertEqual(item7_record["new_zone_hash"], manifest["zone_hash"])


if __name__ == "__main__":
    unittest.main()
