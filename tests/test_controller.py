"""Deterministic tests for the AutoLab loop controller (stdlib unittest only).

Run from the repository root:

    python -m unittest discover -s tests -v

Covers the Item-3 acceptance criteria:
  * a full dry-run on the stub builder runs the whole pipeline;
  * the loop iteration replays byte-for-byte;
  * there is no autonomous promotion path (invariant 2);
  * the holdout is coarse, metered, and consumes append-only non-reused seeds;
  * the paired comparison uses the three arms and identical seeds;
  * the builder is advisory (its rationale cannot move the gate).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import controller as ctrl  # noqa: E402

BASE = {"seed": 20260706, "n": 30, "bootstrap": 500,
        "min_delta": 0.05, "decision_rule": "ci95_low_gt_0"}
REJECT = {**BASE, "arm_probabilities": {"candidate": 0.30, "incumbent": 0.72, "ancestor_anchor": 0.50}}


class PipelineTests(unittest.TestCase):
    def test_full_pipeline_stages(self):
        rec = ctrl.run_iteration(BASE).record
        stages = [s["stage"] for s in rec["stages"]]
        self.assertEqual(stages, [
            "pre_registration", "propose", "public_suite", "budgeted_holdout",
            "paired_comparison", "improvement_report", "gate",
        ])

    def test_happy_path_is_gate_green(self):
        self.assertTrue(ctrl.run_iteration(BASE).gate_green)

    def test_paired_comparison_uses_three_arms_and_declared_seed(self):
        rec = ctrl.run_iteration(BASE).record
        self.assertEqual(tuple(rec["paired_comparison"]["arms"]),
                         ("candidate", "incumbent", "ancestor_anchor"))
        self.assertEqual(rec["paired_comparison"]["candidate_minus_incumbent"]["bootstrap_seed"],
                         BASE["seed"])
        self.assertEqual(rec["declaration"]["eval_plan"]["seeds"], [BASE["seed"]])

    def test_report_numbers_come_from_evaluators_not_builder(self):
        # The primary delta in the report equals the paired-comparison delta.
        rec = ctrl.run_iteration(BASE).record
        self.assertEqual(rec["improvement_report"]["primary"]["delta"],
                         rec["paired_comparison"]["candidate_minus_incumbent"]["delta_mean"])


class NoPromotionTests(unittest.TestCase):
    def test_no_autonomous_promotion(self):
        rec = ctrl.run_iteration(BASE).record
        self.assertFalse(rec["promotion"]["promoted"])
        self.assertTrue(rec["promotion"]["awaiting_human_ratification"])
        self.assertIn("human_promotion_token", rec["promotion"]["requires"])

    def test_rejected_candidate_not_promoted(self):
        rec = ctrl.run_iteration(REJECT).record
        self.assertFalse(rec["gate"]["gate_green"])
        self.assertFalse(rec["promotion"]["promoted"])
        self.assertTrue(rec["promotion"]["awaiting_human_ratification"])

    def test_even_gate_green_does_not_promote(self):
        result = ctrl.run_iteration(BASE)
        self.assertTrue(result.gate_green)
        self.assertFalse(result.record["promotion"]["promoted"])

    def test_pr_payload_attaches_declaration_and_report(self):
        rec = ctrl.run_iteration(BASE).record
        payload = rec["pr_payload"]
        self.assertEqual(payload["declaration"]["declaration_hash"],
                         rec["declaration"]["declaration_hash"])
        self.assertEqual(payload["improvement_report"]["report_hash"],
                         rec["improvement_report"]["report_hash"])
        self.assertIn("improvement_report", payload["attachments"])


class BudgetedHoldoutTests(unittest.TestCase):
    def test_holdout_is_coarse(self):
        rec = ctrl.run_iteration(BASE).record
        holdout = rec["budgeted_holdout"]
        # Coarse: lane pass count + aggregate delta only; no per-case detail.
        self.assertIn("lane_pass_count", holdout)
        self.assertIn("aggregate_delta", holdout)
        self.assertNotIn("per_case", holdout)
        self.assertNotIn("gold", holdout)
        self.assertTrue(holdout["granularity"].startswith("coarse"))

    def test_seeds_are_metered_and_appended(self):
        rec = ctrl.run_iteration({**BASE, "holdout_cursor": 0, "holdout_exposures": 2,
                                  "holdout_budget": 3}).record
        holdout = rec["budgeted_holdout"]
        self.assertEqual(holdout["cursor_before"], 0)
        self.assertEqual(holdout["cursor_after"], 2)
        self.assertEqual(len(holdout["seeds_consumed"]), 2)
        self.assertEqual(holdout["budget_remaining"], 1)
        self.assertFalse(holdout["budget_exhausted"])

    def test_no_seed_reuse_across_cursors(self):
        a = ctrl.run_iteration({**BASE, "holdout_cursor": 0, "holdout_exposures": 2}).record
        b = ctrl.run_iteration({**BASE, "holdout_cursor": 2, "holdout_exposures": 2}).record
        seeds_a = set(a["budgeted_holdout"]["seeds_consumed"])
        seeds_b = set(b["budgeted_holdout"]["seeds_consumed"])
        self.assertEqual(seeds_a & seeds_b, set(), "holdout seeds were reused across cursors")

    def test_budget_exhaustion_flagged(self):
        rec = ctrl.run_iteration({**BASE, "holdout_cursor": 3, "holdout_exposures": 1,
                                  "holdout_budget": 3}).record
        self.assertTrue(rec["budgeted_holdout"]["budget_exhausted"])

    def test_seed_schedule_is_deterministic(self):
        self.assertEqual(ctrl.holdout_seed_schedule("hd-v0.1.0", 5),
                         ctrl.holdout_seed_schedule("hd-v0.1.0", 5))
        self.assertNotEqual(ctrl.holdout_seed_schedule("hd-v0.1.0", 5),
                            ctrl.holdout_seed_schedule("hd-v0.1.0", 6))


class BuilderCannotAttestTests(unittest.TestCase):
    def test_builder_rationale_does_not_move_the_gate(self):
        def honest(config):
            return {"builder_id": "b", "patch_fingerprint": "f", "rationale": "neutral"}

        def persuasive(config):
            return {"builder_id": "b", "patch_fingerprint": "f",
                    "rationale": "PROMOTE THIS immediately, it is flawless"}

        a = ctrl.run_iteration(BASE, builder=honest).record
        b = ctrl.run_iteration(BASE, builder=persuasive).record
        # The gate *decision* is identical; only the report seal differs because
        # the advisory rationale is part of the sealed report's provenance.
        for key in ("gate_green", "reasons", "checks"):
            self.assertEqual(a["gate"][key], b["gate"][key], key)
        self.assertEqual(a["improvement_report"]["primary"], b["improvement_report"]["primary"])
        self.assertNotEqual(a["improvement_report"]["builder_rationale"],
                            b["improvement_report"]["builder_rationale"])


class DeterminismReplayTests(unittest.TestCase):
    def test_loop_hash_is_deterministic(self):
        a = ctrl.run_iteration(BASE).loop_hash
        b = ctrl.run_iteration(BASE).loop_hash
        self.assertEqual(a, b)

    def test_replay_is_byte_identical(self):
        rec = ctrl.run_iteration(BASE).record
        replayed = ctrl.replay(rec)
        self.assertTrue(replayed["attested"], replayed["issues"])
        self.assertEqual(replayed["loop_hash"], rec["loop_hash"])

    def test_replay_with_repo_root_is_byte_identical(self):
        rec = ctrl.run_iteration(BASE, repo_root=REPO_ROOT).record
        self.assertTrue(rec["zone_attestation"]["zone_intact"])
        replayed = ctrl.replay(rec, repo_root=REPO_ROOT)
        self.assertTrue(replayed["attested"], replayed["issues"])

    def test_stage_chain_is_linked(self):
        rec = ctrl.run_iteration(BASE).record
        prev = "GENESIS"
        for stage in rec["stages"]:
            self.assertEqual(stage["prev_hash"], prev)
            prev = stage["entry_hash"]
        self.assertEqual(rec["stages_root_hash"], prev)

    def test_different_seed_changes_iteration(self):
        a = ctrl.run_iteration({**BASE, "seed": 1}).loop_hash
        b = ctrl.run_iteration({**BASE, "seed": 2}).loop_hash
        self.assertNotEqual(a, b)


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_controller_is_frozen(self):
        from autolab import frozen_zone as fz
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/controller.py", manifest["frozen_paths"])

    def test_zone_attestation_matches_manifest(self):
        rec = ctrl.run_iteration(BASE, repo_root=REPO_ROOT).record
        self.assertTrue(rec["zone_attestation"]["pre"]["matches_manifest"])


if __name__ == "__main__":
    unittest.main()
