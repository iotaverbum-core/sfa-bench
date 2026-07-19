"""Regression tests for the corrected OpenAI live-pilot binding surface."""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

import openai_live_pilot_v2 as pilot
from sfa_bench.campaigns.capture.context import (
    REQUIRED_ALPHA2_BINDINGS,
    verify_governed_context,
)
from sfa_bench.campaigns.locking import build_benchmark_lock


ROOT = Path(__file__).resolve().parents[1]


def repository_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git rev-parse failed")
    return result.stdout.strip().lower()


class OpenAILivePilotV2Tests(unittest.TestCase):
    def test_schema_declaration_contains_authoritative_capture_core(self):
        paths = pilot._complete_schema_paths(["campaign_capture_cli.py"])
        self.assertTrue(REQUIRED_ALPHA2_BINDINGS <= set(paths))
        self.assertIn(pilot.SCRIPT_REFERENCE, paths)
        self.assertEqual(len(paths), len(set(paths)))

    def test_built_lock_passes_actual_governed_context_gate(self):
        commit = repository_head()
        campaign = pilot._build_campaign("gpt-5.6-sol", commit)
        lock = build_benchmark_lock(campaign, ROOT)
        bindings = verify_governed_context(campaign, lock, ROOT)

        self.assertTrue(REQUIRED_ALPHA2_BINDINGS <= set(bindings))
        self.assertIn("campaign_capture_check.py", bindings)
        self.assertIn(pilot.SCRIPT_REFERENCE, bindings)
        self.assertEqual(campaign["campaign_id"], pilot.CORRECTED_CAMPAIGN_ID)


if __name__ == "__main__":
    unittest.main()
