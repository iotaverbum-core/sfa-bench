"""Deterministic tests for AutoLab lineage and rollback (Item 5)."""
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
from autolab import lineage as lin  # noqa: E402
from autolab import preregistration as pre  # noqa: E402
from autolab import ratification as rat  # noqa: E402

FIX = REPO_ROOT / "examples" / "preregistration"
RATIFY_TOKEN = "ratify-lineage-0001"
ROLLBACK_TOKEN = "rollback-lineage-0001"
TARGET_REF = {
    "type": "git_commit",
    "sha": "1111111111111111111111111111111111111111",
    "branch": "candidate/item-5",
}
PREVIOUS_REF = {
    "type": "git_commit",
    "sha": "0000000000000000000000000000000000000000",
    "branch": "main",
}


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ratification_for(declaration: dict, report: dict, target_ref: dict) -> dict:
    gate = pre.evaluate_gate(declaration, report)
    return rat.seal_ratification(rat.build_ratification(
        ratification_id=RATIFY_TOKEN,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref=target_ref,
        human_reviewer="human-reviewer",
        rationale="Gate is green and the target ref is approved for lineage.",
    ))


def _append_ratified_promotion(ledger: Path, target_ref: dict = TARGET_REF) -> dict:
    declaration = _load("declaration.json")
    report = _load("report_pass.json")
    record = _ratification_for(declaration, report, target_ref)
    return rat.append_promotion(
        ledger,
        run_id="lineage-ratification-run",
        declaration=declaration,
        report=report,
        ratification=record,
        ratification_token=RATIFY_TOKEN,
    )


def _sealed_rollback(target_ref: dict = TARGET_REF, restore_ref: dict = PREVIOUS_REF) -> dict:
    return lin.seal_rollback(lin.build_rollback(
        rollback_id=ROLLBACK_TOKEN,
        target_ref=target_ref,
        restore_ref=restore_ref,
        human_reviewer="human-reviewer",
        reason="Restore the last reviewed baseline.",
    ))


class LineagePromotionTests(unittest.TestCase):
    def test_promotion_inscription_derives_current_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            entry = lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
                rationale="Inscribing reviewed Item 5 target.",
            )

            self.assertEqual(entry["event_type"], "promotion_inscribed")
            ok, errors, count = ctrl.verify_meta_ledger(ledger)
            self.assertTrue(ok, errors)
            self.assertEqual(count, 2)

            state = lin.derive_lineage_state(ledger)
            self.assertEqual(state.current_ref, TARGET_REF)
            self.assertEqual(state.current_key, lin.target_key(TARGET_REF))
            self.assertEqual(len(state.promotions), 1)
            self.assertEqual(state.promotions[0]["promotion_entry_hash"], promotion[ctrl.ENTRY_HASH_KEY])

    def test_inscription_requires_existing_human_ratification(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            builder_entry = ctrl.append_meta_event(
                ledger,
                event_type="builder_completed",
                run_id="builder-run",
                payload={"target_ref": TARGET_REF},
            )

            with self.assertRaisesRegex(lin.LineageError, "human_ratification"):
                lin.append_promotion_inscription(
                    ledger,
                    run_id="lineage-inscription-run",
                    promotion_entry_hash=builder_entry[ctrl.ENTRY_HASH_KEY],
                    previous_ref=PREVIOUS_REF,
                )

            self.assertIsNone(lin.derive_lineage_state(ledger).current_ref)

    def test_duplicate_current_target_is_rejected_without_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )

            with self.assertRaisesRegex(lin.LineageError, "already current"):
                lin.append_promotion_inscription(
                    ledger,
                    run_id="lineage-inscription-run-2",
                    promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                    previous_ref=PREVIOUS_REF,
                )

            self.assertEqual(len(ctrl.read_meta_ledger(ledger)), 2)


