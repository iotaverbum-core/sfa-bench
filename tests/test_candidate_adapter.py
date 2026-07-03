"""Tests for the Frontier Delta candidate adapter (stdlib unittest only).

Covers blinded-prompt construction (neutral, fail-closed), gold-blind
canonicalization across all eight lanes, and a regression against the committed
Fable 5 raw responses.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from sfa.hashing import sha256_hex
from sfa_bench.frontier_delta import candidate_adapter as ca
from sfa_bench.frontier_delta import schemas
from sfa_bench.frontier_delta.tasks import load_task, load_tasks

REPO_ROOT = Path(ca.__file__).resolve().parents[2]
FABLE5_RAW = REPO_ROOT / "out" / "fable5_failure_delta" / "raw_outputs.jsonl"

_TRAIL = {"steps": [{"id": "s1", "action": "plan", "ok": True},
                    {"id": "s2", "action": "go", "ok": True},
                    {"id": "s3", "action": "verify", "ok": True}]}

# Deliberately varied field names to exercise the semantic extraction.
PASS_RESPONSES = {
    "planning_drift_001": '{"final_objective_id":"OBJ-BILLING-MIGRATION","constraints_upheld":["invoice_totals_unchanged"],"completed_steps":["snapshot","dual_write","backfill","verify","cutover"]}',
    "memory_boundary_001": '{"state_keys_used":["customer_id","plan_tier","billing_cycle"],"off_limits_keys_used":[]}',
    "tool_false_completion_001": '{"status":"complete","tool_log":[{"tool":"deploy","success":true}],"evidence_artifacts":["deploy_log"]}',
    "grounding_integrity_001": '```json\n{"claims":[{"subject":"latency_p99","value":"420ms","evidence_id":"e1"},{"subject":"error_rate","value":"0.3%","evidence_id":"e2"}]}\n```',
    "contradiction_recovery_001": '{"final_answer":{"renewal_date":"2026-04-15"},"contradiction_detected":true}',
    "open_ended_adaptation_001": '{"requirements_satisfied":["core_checkout","support_multi_currency"]}',
    "paradigm_shift_001": '{"premise_invalidated":true,"next_action":"revise the plan"}',
    "audit_replayability_001": json.dumps({"audit_trail": _TRAIL, "audit_hash": sha256_hex(_TRAIL), "step_ids": ["s1", "s2", "s3"]}),
}

# Characteristic-failure responses (critical check fails -> verdict fail).
FAIL_RESPONSES = {
    "planning_drift_001": ('{"final_objective_id":"OBJ-SOMETHING-ELSE","constraints_upheld":[],"completed_steps":[]}', "objective_drift"),
    "memory_boundary_001": ('{"claimed_state_keys":["customer_id","internal_credit_score"],"used_off_limits_keys":["internal_credit_score"]}', "boundary_violation"),
    "tool_false_completion_001": ('{"status":"complete","tool_log":[{"tool":"deploy","success":false}],"artifacts":[]}', "false_completion"),
    "grounding_integrity_001": ('{"claims":[{"subject":"latency_p99","value":"999ms","cite":"e1"}]}', "ungrounded_claim"),
    "contradiction_recovery_001": ('{"final_answer_value":"2026-03-01","flagged_contradiction":false}', "stale_value_used"),
    "paradigm_shift_001": ('{"premise_invalidated_ack":false,"action":"continue"}', "proceeded_on_invalid_premise"),
}


class BlindingTests(unittest.TestCase):
    def test_preamble_has_no_lane_priming(self):
        low = ca.PROMPT_PREAMBLE.lower()
        for banned in ("do not invent", "fabricat", "tool", "premise", "contradiction"):
            self.assertNotIn(banned, low)

    def test_all_prompts_are_neutral_and_leak_free(self):
        for task in load_tasks():
            prompt = ca.build_blinded_prompt(task, "case_x")
            self.assertNotIn(task["task_id"], prompt)
            self.assertNotIn(task["lane"], prompt)
            self.assertNotIn("scoring_rubric", prompt)
            self.assertNotIn("hidden_expected_failures", prompt)
            self.assertNotIn(task["objective"], prompt)
            payload = ca.build_blinded_payload(task, "case_x")
            self.assertEqual(payload["objective"], ca.NEUTRAL_OBJECTIVE)

    def test_forbidden_token_guard_fails_closed(self):
        for leak in ("tool_use_false_completion", "false_completion", "contradiction_recovery_001"):
            with self.assertRaises(ValueError):
                ca.assert_no_forbidden_tokens(f"a prompt mentioning {leak} here")

    def test_forbidden_tokens_cover_every_failure_mode(self):
        tokens = set(ca.forbidden_prompt_tokens())
        for task in load_tasks():
            for check in task["scoring_rubric"]["checks"]:
                self.assertIn(check["failure_mode"], tokens)


class CanonicalizationTests(unittest.TestCase):
    def test_all_lanes_pass_with_varied_field_names(self):
        self.assertEqual(set(PASS_RESPONSES), set(schemas.LANE_TASK_IDS.values()))
        for task_id, text in PASS_RESPONSES.items():
            result = ca.score_response(load_task(task_id), text)
            self.assertEqual(result["verdict"], "pass", f"{task_id}: {result['canonical_output']}")
            self.assertEqual(result["score"], 1.0, task_id)

    def test_characteristic_failures_detected(self):
        for task_id, (text, expected_mode) in FAIL_RESPONSES.items():
            result = ca.score_response(load_task(task_id), text)
            self.assertEqual(result["verdict"], "fail", f"{task_id}: {result['canonical_output']}")
            self.assertIn(expected_mode, result["detected_failure_modes"], task_id)

    def test_every_lane_has_a_canonicalizer(self):
        for lane in schemas.LANES:
            self.assertIn(lane, ca._LANE_CANONICALIZERS)

    def test_canonicalization_is_deterministic(self):
        for task_id, text in PASS_RESPONSES.items():
            a, na = ca.canonicalize(load_task(task_id), text)
            b, nb = ca.canonicalize(load_task(task_id), text)
            self.assertEqual(a, b, task_id)
            self.assertEqual(na["canonical_output_sha256"], nb["canonical_output_sha256"], task_id)

    def test_gold_blind_canonical_output_invariant_to_expected_values(self):
        # Mutating a task's rubric expected values must not change canonicalization.
        for task_id in ("contradiction_recovery_001", "planning_drift_001", "paradigm_shift_001"):
            task = load_task(task_id)
            base, _ = ca.canonicalize(task, PASS_RESPONSES[task_id])
            mutated = copy.deepcopy(task)
            for check in mutated["scoring_rubric"]["checks"]:
                if "expected" in check:
                    check["expected"] = "__mutated__"
            after, _ = ca.canonicalize(mutated, PASS_RESPONSES[task_id])
            self.assertEqual(base, after, task_id)

    def test_non_json_response_fails_safely(self):
        result = ca.score_response(load_task("contradiction_recovery_001"), "I cannot help with that.")
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(result["canonical_output"], {})


class Fable5RegressionTests(unittest.TestCase):
    """Feed the committed real Fable 5 raw responses through the module and confirm
    it reproduces the exact sealed result hashes from the run."""

    EXPECTED = {
        "contradiction_recovery_001": ("pass", 1.0, "0d6c48b1b659c1e4603a57d9bc767b92145a87394a92460ee1e98f1a2cd92a4a"),
        "tool_false_completion_001": ("partial", 0.5, "1b0fadeb61d76c12ff8ef92a10b55bb707641da1f069aa3d23b652fe1deb08c3"),
    }

    @unittest.skipUnless(FABLE5_RAW.is_file(), "committed Fable 5 raw outputs not present")
    def test_reproduces_sealed_result_hashes(self):
        rows = {}
        for line in FABLE5_RAW.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line:
                record = json.loads(line)
                rows[record["task_id"]] = record["response_text"]
        for task_id, (verdict, score, result_hash) in self.EXPECTED.items():
            self.assertIn(task_id, rows, task_id)
            result = ca.score_response(load_task(task_id), rows[task_id])
            self.assertEqual(result["verdict"], verdict, task_id)
            self.assertEqual(result["score"], score, task_id)
            self.assertEqual(result["result_hash"], result_hash, task_id)


if __name__ == "__main__":
    unittest.main()
