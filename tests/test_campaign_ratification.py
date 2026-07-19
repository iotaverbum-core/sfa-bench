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
from sfa_bench.campaigns.capture.lifecycle import EVENT_SCHEMA, ZERO_HASH
from sfa_bench.campaigns.capture.review import REVIEW_BUNDLE_SCHEMA
from sfa_bench.campaigns.capture.run import CAPTURE_MANIFEST_SCHEMA
from sfa_bench.campaigns.locking import benchmark_lock_digest
from sfa_bench.campaigns.protocol import BENCHMARK_LOCK_SCHEMA
from sfa_bench.campaigns.ratification import (
    build_ratification_records,
    validate_review_bundle_bytes,
    verify_lineage_record,
    verify_ratification_packet,
)


NOW = "2026-07-19T20:30:00+02:00"
CAMPAIGN_ID = "openai-gpt56-memory-boundary-pilot-alpha2-r1"
EXECUTION_ID = "openai-gpt56-sol-pilot-002"
REPOSITORY_COMMIT = "6" * 40
VERIFIER_COMMIT = "7" * 40
REQUEST_SHA = "1" * 64
RESPONSE_SHA = "2" * 64
TASK_SHA = "3" * 64
CAPTURE_CONTENT_SHA = "4" * 64
AUTHORIZATION_SHA = "5" * 64


def _lock() -> dict:
    value = {
        "schema_version": BENCHMARK_LOCK_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "campaign_digest": "8" * 64,
        "repository_commit": REPOSITORY_COMMIT,
        "verifier_commit": VERIFIER_COMMIT,
        "release_identifier": "v2.0.0-alpha.2",
        "declared_commands": [],
        "declared_input_digests": {
            "cases": "9" * 64,
            "rules": "a" * 64,
            "taxonomy": "b" * 64,
            "system_prompt": "c" * 64,
            "user_prompt_or_case_set": "d" * 64,
        },
        "bindings": {},
        "digest_scope": {
            "excluded_fields": ["envelope", "lock_digest"],
            "campaign_excluded_fields": ["benchmark_lock"],
        },
    }
    value["lock_digest"] = benchmark_lock_digest(value)
    return value


def _event(
    events: list[dict],
    *,
    event_type: str,
    from_state: str | None,
    to_state: str,
    payload: dict,
    transition: bool = True,
) -> dict:
    sequence = len(events)
    value = {
        "schema_version": EVENT_SCHEMA,
        "sequence": sequence,
        "event_id": f"{EXECUTION_ID}:{sequence:08d}:{event_type}",
        "execution_id": EXECUTION_ID,
        "event_type": event_type,
        "transition": transition,
        "from_state": from_state,
        "to_state": to_state,
        "observed_at": NOW,
        "previous_event_sha256": events[-1]["event_sha256"] if events else ZERO_HASH,
        "payload": payload,
    }
    value["event_sha256"] = sha256_value(value)
    events.append(value)
    return value


def _initial_events(lock_digest: str) -> list[dict]:
    events: list[dict] = []
    _event(events, event_type="run_drafted", from_state=None, to_state="draft", payload={"campaign_id": CAMPAIGN_ID})
    _event(events, event_type="campaign_validated", from_state="draft", to_state="validated", payload={"validation": "passed"})
    _event(events, event_type="benchmark_locked", from_state="validated", to_state="locked", payload={"benchmark_lock_digest": lock_digest})
    _event(
        events,
        event_type="execution_authorization_bound",
        from_state="locked",
        to_state="execution_authorized",
        payload={"authorization_digest": AUTHORIZATION_SHA, "scope": "execution_only", "ratification_status": "unratified"},
    )
    _event(events, event_type="capture_started", from_state="execution_authorized", to_state="capturing", payload={"attempt_number": 1})
    _event(events, event_type="request_preserved", from_state="capturing", to_state="capturing", payload={"attempt_number": 1, "request_sha256": REQUEST_SHA}, transition=False)
    _event(events, event_type="response_preserved", from_state="capturing", to_state="capturing", payload={"attempt_number": 1, "response_sha256": RESPONSE_SHA}, transition=False)
    _event(events, event_type="capture_completed", from_state="capturing", to_state="captured", payload={"attempt_number": 1, "complete": True})
    return events


