"""Tests for hash-bound cohort closure and replication preregistration."""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from sfa_bench.campaigns.capture.canonical import CaptureError, canonical_bytes
from sfa_bench.campaigns.cohort_closure import (
    CLOSURE_SPEC_SCHEMA,
    build_closure_records,
    load_member,
    validate_closure_spec,
    verify_closure_lineage,
    verify_closure_record,
    write_closure_records,
)
from sfa_bench.campaigns.ratification import build_ratification_records

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-07-20T07:00:00+02:00"
SHARED_GROUPS = (
    "cases",
    "rules",
    "taxonomy",
    "normalizer",
    "system_prompt",
    "user_prompt_or_case_set",
)
SHARED = {
    group: [{"path": f"shared/{group}.json", "sha256": char * 64}]
    for group, char in zip(SHARED_GROUPS, ("b", "c", "d", "e", "f", "0"))
}


def _member(
    label: str,
    execution: str,
    *,
    verdict: str = "partial",
    score: float = 0.666667,
    failures: list[str] | None = None,
    result_hash: str = "5" * 64,
) -> dict:
    return {
        "declared_model_label": label,
        "campaign_id": f"campaign-{label}",
        "execution_id": execution,
        "review_bundle_file_sha256": "b" * 64,
        "source_bundle_sha256": "c" * 64,
        "benchmark_lock_digest": "d" * 64,
        "capture_manifest_sha256": "e" * 64,
        "judgment_sha256": "f" * 64,
        "integrity_report_sha256": "0" * 64,
        "ratification_id": f"rat-{execution}",
        "ratification_packet_sha256": result_hash,
        "ratification_packet_file_sha256": "1" * 64,
        "lineage_record_sha256": "2" * 64,
        "lineage_record_file_sha256": "3" * 64,
        "human_disposition": "RATIFIED",
        "verdict": verdict,
        "score": score,
        "detected_failure_modes": list(failures or []),
        "result_hash": result_hash,
        "canonical_output_sha256": "6" * 64,
        "response_text_sha256": "7" * 64,
        "shared_bindings": copy.deepcopy(SHARED),
    }


def _spec(members: list[dict]) -> dict:
    return {
        "schema_version": CLOSURE_SPEC_SCHEMA,
        "closure_id": "closure-test-cohort",
        "cohort_id": "test-cohort",
        "classification": "exploratory_cross_tier_pilot",
        "protocol_reference": "campaigns/examples/openai-gpt56-tier-pilot-protocol.json",
        "members": [
            {
                "declared_model_label": item["declared_model_label"],
                "campaign_id": item["campaign_id"],
                "execution_id": item["execution_id"],
                "ratification_id": item["ratification_id"],
                "requires_protocol_binding": False,
                "source_bundle_sha256": item["source_bundle_sha256"],
                "judgment_sha256": item["judgment_sha256"],
                "ratification_packet_sha256": item["ratification_packet_sha256"],
                "lineage_record_sha256": item["lineage_record_sha256"],
                "verdict": item["verdict"],
                "score": item["score"],
                "detected_failure_modes": item["detected_failure_modes"],
            }
            for item in members
        ],
        "interpretation_limits": ["exploratory only", "no ranking"],
        "authority": {
            "model_endorsement": False,
            "provider_identity_attestation": False,
            "ranking": False,
            "promotion": False,
            "publication": False,
            "release": False,
            "regulatory_or_legal_approval": False,
        },
    }


