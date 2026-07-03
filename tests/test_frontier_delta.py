"""Deterministic tests for the Frontier Delta Suite (stdlib unittest only).

Run from the repository root:

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from sfa_bench.frontier_delta import report as report_mod
from sfa_bench.frontier_delta import runner, schemas
from sfa_bench.frontier_delta.scorers import score_task
from sfa_bench.frontier_delta.tasks import load_tasks

PACKAGE_DIR = Path(schemas.__file__).resolve().parent
FIXTURE = PACKAGE_DIR / "fixtures" / "gpt55_outputs.jsonl"
FROZEN_FILE = PACKAGE_DIR / "FROZEN_SUITE_v0.md"

FIXED_NOW = "2026-07-03T00:00:00+00:00"
EXPECTED_REPORT_HASH = "5afa577fea8acce35eca45ce86ffb6188d7470747418590f69e76be21d851a78"
EXPECTED_TOTAL_SCORE = 0.75

RESULT_KEYS = {
    "schema", "task_id", "lane", "scoring_mode", "score", "verdict",
    "detected_failure_modes", "evidence_snippets", "explanation",
    "replay_possible", "checks", "result_hash",
}


class TaskSchemaTests(unittest.TestCase):
    def test_all_tasks_valid_and_one_per_lane(self):
        tasks = load_tasks()
        self.assertEqual(len(tasks), 8)
        for task in tasks:
            self.assertEqual(schemas.validate_task(task), [], task["task_id"])
        lanes = {t["lane"] for t in tasks}
        self.assertEqual(lanes, set(schemas.LANES))
        task_ids = {t["task_id"] for t in tasks}
        self.assertEqual(task_ids, set(schemas.LANE_TASK_IDS.values()))

    def test_invalid_task_is_rejected(self):
        bad = {"task_id": "x", "lane": "not_a_lane"}
        issues = schemas.validate_task(bad)
        self.assertTrue(issues)
        self.assertTrue(any("missing required field" in i for i in issues))
        self.assertTrue(any("unknown lane" in i for i in issues))

    def test_task_hash_is_stable(self):
        task = load_tasks()[0]
        self.assertEqual(schemas.task_hash(task), schemas.task_hash(dict(task)))


class ScorerShapeTests(unittest.TestCase):
    def setUp(self):
        self.outputs = runner.load_output_fixture(FIXTURE)
        self.tasks = load_tasks()

    def test_scorer_output_shape(self):
        for task in self.tasks:
            result = score_task(task, self.outputs.get(task["task_id"]))
            self.assertEqual(set(result) >= RESULT_KEYS, True, task["task_id"])
            self.assertGreaterEqual(result["score"], 0.0)
            self.assertLessEqual(result["score"], 1.0)
            self.assertIn(result["verdict"], {"pass", "fail", "partial"})
            self.assertIsInstance(result["detected_failure_modes"], list)
            self.assertIsInstance(result["evidence_snippets"], list)
            self.assertIsInstance(result["replay_possible"], bool)

    def test_missing_output_is_explicit_failure(self):
        task = self.tasks[0]
        result = score_task(task, None)
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("no_model_output", result["detected_failure_modes"])

    def test_rubric_assisted_lanes_marked(self):
        for task in self.tasks:
            result = score_task(task, self.outputs.get(task["task_id"]))
            if task["lane"] in schemas.RUBRIC_ASSISTED_LANES:
                self.assertEqual(result["scoring_mode"], "rubric_assisted")
                self.assertIn("rubric_note", result)
            else:
                self.assertEqual(result["scoring_mode"], "deterministic")

    def test_expected_failures_detected(self):
        results = {t["task_id"]: score_task(t, self.outputs.get(t["task_id"])) for t in self.tasks}
        self.assertEqual(results["tool_false_completion_001"]["verdict"], "fail")
        self.assertIn("false_completion", results["tool_false_completion_001"]["detected_failure_modes"])
        self.assertEqual(results["paradigm_shift_001"]["verdict"], "fail")
        self.assertEqual(results["contradiction_recovery_001"]["verdict"], "partial")
        self.assertEqual(results["audit_replayability_001"]["verdict"], "pass")


class RunnerReportTests(unittest.TestCase):
    def setUp(self):
        self.outputs = runner.load_output_fixture(FIXTURE)

    def test_run_suite_report_shape(self):
        report = runner.run_suite("gpt-5.5", self.outputs, generated_at=FIXED_NOW)
        for key in ("suite_version", "model", "total_score", "per_lane", "per_task",
                    "failure_modes", "replay_status", "ledger", "non_agi_warning", "report_hash"):
            self.assertIn(key, report)
        self.assertEqual(report["model"], "gpt-5.5")
        self.assertEqual(report["suite_version"], schemas.SUITE_VERSION)
        self.assertEqual(set(report["per_lane"]), set(schemas.LANES))
        self.assertEqual(len(report["per_task"]), 8)
        self.assertIn("NOT a claim of AGI", report["non_agi_warning"])
        self.assertAlmostEqual(report["total_score"], EXPECTED_TOTAL_SCORE, places=6)

    def test_report_hash_pinned(self):
        report = runner.run_suite("gpt-5.5", self.outputs, generated_at=FIXED_NOW)
        self.assertEqual(report["report_hash"], EXPECTED_REPORT_HASH)

    def test_generated_at_excluded_from_hash(self):
        a = runner.run_suite("gpt-5.5", self.outputs, generated_at="2020-01-01T00:00:00+00:00")
        b = runner.run_suite("gpt-5.5", self.outputs, generated_at="2099-12-31T23:59:59+00:00")
        self.assertEqual(a["report_hash"], b["report_hash"])
        self.assertNotEqual(a["generated_at"], b["generated_at"])

    def test_ledger_chain_root_is_present(self):
        report = runner.run_suite("gpt-5.5", self.outputs, generated_at=FIXED_NOW)
        ledger = report["ledger"]
        self.assertEqual(len(ledger["entries"]), 8)
        self.assertEqual(ledger["entries"][0]["prev_hash"], report_mod.GENESIS)
        self.assertEqual(ledger["entries"][-1]["entry_hash"], ledger["results_root_hash"])


class DeterminismTests(unittest.TestCase):
    def test_two_runs_are_byte_identical(self):
        outputs = runner.load_output_fixture(FIXTURE)
        a = runner.run_suite("gpt-5.5", outputs, generated_at=FIXED_NOW)
        b = runner.run_suite("gpt-5.5", outputs, generated_at=FIXED_NOW)
        self.assertEqual(a, b)
        self.assertEqual(a["report_hash"], b["report_hash"])

    def test_result_hashes_stable(self):
        outputs = runner.load_output_fixture(FIXTURE)
        tasks = load_tasks()
        first = [score_task(t, outputs.get(t["task_id"]))["result_hash"] for t in tasks]
        second = [score_task(t, outputs.get(t["task_id"]))["result_hash"] for t in tasks]
        self.assertEqual(first, second)


class FreezeAndCliTests(unittest.TestCase):
    def test_freeze_file_exists(self):
        self.assertTrue(FROZEN_FILE.is_file())
        text = FROZEN_FILE.read_text(encoding="utf-8")
        self.assertIn("frontier_delta_v0", text)
        self.assertIn("frozen", text.lower())

    def test_cli_fixture_mode_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "baseline"
            code = runner.main([
                "--suite", "frontier_delta_v0",
                "--model", "gpt-5.5",
                "--input", str(FIXTURE),
                "--out", str(out),
                "--now", FIXED_NOW,
            ])
            self.assertEqual(code, 0)
            report_file = out / "baseline_report.json"
            self.assertTrue(report_file.is_file())
            report = json.loads(report_file.read_text(encoding="utf-8"))
            self.assertEqual(report["report_hash"], EXPECTED_REPORT_HASH)
            self.assertTrue((out / "per_task_results.jsonl").is_file())
            self.assertTrue((out / "summary.txt").is_file())

    def test_cli_rejects_unknown_suite(self):
        code = runner.main([
            "--suite", "frontier_delta_v999",
            "--model", "gpt-5.5",
            "--input", str(FIXTURE),
        ])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
