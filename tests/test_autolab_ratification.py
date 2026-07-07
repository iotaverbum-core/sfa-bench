"""Deterministic tests for AutoLab human ratification (Item 4)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import controller as ctrl  # noqa: E402
from autolab import frozen_zone as fz  # noqa: E402
from autolab import preregistration as pre  # noqa: E402
from autolab import ratification as rat  # noqa: E402

FIX = REPO_ROOT / "examples" / "preregistration"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ratification_for(declaration: dict, report: dict, *, decision: str = "approve") -> dict:
    gate = pre.evaluate_gate(declaration, report)
    return rat.seal_ratification(rat.build_ratification(
        ratification_id="ratify-demo-0001",
        decision=decision,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref={
            "type": "git_commit",
            "sha": "0123456789abcdef0123456789abcdef01234567",
            "branch": "candidate/item-4",
        },
        human_reviewer="human-reviewer",
        rationale="Gate is green and the target ref is approved for promotion.",
    ))


class PromotionSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.declaration = _load("declaration.json")
        self.report_pass = _load("report_pass.json")
        self.report_regression = _load("report_regression.json")
        self.record = _ratification_for(self.declaration, self.report_pass)

    def test_gate_green_plus_human_token_promotes(self):
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            self.record,
            ratification_token="ratify-demo-0001",
        )
        self.assertTrue(decision.promoted, decision.reasons)
        self.assertIn("promoted", decision.to_dict())
        self.assertEqual(decision.ratification_hash, self.record["ratification_hash"])

    def test_gate_green_without_token_does_not_promote(self):
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            self.record,
            ratification_token=None,
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("token missing" in reason for reason in decision.reasons))

    def test_wrong_token_does_not_promote(self):
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            self.record,
            ratification_token="wrong-token",
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("does not match" in reason for reason in decision.reasons))

    def test_gate_red_cannot_be_overridden_by_human_token(self):
        red_record = _ratification_for(self.declaration, self.report_regression)
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_regression,
            red_record,
            ratification_token="ratify-demo-0001",
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("deterministic gate is red" in reason for reason in decision.reasons))

    def test_human_rejection_does_not_promote(self):
        reject = _ratification_for(self.declaration, self.report_pass, decision="reject")
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            reject,
            ratification_token="ratify-demo-0001",
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("not 'approve'" in reason for reason in decision.reasons))

    def test_tampered_ratification_hash_raises(self):
        tampered = dict(self.record)
        tampered["target_ref"] = dict(tampered["target_ref"])
        tampered["target_ref"]["sha"] = "f" * 40
        with self.assertRaises(rat.RatificationError):
            rat.evaluate_promotion(
                self.declaration,
                self.report_pass,
                tampered,
                ratification_token="ratify-demo-0001",
            )

    def test_resealed_wrong_gate_hash_is_rejected(self):
        wrong = dict(self.record)
        wrong["gate_decision_hash"] = "0" * 64
        wrong = rat.seal_ratification(wrong)
        decision = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            wrong,
            ratification_token="ratify-demo-0001",
        )
        self.assertFalse(decision.promoted)
        self.assertTrue(any("gate_decision_hash" in reason for reason in decision.reasons))

    def test_decision_is_deterministic(self):
        a = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            self.record,
            ratification_token="ratify-demo-0001",
        ).to_dict()
        b = rat.evaluate_promotion(
            self.declaration,
            self.report_pass,
            self.record,
            ratification_token="ratify-demo-0001",
        ).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_builder_self_reported_booleans_do_not_help_bad_report(self):
        bad = dict(self.report_regression)
        bad["protected"] = [dict(p, ok=True, within_tolerance=True) for p in bad["protected"]]
        bad = pre.seal_report(bad)
        bad_record = _ratification_for(self.declaration, bad)
        decision = rat.evaluate_promotion(
            self.declaration,
            bad,
            bad_record,
            ratification_token="ratify-demo-0001",
        )
        self.assertFalse(decision.promoted)


class MetaLedgerIntegrationTests(unittest.TestCase):
    def test_successful_promotion_appends_to_meta_ledger(self):
        declaration = _load("declaration.json")
        report = _load("report_pass.json")
        record = _ratification_for(declaration, report)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            entry = rat.append_promotion(
                ledger,
                run_id="ratification-run",
                declaration=declaration,
                report=report,
                ratification=record,
                ratification_token="ratify-demo-0001",
            )
            self.assertEqual(entry["event_type"], "human_ratification")
            ok, errors, count = ctrl.verify_meta_ledger(ledger)
            self.assertTrue(ok, errors)
            self.assertEqual(count, 1)
            payload = ctrl.read_meta_ledger(ledger)[0]["payload"]
            self.assertTrue(payload["promotion"]["promoted"])
            self.assertEqual(payload["ratification"]["ratification_hash"], record["ratification_hash"])

    def test_rejected_promotion_does_not_append(self):
        declaration = _load("declaration.json")
        report = _load("report_pass.json")
        record = _ratification_for(declaration, report)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            with self.assertRaises(rat.RatificationError):
                rat.append_promotion(
                    ledger,
                    run_id="ratification-run",
                    declaration=declaration,
                    report=report,
                    ratification=record,
                    ratification_token="wrong-token",
                )
            self.assertEqual(ctrl.read_meta_ledger(ledger), [])


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_ratification_module_is_frozen(self):
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/ratification.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.4.0-add-ratification")
        self.assertIsNotNone(record, "fz-v0.4.0 amendment record missing")
        self.assertIn("autolab/ratification.py", record["applies_to"])
        if record["new_zone_hash"] == manifest["zone_hash"]:
            return
        successor = amendments.get("fz-v0.5.0-add-lineage-rollback")
        self.assertIsNotNone(successor, "v0.4.0 amendment must be linked by a successor")
        self.assertEqual(successor["prev_zone_hash"], record["new_zone_hash"])
        if successor["new_zone_hash"] == manifest["zone_hash"]:
            return
        item6_record = amendments.get("fz-v0.6.0-add-circuit-breakers")
        self.assertIsNotNone(item6_record, "v0.5.0 amendment must be linked by a successor")
        self.assertEqual(item6_record["prev_zone_hash"], successor["new_zone_hash"])
        self.assertEqual(item6_record["new_zone_hash"], manifest["zone_hash"])


if __name__ == "__main__":
    unittest.main()