class CohortClosureTests(unittest.TestCase):
    def members(self) -> list[dict]:
        return [
            _member("gpt-5.6-sol", "sol-001", failures=["state_loss"], result_hash="8" * 64),
            _member("gpt-5.6-terra", "terra-001", failures=["state_loss"], result_hash="8" * 64),
            _member("gpt-5.6-luna", "luna-001", verdict="pass", score=1.0, result_hash="9" * 64),
        ]

    def test_builds_closed_nonranking_record(self):
        members = self.members()
        record, lineage = build_closure_records(
            spec=_spec(members),
            spec_reference="campaigns/examples/test-closure.json",
            spec_file_sha256="a" * 64,
            protocol_sha256="b" * 64,
            members=members,
            closed_by="Matthew Neal",
            created_at=NOW,
        )
        self.assertEqual(record["outcome"]["class"], "COHORT_CLOSED")
        self.assertEqual(record["descriptive_summary"]["verdict_counts"], {"partial": 2, "pass": 1})
        self.assertEqual(record["descriptive_summary"]["failure_mode_counts"], {"state_loss": 2})
        groups = {
            item["result_hash"]: item["execution_ids"]
            for item in record["descriptive_summary"]["result_hash_groups"]
        }
        self.assertEqual(groups["8" * 64], ["sol-001", "terra-001"])
        self.assertFalse(record["interpretation"]["inferential_ranking_authorized"])
        self.assertTrue(all(value is False for value in record["authority_scope"].values()))
        verify_closure_record(record)
        verify_closure_lineage(lineage, record)

    def test_shared_input_mismatch_fails_closed(self):
        members = self.members()
        members[2]["shared_bindings"]["cases"][0]["sha256"] = "a" * 64
        with self.assertRaises(CaptureError) as caught:
            build_closure_records(
                spec=_spec(members),
                spec_reference="campaigns/examples/test-closure.json",
                spec_file_sha256="a" * 64,
                protocol_sha256="b" * 64,
                members=members,
                closed_by="Matthew Neal",
                created_at=NOW,
            )
        self.assertEqual(caught.exception.code, "COHORT_SHARED_INPUT_MISMATCH")

    def test_spec_rejects_ranking_authority(self):
        spec = _spec(self.members())
        spec["authority"]["ranking"] = True
        with self.assertRaises(CaptureError) as caught:
            validate_closure_spec(spec)
        self.assertEqual(caught.exception.code, "COHORT_CLOSURE_AUTHORITY_OVERREACH")

    def test_write_is_exclusive(self):
        members = self.members()
        record, lineage = build_closure_records(
            spec=_spec(members),
            spec_reference="campaigns/examples/test-closure.json",
            spec_file_sha256="a" * 64,
            protocol_sha256="b" * 64,
            members=members,
            closed_by="Matthew Neal",
            created_at=NOW,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = write_closure_records(root, record, lineage)
            self.assertTrue((target / "cohort-closure.json").is_file())
            self.assertTrue((target / "cohort-closure-lineage.json").is_file())
            with self.assertRaises(FileExistsError):
                write_closure_records(root, record, lineage)

    def test_load_member_binds_ratification_and_protocol(self):
        campaign_id = "campaign-terra"
        execution_id = "terra-001"
        protocol_reference = "campaigns/examples/protocol.json"
        protocol_sha = "f" * 64
        bundle = {
            "bundle_sha256": "1" * 64,
            "campaign_id": campaign_id,
            "execution_id": execution_id,
            "benchmark_lock": {
                "lock_digest": "2" * 64,
                "bindings": {
                    **copy.deepcopy(SHARED),
                    "evidence": [{"path": protocol_reference, "sha256": protocol_sha}],
                },
            },
            "capture_manifest": {"manifest_sha256": "3" * 64},
            "deterministic_judgment": {
                "judgment_sha256": "4" * 64,
                "response_blob_sha256": "5" * 64,
                "deterministic_result": {
                    "verdict": "partial",
                    "score": 0.666667,
                    "detected_failure_modes": ["state_loss"],
                    "explanation": "partial",
                    "result_hash": "8" * 64,
                    "parse_notes": {
                        "canonical_output_sha256": "9" * 64,
                        "response_text_sha256": "a" * 64,
                    },
                },
            },
            "integrity_verification_report": {"integrity_report_sha256": "6" * 64},
            "lifecycle_ledger": {"root_sha256": "7" * 64},
        }
        review_file_sha = "b" * 64
        packet, lineage = build_ratification_records(
            bundle=bundle,
            source_file_sha256=review_file_sha,
            ratification_id="rat-terra-001",
            action="ratify",
            reviewer="Matthew Neal",
            rationale="accurate partial",
            created_at=NOW,
        )
        member_spec = {
            "declared_model_label": "gpt-5.6-terra",
            "campaign_id": campaign_id,
            "execution_id": execution_id,
            "ratification_id": "rat-terra-001",
            "requires_protocol_binding": True,
            "source_bundle_sha256": "1" * 64,
            "judgment_sha256": "4" * 64,
            "ratification_packet_sha256": packet["ratification_packet_sha256"],
            "lineage_record_sha256": lineage["lineage_record_sha256"],
            "verdict": "partial",
            "score": 0.666667,
            "detected_failure_modes": ["state_loss"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_root = root / "captures"
            review_path = capture_root / campaign_id / execution_id / "review-bundle.json"
            review_path.parent.mkdir(parents=True)
            review_path.write_bytes(b"placeholder")
            rat_root = root / "ratifications"
            rat_dir = rat_root / "rat-terra-001"
            rat_dir.mkdir(parents=True)
            (rat_dir / "ratification-packet.json").write_bytes(canonical_bytes(packet))
            (rat_dir / "lineage-record.json").write_bytes(canonical_bytes(lineage))
            with mock.patch(
                "sfa_bench.campaigns.cohort_closure.read_validated_review_bundle",
                return_value=(bundle, review_file_sha),
            ):
                loaded = load_member(
                    member_spec,
                    capture_root=capture_root,
                    ratification_root=rat_root,
                    protocol_reference=protocol_reference,
                    protocol_sha256=protocol_sha,
                )
        self.assertEqual(loaded["human_disposition"], "RATIFIED")
        self.assertEqual(loaded["result_hash"], "8" * 64)


class ReplicationPreregistrationTests(unittest.TestCase):
    def test_repeated_replication_is_fresh_fixed_and_balanced(self):
        path = ROOT / "campaigns/examples/openai-gpt56-memory-boundary-replication-r1.json"
        protocol = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(protocol["status"], "preregistered")
        self.assertFalse(protocol["pilot_use"]["included_in_primary_analysis"])
        self.assertFalse(protocol["pilot_use"]["included_in_secondary_analysis"])
        blocks = protocol["execution_blocks"]
        self.assertEqual(len(blocks), 10)
        flattened = [model for block in blocks for model in block["order"]]
        self.assertEqual(
            Counter(flattened),
            Counter({"gpt-5.6-sol": 10, "gpt-5.6-terra": 10, "gpt-5.6-luna": 10}),
        )
        for expected, block in enumerate(blocks, start=1):
            self.assertEqual(block["block"], expected)
            self.assertEqual(
                set(block["order"]),
                {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"},
            )
        self.assertEqual(protocol["stopping_rule"]["planned_authorized_executions"], 30)
        self.assertFalse(protocol["execution_policy"]["automatic_retry"])
        self.assertFalse(protocol["execution_policy"]["silent_model_substitution"])
        self.assertFalse(protocol["stopping_rule"]["optional_stopping"])
        self.assertFalse(protocol["analysis_plan"]["pairwise_model_ranking"])
        self.assertTrue(all(value is False for value in protocol["authority"].values()))


if __name__ == "__main__":
    unittest.main()
