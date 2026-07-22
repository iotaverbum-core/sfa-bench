"""Tests for the guarded 48-slot GPT-5.6 Sol R2 execution harness."""
from __future__ import annotations

import base64
from collections import Counter
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import openai_gpt56_r2 as cli
import openai_live_pilot as base
from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    write_exclusive_json,
)
from sfa_bench.campaigns.capture.context import REQUIRED_ALPHA2_BINDINGS
from sfa_bench.campaigns.locking import build_benchmark_lock
from sfa_bench.campaigns.r2_authorization import (
    build_block_authorization,
    read_block_authorization,
    verify_block_authorization,
    write_block_authorization,
)
from sfa_bench.campaigns.r2_harness_plan import (
    initialize_slot_plan,
    read_slot_plan,
)
from sfa_bench.campaigns.r2_plan import (
    CONDITION_IDS,
    build_condition_prompt,
    build_slot_plan,
)
from sfa_bench.campaigns.r2_state import (
    scan_slot_states,
    status_document,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-07-22T08:00:00+02:00"


class R2HarnessTests(unittest.TestCase):
    def env(self, root: str):
        return mock.patch.dict(
            os.environ,
            {
                "SFA_R2_HARNESS_ROOT": str(Path(root) / "harness"),
                "SFA_CAMPAIGN_CAPTURE_ROOT": str(
                    Path(root) / "captures"
                ),
            },
            clear=False,
        )

    def commit(self) -> str:
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            .stdout.strip()
            .lower()
        )

    def authorize(self, root: str):
        plan = read_slot_plan(ROOT)
        value = build_block_authorization(
            ROOT,
            plan=plan,
            block=1,
            operator="Matthew Neal",
            rationale="Authorize the fixed first R2 block.",
            issued_at=NOW,
        )
        return (
            plan,
            value,
            write_block_authorization(ROOT, value, plan),
        )

    def write_run(
        self,
        root: str,
        slot: dict,
        *,
        attempts: int = 0,
        model: str | None = None,
    ):
        target = (
            Path(root)
            / "captures"
            / slot["campaign_id"]
            / slot["execution_id"]
        )
        (target / "attempts").mkdir(parents=True)
        write_exclusive_json(
            target / "run.json",
            {
                "campaign_id": slot["campaign_id"],
                "execution_id": slot["execution_id"],
            },
        )
        write_exclusive_json(
            target / "preregistration.json",
            {
                "campaign_id": slot["campaign_id"],
                "provider_model_identifier": model or slot["model"],
            },
        )
        for number in range(1, attempts + 1):
            directory = target / "attempts" / f"{number:06d}"
            directory.mkdir()
            write_exclusive_json(
                directory / "attempt.json",
                {
                    "attempt_number": number,
                    "execution_id": slot["execution_id"],
                    "complete": True,
                },
            )
        return target

    def test_plan_has_exact_balanced_slots_positions_and_ids(self):
        plan = build_slot_plan(ROOT)
        self.assertEqual(
            (plan["slot_count"], plan["block_count"]),
            (48, 12),
        )
        self.assertEqual(
            [item["condition_id"] for item in plan["slots"][:4]],
            list(CONDITION_IDS),
        )
        for condition_id in CONDITION_IDS:
            members = [
                item
                for item in plan["slots"]
                if item["condition_id"] == condition_id
            ]
            self.assertEqual(len(members), 12)
            self.assertEqual(
                Counter(item["position"] for item in members),
                Counter({1: 3, 2: 3, 3: 3, 4: 3}),
            )
            self.assertEqual(
                [item["execution_id"] for item in members],
                [
                    f"openai-gpt56-sol-r2-{condition_id}-{n:03d}"
                    for n in range(1, 13)
                ],
            )

    def test_offline_commands_are_immutable_and_credential_free(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            with mock.patch.object(
                base,
                "_api_key",
                side_effect=AssertionError("provider access"),
            ):
                self.assertEqual(cli.main(["initialize"]), 0)
                self.assertEqual(cli.main(["status"]), 0)
                self.assertEqual(
                    cli.main(
                        [
                            "authorize-block",
                            "--operator",
                            "Matthew Neal",
                            "--block",
                            "1",
                            "--rationale",
                            "Authorize the fixed first R2 block.",
                            "--now",
                            NOW,
                        ]
                    ),
                    0,
                )
                with self.assertRaises(CaptureError) as caught:
                    initialize_slot_plan(ROOT)
            self.assertEqual(caught.exception.code, "NO_OVERWRITE")

    def test_authorization_is_next_block_only_canonical_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan = read_slot_plan(ROOT)
            with self.assertRaises(CaptureError) as caught:
                build_block_authorization(
                    ROOT,
                    plan=plan,
                    block=2,
                    operator="Matthew Neal",
                    rationale="Skip block one.",
                    issued_at=NOW,
                )
            self.assertEqual(caught.exception.code, "R2_BLOCK_OUT_OF_ORDER")
            plan, value, path = self.authorize(root)
            self.assertEqual(
                [item["slot_id"] for item in value["authorized_slots"]],
                ["slot-001", "slot-002", "slot-003", "slot-004"],
            )
            self.assertEqual(
                read_block_authorization(ROOT, path.absolute(), plan),
                value,
            )
            altered = dict(value)
            altered["block"] = 2
            with self.assertRaises(CaptureError) as caught:
                verify_block_authorization(altered, plan)
            self.assertEqual(
                caught.exception.code,
                "R2_BLOCK_AUTHORIZATION_DIGEST_MISMATCH",
            )
            copied = Path(root) / "copy.json"
            copied.write_bytes(path.read_bytes())
            with self.assertRaises(CaptureError):
                read_block_authorization(
                    ROOT,
                    copied.absolute(),
                    plan,
                )

    def test_slot_state_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan = read_slot_plan(ROOT)
            self.write_run(root, plan["slots"][0])
            state = status_document(ROOT, plan)
            self.assertEqual(state["next_slot"]["slot_id"], "slot-002")
            self.assertEqual(
                state["slots"][0]["capture_state"],
                "initialized",
            )
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan = read_slot_plan(ROOT)
            self.write_run(root, plan["slots"][1])
            with self.assertRaises(CaptureError) as caught:
                scan_slot_states(ROOT, plan)
            self.assertEqual(
                caught.exception.code,
                "R2_SLOT_ORDER_VIOLATION",
            )
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan = read_slot_plan(ROOT)
            self.write_run(root, plan["slots"][0], attempts=2)
            with self.assertRaises(CaptureError) as caught:
                scan_slot_states(ROOT, plan)
            self.assertEqual(
                caught.exception.code,
                "R2_ATTEMPT_LIMIT_EXCEEDED",
            )
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan = read_slot_plan(ROOT)
            self.write_run(
                root,
                plan["slots"][0],
                model="gpt-5.6-luna",
            )
            with self.assertRaises(CaptureError) as caught:
                scan_slot_states(ROOT, plan)
            self.assertEqual(
                caught.exception.code,
                "R2_MODEL_SUBSTITUTION_DETECTED",
            )

    def test_execute_requires_explicit_flag_and_derives_exact_slot(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            _plan, _value, path = self.authorize(root)
            stream = io.StringIO()
            with (
                mock.patch.object(
                    base,
                    "_api_key",
                    side_effect=AssertionError("provider access"),
                ),
                redirect_stdout(stream),
            ):
                code = cli.main(
                    [
                        "execute-next",
                        "--operator",
                        "Matthew Neal",
                        "--block-authorization",
                        str(path),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertEqual(
                json.loads(stream.getvalue())["issue"]["code"],
                "R2_EXECUTION_REQUIRED",
            )

            original = (
                base._build_campaign,
                base._build_request,
                base._emit,
                base.seal_authorization,
            )

            def delegated(argv):
                self.assertIn("gpt-5.6-sol", argv)
                self.assertIn(
                    "openai-gpt56-sol-r2-prose-no-reminder-001",
                    argv,
                )
                self.assertIs(base._build_campaign, cli._build_campaign)
                self.assertIs(base._build_request, cli._build_request)
                self.assertIs(base._emit, cli._emit_live)
                self.assertIs(
                    base.seal_authorization,
                    cli._seal_execution_authorization,
                )
                return 7

            with mock.patch.object(base, "main", side_effect=delegated):
                self.assertEqual(
                    cli.main(
                        [
                            "execute-next",
                            "--operator",
                            "Matthew Neal",
                            "--block-authorization",
                            str(path),
                            "--execute",
                        ]
                    ),
                    7,
                )
            self.assertEqual(
                (
                    base._build_campaign,
                    base._build_request,
                    base._emit,
                    base.seal_authorization,
                ),
                original,
            )

    def test_completed_block_authorization_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan, _value, path = self.authorize(root)
            for slot in plan["slots"][:4]:
                self.write_run(root, slot, attempts=1)
            stream = io.StringIO()
            with (
                mock.patch.object(
                    base,
                    "_api_key",
                    side_effect=AssertionError("provider access"),
                ),
                redirect_stdout(stream),
            ):
                code = cli.main(
                    [
                        "execute-next",
                        "--operator",
                        "Matthew Neal",
                        "--block-authorization",
                        str(path),
                        "--execute",
                    ]
                )
            self.assertEqual(code, 2)
            result = json.loads(stream.getvalue())
            self.assertEqual(
                result["issue"]["code"],
                "R2_BLOCK_OUT_OF_ORDER",
            )
            self.assertFalse(result["provider_request_sent"])

    def test_campaign_request_and_execution_authority_bind_controls(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan, value, _path = self.authorize(root)
            slot = plan["slots"][0]
            (
                cli._ACTIVE_SLOT,
                cli._ACTIVE_BLOCK_AUTHORIZATION,
                cli._ACTIVE_PLAN,
            ) = (slot, value, plan)
            try:
                campaign = cli._build_campaign(
                    slot["model"],
                    self.commit(),
                )
                lock = build_benchmark_lock(campaign, ROOT)
                request_bytes = cli._build_request(slot["model"], 1000)
                sealed = cli._seal_execution_authorization(
                    {
                        "authorization_id": "replaced",
                        "campaign_id": slot["campaign_id"],
                        "execution_id": slot["execution_id"],
                    }
                )
            finally:
                (
                    cli._ACTIVE_SLOT,
                    cli._ACTIVE_BLOCK_AUTHORIZATION,
                    cli._ACTIVE_PLAN,
                ) = (None, None, None)
            self.assertEqual(campaign["run_count"], 12)
            self.assertEqual(
                campaign["execution_plan"]["planned_repetitions"],
                12,
            )
            bound = {
                entry["path"]
                for group in lock["bindings"].values()
                for entry in group
            }
            self.assertIn(cli.SCRIPT_REFERENCE, bound)
            self.assertTrue(cli.MODULE_REFERENCES.issubset(bound))
            self.assertIn(cli.PREREGISTRATION_REFERENCE, bound)
            self.assertTrue(
                set(REQUIRED_ALPHA2_BINDINGS).issubset(bound)
            )
            request = json.loads(request_bytes)
            self.assertEqual(
                request["input"],
                build_condition_prompt(slot["condition_id"], ROOT),
            )
            self.assertFalse(request["store"])
            token = (
                base64.b32encode(
                    bytes.fromhex(value["authorization_sha256"])
                )
                .decode("ascii")
                .rstrip("=")
                .lower()
            )
            self.assertIn(token, sealed["authorization_id"])
            self.assertLessEqual(len(sealed["authorization_id"]), 64)

    def test_live_output_forbids_governance_effects(self):
        with tempfile.TemporaryDirectory() as root, self.env(root):
            initialize_slot_plan(ROOT)
            plan, value, _path = self.authorize(root)
            (
                cli._ACTIVE_SLOT,
                cli._ACTIVE_BLOCK_AUTHORIZATION,
                cli._ACTIVE_PLAN,
            ) = (plan["slots"][0], value, plan)
            stream = io.StringIO()
            try:
                with redirect_stdout(stream):
                    cli._emit_live(
                        {
                            "command": "openai-live-pilot",
                            "status": "captured",
                        }
                    )
            finally:
                (
                    cli._ACTIVE_SLOT,
                    cli._ACTIVE_BLOCK_AUTHORIZATION,
                    cli._ACTIVE_PLAN,
                ) = (None, None, None)
            result = json.loads(stream.getvalue())
            self.assertEqual(result["command"], cli.COMMAND_NAME)
            self.assertEqual(
                result["condition_id"],
                "prose-no-reminder",
            )
            for field in (
                "model_endorsement",
                "ranking",
                "promotion",
                "publication",
                "release",
            ):
                self.assertFalse(result[field])


if __name__ == "__main__":
    unittest.main()
