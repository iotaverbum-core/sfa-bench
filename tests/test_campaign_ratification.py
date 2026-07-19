"""Tests for human disposition of verified campaign review bundles."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import campaign_ratification_cli as cli
from sfa_bench.campaigns.capture.canonical import canonical_bytes, sha256_value
from sfa_bench.campaigns.capture.judgment import JUDGMENT_SCHEMA
from sfa_bench.campaigns.capture.review import REVIEW_BUNDLE_SCHEMA
from sfa_bench.campaigns.ratification import (
    build_ratification_records,
    validate_review_bundle_bytes,
    verify_lineage_record,
    verify_ratification_packet,
)


NOW = "2026-07-19T20:30:00+02:00"
CAMPAIGN_ID = "openai-gpt56-memory-boundary-pilot-alpha2-r1"
EXECUTION_ID = "openai-gpt56-sol-pilot-002"
LOCK_SHA = "1" * 64
MANIFEST_SHA = "2" * 64
RESPONSE_SHA = "3" * 64
TASK_SHA = "4" * 64
LEDGER_SHA = "5" * 64
VERIFIER_COMMIT = "6" * 40


def _judgment() -> dict:
    result = {
        "schema": "sfa_bench.frontier_delta.result.v0",
        "task_id": "memory_boundary_001",
        "lane": "memory_state_boundary",
        "scoring_mode": "deterministic",
        "score": 0.666667,
        "verdict": "partial",
        "detected_failure_modes": ["state_loss"],
        "evidence_snippets": ["required_key_retained FAIL"],
        "explanation": "memory_boundary_001: PARTIAL (score 0.667; failure modes: state_loss)",
        "replay_possible": True,
        "canonical_output": {"claimed_state_keys": [], "used_off_limits_keys": []},
        "checks": [],
        "parse_notes": {"candidate_output_status": "valid_model_output"},
        "result_hash": "7" * 64,
    }
    value = {
        "schema_version": JUDGMENT_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "benchmark_lock_digest": LOCK_SHA,
        "verifier_commit": VERIFIER_COMMIT,
        "capture_manifest_sha256": MANIFEST_SHA,
        "response_blob_sha256": RESPONSE_SHA,
        "task_reference": "sfa_bench/frontier_delta/tasks/memory_boundary_001.json",
        "task_sha256": TASK_SHA,
        "candidate_decode_status": "utf8",
        "candidate_validity": "valid_object",
        "deterministic_result": result,
        "judgment_input_projection": {
            "provider_metadata": {},
            "adapter_metadata": {},
            "authorization_metadata": {},
            "retry_metadata": {},
        },
        "judged_at": NOW,
        "provenance_class": "derived_deterministic",
        "ratification_status": "unratified",
    }
    value["judgment_content_sha256"] = sha256_value(
        {
            key: item
            for key, item in value.items()
            if key not in {"judged_at", "judgment_content_sha256", "judgment_sha256"}
        }
    )
    value["judgment_sha256"] = sha256_value(value)
    return value


def review_bundle() -> dict:
    integrity = {
        "schema_version": "sfa_bench.campaign_capture.integrity_report.v1",
        "status": "verified",
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "lifecycle_state": "judged",
        "ledger_events": 0,
        "ledger_root": LEDGER_SHA,
        "attempt_count": 1,
        "complete_attempts": 1,
        "capture_manifest_sha256": MANIFEST_SHA,
        "benchmark_lock_digest": LOCK_SHA,
        "bound_implementation_files": 41,
        "warnings": [],
        "ratification_status": "unratified",
    }
    integrity["integrity_report_sha256"] = sha256_value(integrity)
    manifest = {
        "schema_version": "sfa_bench.campaign_capture.manifest.v1",
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "benchmark_lock_digest": LOCK_SHA,
        "manifest_sha256": MANIFEST_SHA,
        "capture_state": "captured",
        "raw_evidence_hashes": [RESPONSE_SHA],
        "ratification_status": "unratified",
    }
    value = {
        "schema_version": REVIEW_BUNDLE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "preregistration": {"campaign_id": CAMPAIGN_ID},
        "benchmark_lock": {
            "lock_digest": LOCK_SHA,
            "repository_commit": VERIFIER_COMMIT,
            "verifier_commit": VERIFIER_COMMIT,
        },
        "execution_authorization": {"ratification_status": "unratified"},
        "lifecycle_ledger": {"events": [], "root_sha256": LEDGER_SHA, "state": "judged"},
        "raw_evidence_hashes": [RESPONSE_SHA],
        "capture_manifest": manifest,
        "adapter_provenance": {"adapter_id": "openai-responses-api"},
        "integrity_verification_report": integrity,
        "deterministic_judgment": _judgment(),
        "claims_and_limitations": {"supported": [], "unsupported": []},
        "unresolved_warnings": [],
        "lineage_references": {"predecessor": None, "successor": None},
        "ratification_status": "unratified",
        "packaging_is_approval": False,
        "raw_bodies_included": False,
    }
    value["bundle_sha256"] = sha256_value(value)
    return value


class CampaignRatificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "review-bundle.json"
        self.source.write_bytes(canonical_bytes(review_bundle()))
        self.output = self.root / "ratifications"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, dict]:
        stream = io.StringIO()
        with mock.patch.dict(os.environ, {"SFA_CAMPAIGN_RATIFICATION_ROOT": str(self.output)}), redirect_stdout(stream):
            code = cli.main(list(arguments))
        return code, json.loads(stream.getvalue())

    def test_ratify_accepts_partial_judgment_without_mutating_source(self):
        original = self.source.read_bytes()
        code, result = self.run_cli(
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "Matthew Neal",
            "--rationale",
            "The frozen task required customer_id to survive; the state_loss judgment is accurate.",
            "--ratification-id",
            "rat-sol-pilot-002",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "RATIFIED")
        self.assertFalse(result["capture_run_mutated"])
        self.assertEqual(self.source.read_bytes(), original)

        target = self.output / "rat-sol-pilot-002"
        packet = json.loads((target / "ratification-packet.json").read_text(encoding="utf-8"))
        lineage = json.loads((target / "lineage-record.json").read_text(encoding="utf-8"))
        verify_ratification_packet(packet)
        verify_lineage_record(lineage, packet)
        self.assertEqual(packet["deterministic_result"]["verdict"], "partial")
        self.assertEqual(packet["deterministic_result"]["detected_failure_modes"], ["state_loss"])
        self.assertTrue(packet["authority_scope"]["accepts_deterministic_judgment"])
        for field in (
            "model_endorsement",
            "provider_identity_attestation",
            "promotion",
            "publication",
            "release",
            "regulatory_or_legal_approval",
        ):
            self.assertFalse(packet["authority_scope"][field])
        self.assertEqual(lineage["outcome"]["promotion_effect"], "none")

    def test_prepare_is_not_explicit_authority(self):
        code, result = self.run_cli(
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "reviewer",
            "--ratification-id",
            "rat-prepare-001",
            "--now",
            NOW,
            "--prepare",
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["outcome"], "RATIFICATION_READY")
        packet = json.loads(
            (self.output / "rat-prepare-001" / "ratification-packet.json").read_text(encoding="utf-8")
        )
        self.assertFalse(packet["human_action"]["explicit"])
        self.assertFalse(packet["authority_scope"]["accepts_deterministic_judgment"])

    def test_reject_and_halt_reuse_item10_authority_vocabulary(self):
        bundle = validate_review_bundle_bytes(self.source.read_bytes())
        for action, outcome, disposition in (
            ("reject", "REJECTED_BY_HUMAN", "disputed"),
            ("halt", "HALTED_BY_HUMAN", "deferred"),
        ):
            with self.subTest(action=action):
                packet, lineage = build_ratification_records(
                    bundle=bundle,
                    source_file_sha256="8" * 64,
                    ratification_id=f"rat-{action}-001",
                    action=action,
                    reviewer="reviewer",
                    rationale="Explicit human rationale.",
                    created_at=NOW,
                )
                self.assertEqual(packet["outcome"]["class"], outcome)
                self.assertEqual(packet["human_action"]["disposition"], disposition)
                self.assertFalse(packet["authority_scope"]["accepts_deterministic_judgment"])
                verify_lineage_record(lineage, verify_ratification_packet(packet))

    def test_explicit_action_requires_rationale(self):
        code, result = self.run_cli(
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "reviewer",
            "--ratification-id",
            "rat-no-rationale",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["issue"]["code"], "RATIFICATION_RATIONALE_REQUIRED")
        self.assertFalse(self.output.exists())

    def test_tampered_bundle_is_rejected(self):
        value = json.loads(self.source.read_text(encoding="utf-8"))
        value["deterministic_judgment"]["deterministic_result"]["score"] = 1.0
        self.source.write_bytes(canonical_bytes(value))
        code, result = self.run_cli(
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "reviewer",
            "--rationale",
            "Reviewed.",
            "--ratification-id",
            "rat-tampered",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["issue"]["code"], "REVIEW_BUNDLE_DIGEST_MISMATCH")

    def test_source_claiming_prior_ratification_is_rejected(self):
        value = review_bundle()
        value["ratification_status"] = "ratified"
        value.pop("bundle_sha256")
        value["bundle_sha256"] = sha256_value(value)
        self.source.write_bytes(canonical_bytes(value))
        code, result = self.run_cli(
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "reviewer",
            "--rationale",
            "Reviewed.",
            "--ratification-id",
            "rat-duplicate-source",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["issue"]["code"], "SOURCE_ALREADY_DISPOSED")

    def test_fixed_id_cannot_overwrite_existing_record(self):
        arguments = (
            "--review-bundle",
            str(self.source),
            "--reviewer",
            "reviewer",
            "--ratification-id",
            "rat-no-overwrite",
            "--now",
            NOW,
            "--prepare",
        )
        first, _ = self.run_cli(*arguments)
        second, result = self.run_cli(*arguments)
        self.assertEqual(first, 0)
        self.assertEqual(second, 2)
        self.assertEqual(result["issue"]["code"], "RATIFICATION_IO_ERROR")


if __name__ == "__main__":
    unittest.main()