class RollbackTests(unittest.TestCase):
    def test_rollback_requires_human_token_and_does_not_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )

            with self.assertRaisesRegex(lin.LineageError, "token missing"):
                lin.append_rollback(
                    ledger,
                    run_id="rollback-run",
                    rollback=_sealed_rollback(),
                    rollback_token=None,
                )

            self.assertEqual(len(ctrl.read_meta_ledger(ledger)), 2)

    def test_rollback_appends_and_restores_previous_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )
            rollback = _sealed_rollback()
            entry = lin.append_rollback(
                ledger,
                run_id="rollback-run",
                rollback=rollback,
                rollback_token=ROLLBACK_TOKEN,
            )

            self.assertEqual(entry["event_type"], "rollback_inscribed")
            state = lin.derive_lineage_state(ledger)
            self.assertEqual(state.current_ref, PREVIOUS_REF)
            self.assertEqual(state.current_key, lin.target_key(PREVIOUS_REF))
            self.assertEqual(len(state.rollbacks), 1)
            self.assertEqual(len(ctrl.read_meta_ledger(ledger)), 3)

    def test_wrong_rollback_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )
            wrong_target = dict(TARGET_REF, sha="2222222222222222222222222222222222222222")

            with self.assertRaisesRegex(lin.LineageError, "not the current"):
                lin.append_rollback(
                    ledger,
                    run_id="rollback-run",
                    rollback=_sealed_rollback(target_ref=wrong_target),
                    rollback_token=ROLLBACK_TOKEN,
                )

            self.assertEqual(len(ctrl.read_meta_ledger(ledger)), 2)

    def test_tampered_rollback_hash_raises(self):
        rollback = _sealed_rollback()
        rollback["reason"] = "Edited after sealing."
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )

            with self.assertRaisesRegex(lin.LineageError, "rollback_hash"):
                lin.append_rollback(
                    ledger,
                    run_id="rollback-run",
                    rollback=rollback,
                    rollback_token=ROLLBACK_TOKEN,
                )

    def test_ratification_entry_cannot_be_reinscribed_after_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )
            lin.append_rollback(
                ledger,
                run_id="rollback-run",
                rollback=_sealed_rollback(),
                rollback_token=ROLLBACK_TOKEN,
            )

            with self.assertRaisesRegex(lin.LineageError, "already inscribed"):
                lin.append_promotion_inscription(
                    ledger,
                    run_id="lineage-reinscription-run",
                    promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                )

            self.assertEqual(len(ctrl.read_meta_ledger(ledger)), 3)


    def test_state_derivation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "meta.jsonl"
            promotion = _append_ratified_promotion(ledger)
            lin.append_promotion_inscription(
                ledger,
                run_id="lineage-inscription-run",
                promotion_entry_hash=promotion[ctrl.ENTRY_HASH_KEY],
                previous_ref=PREVIOUS_REF,
            )
            lin.append_rollback(
                ledger,
                run_id="rollback-run",
                rollback=_sealed_rollback(),
                rollback_token=ROLLBACK_TOKEN,
            )
            a = lin.derive_lineage_state(ledger).to_dict()
            b = lin.derive_lineage_state(ledger).to_dict()
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_lineage_module_is_frozen(self):
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/lineage.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.5.0-add-lineage-rollback")
        self.assertIsNotNone(record, "fz-v0.5.0 amendment record missing")
        self.assertIn("autolab/lineage.py", record["applies_to"])
        if record["new_zone_hash"] == manifest["zone_hash"]:
            return
        successor = amendments.get("fz-v0.6.0-add-circuit-breakers")
        self.assertIsNotNone(successor, "v0.5.0 amendment must be linked by a successor")
        self.assertEqual(successor["prev_zone_hash"], record["new_zone_hash"])
        if successor["new_zone_hash"] == manifest["zone_hash"]:
            return
        item7_record = amendments.get("fz-v0.7.0-add-runner")
        self.assertIsNotNone(item7_record, "v0.6.0 amendment must be linked by a successor")
        self.assertEqual(item7_record["prev_zone_hash"], successor["new_zone_hash"])
        if item7_record["new_zone_hash"] == manifest["zone_hash"]:
            return
        release_record = amendments.get("fz-v0.8.0-v2-alpha1-integrity-release")
        self.assertIsNotNone(release_record, "v0.7.0 amendment must be linked by a successor")
        self.assertEqual(release_record["prev_zone_hash"], item7_record["new_zone_hash"])
        if release_record["new_zone_hash"] == manifest["zone_hash"]:
            return
        alpha2_record = amendments.get("fz-v0.9.0-v2-alpha2-campaign-capture-release")
        self.assertIsNotNone(alpha2_record, "v0.8.0 amendment must be linked by a successor")
        self.assertEqual(alpha2_record["prev_zone_hash"], release_record["new_zone_hash"])
        self.assertEqual(alpha2_record["new_zone_hash"], manifest["zone_hash"])


if __name__ == "__main__":
    unittest.main()