def _manifest(lock: dict, preseal_root: str) -> dict:
    value = {
        "schema_version": CAPTURE_MANIFEST_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "benchmark_lock_digest": lock["lock_digest"],
        "benchmark_commit": REPOSITORY_COMMIT,
        "verifier_commit": VERIFIER_COMMIT,
        "release_identifier": "v2.0.0-alpha.2",
        "authorization_digest": AUTHORIZATION_SHA,
        "adapter": {
            "adapter_id": "openai-responses-api",
            "adapter_version": "sfa_bench.openai_responses_adapter.v1",
            "implementation_path": "sfa_bench/campaigns/capture/openai_responses.py",
        },
        "prompt_reference": "campaigns/examples/prompts/gpt56-study-system-prompt.txt",
        "case_reference": "sfa_bench/frontier_delta/tasks/memory_boundary_001.json",
        "attempts": [
            {
                "attempt_number": 1,
                "retry_reason": None,
                "transport_status": "completed",
                "complete": True,
                "request_sha256": REQUEST_SHA,
                "response_sha256": RESPONSE_SHA,
                "response_byte_length": 256,
                "provider_request_id": None,
                "warnings": [],
                "attempt_digest": "e" * 64,
            }
        ],
        "raw_evidence_hashes": [REQUEST_SHA, RESPONSE_SHA],
        "capture_state": "captured",
        "ledger_root_before_seal": preseal_root,
        "capture_started_at": NOW,
        "capture_completed_at": NOW,
        "warnings": [],
        "provenance_classes": [
            "git_verified",
            "capture_observed",
            "provider_declared_unverified",
            "adapter_declared",
            "operator_declared",
        ],
        "ratification_status": "unratified",
        "capture_content_sha256": CAPTURE_CONTENT_SHA,
    }
    value["manifest_sha256"] = sha256_value(value)
    return value


def _judgment(lock: dict, manifest: dict) -> dict:
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
        "result_hash": "f" * 64,
    }
    value = {
        "schema_version": JUDGMENT_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "benchmark_lock_digest": lock["lock_digest"],
        "verifier_commit": VERIFIER_COMMIT,
        "capture_manifest_sha256": manifest["manifest_sha256"],
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
    lock = _lock()
    events = _initial_events(lock["lock_digest"])
    manifest = _manifest(lock, events[-1]["event_sha256"])
    _event(
        events,
        event_type="capture_sealed",
        from_state="captured",
        to_state="sealed",
        payload={
            "manifest_sha256": manifest["manifest_sha256"],
            "capture_content_sha256": CAPTURE_CONTENT_SHA,
        },
    )
    judgment = _judgment(lock, manifest)
    _event(
        events,
        event_type="judgment_sealed",
        from_state="sealed",
        to_state="judged",
        payload={
            "judgment_sha256": judgment["judgment_sha256"],
            "verifier_commit": VERIFIER_COMMIT,
        },
    )
    ledger_root = events[-1]["event_sha256"]
    integrity = {
        "schema_version": "sfa_bench.campaign_capture.integrity_report.v1",
        "status": "verified",
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "lifecycle_state": "judged",
        "ledger_events": len(events),
        "ledger_root": ledger_root,
        "attempt_count": 1,
        "complete_attempts": 1,
        "capture_manifest_sha256": manifest["manifest_sha256"],
        "benchmark_lock_digest": lock["lock_digest"],
        "bound_implementation_files": 41,
        "warnings": [],
        "ratification_status": "unratified",
    }
    integrity["integrity_report_sha256"] = sha256_value(integrity)
    value = {
        "schema_version": REVIEW_BUNDLE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "execution_id": EXECUTION_ID,
        "preregistration": {"campaign_id": CAMPAIGN_ID},
        "benchmark_lock": lock,
        "execution_authorization": {"ratification_status": "unratified"},
        "lifecycle_ledger": {"events": events, "root_sha256": ledger_root, "state": "judged"},
        "raw_evidence_hashes": [REQUEST_SHA, RESPONSE_SHA],
        "capture_manifest": manifest,
        "adapter_provenance": {"adapter_id": "openai-responses-api"},
        "integrity_verification_report": integrity,
        "deterministic_judgment": judgment,
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
        with mock.patch.dict(
            os.environ,
            {"SFA_CAMPAIGN_RATIFICATION_ROOT": str(self.output)},
        ), redirect_stdout(stream):
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

    def test_outer_bundle_tampering_is_rejected(self):
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

    def test_inner_manifest_tampering_is_rejected_even_with_resealed_bundle(self):
        value = review_bundle()
        value["capture_manifest"]["warnings"] = ["injected"]
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
            "rat-manifest-tampered",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["issue"]["code"], "CAPTURE_MANIFEST_DIGEST_MISMATCH")

    def test_lifecycle_chain_tampering_is_rejected_even_with_resealed_bundle(self):
        value = review_bundle()
        value["lifecycle_ledger"]["events"][0]["payload"]["injected"] = True
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
            "rat-ledger-tampered",
            "--now",
            NOW,
            "--ratify",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["issue"]["code"], "EVENT_HASH_MISMATCH")

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
