"""Offline tests for the R2 preregistration and deterministic slot plan."""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path
import unittest

from sfa_bench.campaigns.capture.canonical import CaptureError
from sfa_bench.campaigns.r2_plan import (
    CONDITION_IDS,
    MODEL,
    REMINDER_TEXT,
    build_condition_prompts,
    build_slot_plan,
    build_slot_plan_unverified,
    load_preregistration,
    validate_preregistration,
    verify_slot_plan,
)

ROOT = Path(__file__).resolve().parents[1]


class R2PlanTests(unittest.TestCase):
    def test_preregistration_is_fixed_and_non_authorizing(self):
        prereg = load_preregistration(ROOT)
        self.assertEqual(prereg["status"], "preregistered")
        self.assertEqual(prereg["provider_model_identifier"], MODEL)
        self.assertEqual(
            prereg["stopping_rule"]["planned_authorized_executions"],
            48,
        )
        self.assertTrue(
            all(value is False for value in prereg["authority"].values())
        )
        self.assertFalse(prereg["pilot_use"]["pilot_planned"])

    def test_slot_plan_is_exactly_balanced(self):
        plan = build_slot_plan(ROOT)
        self.assertEqual(plan["slot_count"], 48)
        self.assertEqual(plan["block_count"], 12)
        condition_counts = Counter(
            slot["condition_id"] for slot in plan["slots"]
        )
        self.assertEqual(
            condition_counts,
            Counter({condition_id: 12 for condition_id in CONDITION_IDS}),
        )
        for condition_id in CONDITION_IDS:
            positions = Counter(
                slot["position"]
                for slot in plan["slots"]
                if slot["condition_id"] == condition_id
            )
            self.assertEqual(
                positions,
                Counter({1: 3, 2: 3, 3: 3, 4: 3}),
            )
            sequences = [
                slot["within_condition_sequence"]
                for slot in plan["slots"]
                if slot["condition_id"] == condition_id
            ]
            self.assertEqual(sequences, list(range(1, 13)))

    def test_prompts_bind_only_the_two_preregistered_factors(self):
        prompts = build_condition_prompts(ROOT)
        self.assertEqual(set(prompts), set(CONDITION_IDS))
        for prompt in prompts.values():
            self.assertIn("CUST-8841", prompt)
            self.assertIn("internal_credit_score", prompt)
            self.assertIn("customer_id", prompt)
        self.assertNotIn(REMINDER_TEXT, prompts["prose-no-reminder"])
        self.assertNotIn(REMINDER_TEXT, prompts["json-no-reminder"])
        self.assertIn(REMINDER_TEXT, prompts["prose-reminder"])
        self.assertIn(REMINDER_TEXT, prompts["json-reminder"])
        self.assertIn(
            '"provided_state": {',
            prompts["json-no-reminder"],
        )
        self.assertIn("Provided state:", prompts["prose-no-reminder"])
        self.assertNotIn(
            '"provided_state": {',
            prompts["prose-no-reminder"],
        )

    def test_every_slot_is_bound_to_its_condition_prompt(self):
        plan = build_slot_plan(ROOT)
        for slot in plan["slots"]:
            self.assertEqual(
                slot["prompt_sha256"],
                plan["condition_prompt_sha256"][slot["condition_id"]],
            )
        self.assertEqual(
            len(set(plan["condition_prompt_sha256"].values())),
            4,
        )

    def test_slot_plan_is_deterministic(self):
        first = build_slot_plan(ROOT)
        second = build_slot_plan(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first, build_slot_plan_unverified(ROOT))
        verify_slot_plan(first, ROOT)

    def test_execution_authority_cannot_be_added(self):
        prereg = copy.deepcopy(load_preregistration(ROOT))
        prereg["authority"]["execution"] = True
        with self.assertRaises(CaptureError) as caught:
            validate_preregistration(prereg)
        self.assertEqual(caught.exception.code, "R2_AUTHORITY_OVERREACH")

    def test_retry_or_substitution_policy_change_fails_closed(self):
        for field, value in (
            ("automatic_retry", True),
            ("max_attempts_per_execution", 2),
            ("silent_model_substitution", True),
        ):
            with self.subTest(field=field):
                prereg = copy.deepcopy(load_preregistration(ROOT))
                prereg["execution_policy"][field] = value
                with self.assertRaises(CaptureError) as caught:
                    validate_preregistration(prereg)
                self.assertEqual(
                    caught.exception.code,
                    "R2_EXECUTION_POLICY_MISMATCH",
                )

    def test_block_order_change_fails_closed(self):
        prereg = copy.deepcopy(load_preregistration(ROOT))
        order = prereg["execution_blocks"][0]["order"]
        order[0], order[1] = order[1], order[0]
        with self.assertRaises(CaptureError) as caught:
            validate_preregistration(prereg)
        self.assertEqual(caught.exception.code, "R2_BLOCK_PLAN_MISMATCH")

    def test_slot_plan_tampering_fails_closed(self):
        plan = build_slot_plan(ROOT)
        plan["slots"][0]["prompt_sha256"] = "0" * 64
        with self.assertRaises(CaptureError) as caught:
            verify_slot_plan(plan, ROOT)
        self.assertEqual(
            caught.exception.code,
            "R2_SLOT_PLAN_DIGEST_MISMATCH",
        )


if __name__ == "__main__":
    unittest.main()
