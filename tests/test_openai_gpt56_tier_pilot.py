"""Tests for the preregistered GPT-5.6 Terra and Luna tier pilots."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

import openai_gpt56_tier_pilot as tier
import openai_live_pilot as base
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.locking import build_benchmark_lock


ROOT = Path(__file__).resolve().parents[1]


class GPT56TierPilotTests(unittest.TestCase):
    def repository_commit(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip().lower()

    def test_only_terra_and_luna_are_preregistered(self):
        for model in ("gpt-5.6", "gpt-5.6-sol", "gpt-5.5", "gpt-5.6-terra "):
            with self.subTest(model=model), self.assertRaises(base.PilotError) as caught:
                tier._spec(model)
            self.assertEqual(caught.exception.code, "TIER_MODEL_NOT_PREREGISTERED")

    def test_exact_execution_ids_are_defaulted_and_enforced(self):
        for model, expected in (
            ("gpt-5.6-terra", "openai-gpt56-terra-pilot-001"),
            ("gpt-5.6-luna", "openai-gpt56-luna-pilot-001"),
        ):
            with self.subTest(model=model):
                args = tier._parse_args(
                    ["--operator", "Matthew Neal", "--model", model, "--execute"]
                )
                self.assertEqual(args.execution_id, expected)
                with self.assertRaises(base.PilotError) as caught:
                    tier._parse_args(
                        [
                            "--operator",
                            "Matthew Neal",
                            "--model",
                            model,
                            "--execution-id",
                            "wrong-execution-id",
                            "--execute",
                        ]
                    )
                self.assertEqual(caught.exception.code, "TIER_EXECUTION_ID_MISMATCH")

    def test_preparation_only_use_is_rejected_before_provider_access(self):
        with self.assertRaises(base.PilotError) as caught:
            tier._parse_args(
                ["--operator", "Matthew Neal", "--model", "gpt-5.6-terra"]
            )
        self.assertEqual(caught.exception.code, "TIER_EXECUTION_REQUIRED")

    def test_campaigns_have_distinct_identity_and_shared_frozen_inputs(self):
        commit = self.repository_commit()
        campaigns = {
            model: tier._build_campaign(model, commit)
            for model in ("gpt-5.6-terra", "gpt-5.6-luna")
        }
        terra = campaigns["gpt-5.6-terra"]
        luna = campaigns["gpt-5.6-luna"]

        self.assertNotEqual(terra["campaign_id"], luna["campaign_id"])
        self.assertEqual(terra["provider_model_identifier"], "gpt-5.6-terra")
        self.assertEqual(luna["provider_model_identifier"], "gpt-5.6-luna")
        for field in (
            "frozen_case_set_digest",
            "frozen_rule_digest",
            "frozen_taxonomy_digest",
            "system_prompt",
            "user_prompt_or_case_set",
        ):
            self.assertEqual(terra[field], luna[field])
        self.assertEqual(terra["run_count"], 1)
        self.assertEqual(luna["run_count"], 1)
        self.assertIn("cannot support a provider-tier ranking", " ".join(terra["declared_limitations"]))
        self.assertEqual(len(terra["benchmark_inputs"]["declared_commands"]), 1)
        self.assertTrue(terra["benchmark_inputs"]["declared_commands"][0].endswith("--execute"))

    def test_protocol_and_complete_capture_core_are_lock_bound(self):
        commit = self.repository_commit()
        for model in ("gpt-5.6-terra", "gpt-5.6-luna"):
            with self.subTest(model=model):
                campaign = tier._build_campaign(model, commit)
                lock = build_benchmark_lock(campaign, ROOT)
                bound = {
                    entry["path"]
                    for group in lock["bindings"].values()
                    for entry in group
                }
                self.assertIn(tier.PROTOCOL_REFERENCE, bound)
                self.assertIn(tier.SCRIPT_REFERENCE, bound)
                self.assertTrue(set(REQUIRED_ALPHA2_BINDINGS).issubset(bound))

    def test_requests_differ_only_by_exact_model_identifier(self):
        terra = json.loads(base._build_request("gpt-5.6-terra", 1000))
        luna = json.loads(base._build_request("gpt-5.6-luna", 1000))
        self.assertEqual(terra.pop("model"), "gpt-5.6-terra")
        self.assertEqual(luna.pop("model"), "gpt-5.6-luna")
        self.assertEqual(terra, luna)
        self.assertIs(terra["store"], False)
        self.assertNotIn("tools", terra)

    def test_protocol_records_ratified_anchor_and_exploratory_limits(self):
        protocol = json.loads((ROOT / tier.PROTOCOL_REFERENCE).read_text(encoding="utf-8"))
        self.assertEqual(protocol["ratified_anchor"]["execution_id"], "openai-gpt56-sol-pilot-002")
        self.assertEqual(protocol["ratified_anchor"]["human_disposition"], "RATIFIED")
        self.assertEqual(
            [item["execution_id"] for item in protocol["planned_successors"]],
            ["openai-gpt56-terra-pilot-001", "openai-gpt56-luna-pilot-001"],
        )
        self.assertTrue(any("cannot support a provider-tier ranking" in item for item in protocol["interpretation_limits"]))
        self.assertFalse(protocol["authority"]["automatic_ratification"])


if __name__ == "__main__":
    unittest.main()
