"""Tests for deterministic candidate-evidence successor generation."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from sfa.hashing import sha256_hex
from sfa_bench.frontier_delta import candidate_adapter
from sfa_bench.frontier_delta import candidate_evidence as evidence


REPO_ROOT = Path(evidence.__file__).resolve().parents[2]
RAW = REPO_ROOT / "out" / "fable5_failure_delta" / "raw_outputs.jsonl"
PREDECESSOR = (
    REPO_ROOT / "out" / "fable5_failure_delta" / "scored_results.json"
)
COMMIT = "f09b02f7bd61f8ae8b7cb3e329752819d6c4e923"
ARTIFACT_ID = "fable5-integrity-successor-alpha1"
REASON = "candidate output integrity gate correction"


def _build() -> dict:
    return evidence.build_successor(
        RAW,
        PREDECESSOR,
        artifact_id=ARTIFACT_ID,
        benchmark_commit=COMMIT,
        verifier_commit=COMMIT,
        reason=REASON,
    )


class EvidenceUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(evidence, "_verify_repository_bindings")
        patcher.start()
        self.addCleanup(patcher.stop)


class RepositoryProvenanceTests(unittest.TestCase):
    def test_public_build_rejects_unresolved_benchmark_commit(self):
        with self.assertRaises(evidence.CandidateEvidenceError) as caught:
            evidence.build_successor(
                RAW,
                PREDECESSOR,
                artifact_id=ARTIFACT_ID,
                benchmark_commit="0" * 40,
                verifier_commit=COMMIT,
                reason=REASON,
            )
        self.assertEqual(caught.exception.code, "benchmark_commit_unresolved")

    def test_public_build_rejects_commit_without_bound_implementation(self):
        with self.assertRaises(evidence.CandidateEvidenceError) as caught:
            evidence.build_successor(
                RAW,
                PREDECESSOR,
                artifact_id=ARTIFACT_ID,
                benchmark_commit=COMMIT,
                verifier_commit=COMMIT,
                reason=REASON,
            )
        self.assertEqual(
            caught.exception.code,
            "benchmark_commit_content_mismatch",
        )

    def test_public_verifier_has_no_repository_bypass(self):
        with self.assertRaises(TypeError):
            evidence.verify_successor(
                "unused.json",
                RAW,
                PREDECESSOR,
                verify_repository=False,
            )
        self.assertFalse(hasattr(evidence, "verify_successor_content"))


class SuccessorBuildTests(EvidenceUnitTest):
    def test_build_is_deterministic_and_byte_identical(self):
        first = _build()
        second = _build()
        self.assertEqual(first, second)
        self.assertEqual(
            evidence._artifact_bytes(first),
            evidence._artifact_bytes(second),
        )

    def test_lineage_scores_hashes_and_adapter_version_are_explicit(self):
        predecessor_before = hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest()
        raw_before = hashlib.sha256(RAW.read_bytes()).hexdigest()
        artifact = _build()
        self.assertEqual(
            hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest(),
            predecessor_before,
        )
        self.assertEqual(hashlib.sha256(RAW.read_bytes()).hexdigest(), raw_before)
        self.assertEqual(artifact["artifact_id"], ARTIFACT_ID)
        self.assertEqual(
            artifact["implementation"]["benchmark_commit"],
            COMMIT,
        )
        self.assertEqual(
            artifact["implementation"]["verifier_commit"],
            COMMIT,
        )
        self.assertEqual(
            artifact["lineage"]["predecessor_file_sha256"],
            predecessor_before,
        )
        self.assertEqual(
            artifact["lineage"]["predecessor_reference"],
            f"sha256:{predecessor_before}",
        )
        self.assertEqual(
            artifact["lineage"]["reason_for_regeneration"],
            REASON,
        )
        self.assertFalse(artifact["lineage"]["historical_artifact_mutated"])
        self.assertEqual(
            artifact["source_evidence"]["raw_jsonl_file_sha256"],
            raw_before,
        )
        self.assertEqual(
            artifact["implementation"]["candidate_adapter_version"],
            candidate_adapter.CANDIDATE_ADAPTER_VERSION,
        )
        self.assertEqual(
            artifact["scoring_status"]["predecessor"]["total_score"],
            0.770833,
        )
        self.assertEqual(
            artifact["scoring_status"]["successor"]["total_score"],
            0.6875,
        )
        self.assertEqual(
            artifact["scoring_status"]["successor"]["invalid_output_counts"],
            {"no_model_output": 2},
        )
        seal = artifact.pop("canonical_artifact_sha256")
        self.assertEqual(seal, sha256_hex(artifact))

    def test_empty_fable_responses_are_invalid_not_default_scored(self):
        artifact = _build()
        by_task = {row["task_id"]: row for row in artifact["per_task"]}
        for task_id in ("memory_boundary_001", "audit_replayability_001"):
            result = by_task[task_id]["corrected_result"]
            self.assertEqual(result["score"], 0.0)
            self.assertEqual(result["verdict"], "fail")
            self.assertEqual(
                result["detected_failure_modes"],
                ["no_model_output"],
            )
            self.assertIsNone(result["canonical_output"])

    def test_artifact_contains_references_not_provider_payloads(self):
        text = evidence._artifact_bytes(_build()).decode("utf-8")
        self.assertNotIn('"api_response"', text)
        self.assertNotIn('"raw_response_body"', text)
        self.assertIn('"response_text_sha256"', text)
        self.assertIn('"raw_response_body_sha256"', text)

    def test_write_is_atomic_deterministic_and_never_overwrites(self):
        artifact = _build()
        with tempfile.TemporaryDirectory() as first_tmp:
            with tempfile.TemporaryDirectory() as second_tmp:
                first = evidence.write_successor(artifact, first_tmp)
                second = evidence.write_successor(artifact, second_tmp)
                self.assertEqual(first.name, f"{ARTIFACT_ID}.json")
                self.assertEqual(first.read_bytes(), second.read_bytes())
                with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                    evidence.write_successor(artifact, first_tmp)
                self.assertEqual(caught.exception.code, "successor_already_exists")

    def test_invalid_artifact_ids_reject_path_components(self):
        for artifact_id in ("../escape", "..", "a/b", "a\\b", ""):
            with self.subTest(artifact_id=artifact_id):
                with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                    evidence.build_successor(
                        RAW,
                        PREDECESSOR,
                        artifact_id=artifact_id,
                        benchmark_commit=COMMIT,
                        verifier_commit=COMMIT,
                        reason=REASON,
                    )
                self.assertEqual(caught.exception.code, "artifact_id_invalid")

    def test_cli_output_path_cannot_escape_repository_out(self):
        with self.assertRaises(evidence.CandidateEvidenceError) as caught:
            evidence._resolve_cli_output_root(REPO_ROOT, "../escape")
        self.assertEqual(
            caught.exception.code,
            "output_path_outside_approved_root",
        )


class SuccessorVerifyTests(EvidenceUnitTest):
    def _build_from_copies(
        self,
        root: Path,
    ) -> tuple[Path, Path, Path]:
        raw = root / "raw_outputs.jsonl"
        predecessor = root / "scored_results.json"
        shutil.copyfile(RAW, raw)
        shutil.copyfile(PREDECESSOR, predecessor)
        artifact = evidence.build_successor(
            raw,
            predecessor,
            artifact_id=ARTIFACT_ID,
            benchmark_commit=COMMIT,
            verifier_commit=COMMIT,
            reason=REASON,
        )
        artifact_path = root / "successor.json"
        artifact_path.write_bytes(evidence._artifact_bytes(artifact))
        return raw, predecessor, artifact_path

    def test_verify_rederives_without_mutating_any_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, predecessor, artifact = self._build_from_copies(Path(tmp))
            paths = (
                raw,
                predecessor,
                Path(candidate_adapter.__file__),
                artifact,
            )
            before = {path: path.read_bytes() for path in paths}
            result = evidence.verify_successor(
                artifact,
                raw,
                predecessor,
            )
            after = {path: path.read_bytes() for path in paths}
        self.assertEqual(before, after)
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "candidate_evidence_verified")

    def test_verify_detects_raw_and_predecessor_drift(self):
        drift_cases = (
            ("raw", "raw_evidence_digest_mismatch"),
            ("predecessor", "predecessor_digest_mismatch"),
        )
        for target, expected_code in drift_cases:
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as tmp:
                    raw, predecessor, artifact = (
                        self._build_from_copies(Path(tmp))
                    )
                    selected = {
                        "raw": raw,
                        "predecessor": predecessor,
                    }[target]
                    selected.write_bytes(selected.read_bytes() + b"\n")
                    with self.assertRaises(
                        evidence.CandidateEvidenceError
                    ) as caught:
                        evidence.verify_successor(
                            artifact,
                            raw,
                            predecessor,
                        )
                self.assertEqual(caught.exception.code, expected_code)

    def test_verify_detects_adapter_digest_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, predecessor, artifact_path = self._build_from_copies(
                Path(tmp)
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["implementation"]["candidate_adapter_sha256"] = "0" * 64
            artifact["canonical_artifact_sha256"] = sha256_hex(
                {
                    key: value
                    for key, value in artifact.items()
                    if key != "canonical_artifact_sha256"
                }
            )
            artifact_path.write_bytes(evidence._artifact_bytes(artifact))
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.verify_successor(
                    artifact_path,
                    raw,
                    predecessor,
                )
        self.assertEqual(
            caught.exception.code,
            "candidate_adapter_digest_mismatch",
        )

    def test_verify_detects_task_digest_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, predecessor, artifact_path = (
                self._build_from_copies(Path(tmp))
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            task = artifact["source_evidence"]["task_files"][
                "memory_boundary_001"
            ]
            task["sha256"] = "0" * 64
            artifact["canonical_artifact_sha256"] = sha256_hex(
                {
                    key: value
                    for key, value in artifact.items()
                    if key != "canonical_artifact_sha256"
                }
            )
            artifact_path.write_bytes(evidence._artifact_bytes(artifact))
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.verify_successor(
                    artifact_path,
                    raw,
                    predecessor,
                )
        self.assertEqual(caught.exception.code, "task_digest_mismatch")

    def test_verify_detects_seal_and_rederivation_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, predecessor, artifact_path = (
                self._build_from_copies(Path(tmp))
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["artifact_id"] = "tampered"
            artifact_path.write_bytes(evidence._artifact_bytes(artifact))
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.verify_successor(
                    artifact_path,
                    raw,
                    predecessor,
                )
            self.assertEqual(caught.exception.code, "successor_seal_mismatch")

            artifact = evidence.build_successor(
                raw,
                predecessor,
                artifact_id=ARTIFACT_ID,
                benchmark_commit=COMMIT,
                verifier_commit=COMMIT,
                reason=REASON,
            )
            artifact["scoring_status"]["successor"]["total_score"] = 1.0
            artifact["canonical_artifact_sha256"] = sha256_hex(
                {
                    key: value
                    for key, value in artifact.items()
                    if key != "canonical_artifact_sha256"
                }
            )
            artifact_path.write_bytes(evidence._artifact_bytes(artifact))
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.verify_successor(
                    artifact_path,
                    raw,
                    predecessor,
                )
        self.assertEqual(
            caught.exception.code,
            "successor_rederivation_mismatch",
        )

    def test_verify_rejects_nondeterministic_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, predecessor, artifact_path = (
                self._build_from_copies(Path(tmp))
            )
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.verify_successor(
                    artifact_path,
                    raw,
                    predecessor,
                )
        self.assertEqual(
            caught.exception.code,
            "successor_serialization_mismatch",
        )


class CandidateEvidenceCliTests(EvidenceUnitTest):
    def test_build_verify_and_no_overwrite_return_machine_readable_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_root = root / "out" / "successors"
            build_args = [
                "build",
                "--raw",
                str(RAW),
                "--predecessor",
                str(PREDECESSOR),
                "--artifact-id",
                ARTIFACT_ID,
                "--benchmark-commit",
                COMMIT,
                "--verifier-commit",
                COMMIT,
                "--reason",
                REASON,
                "--output-root",
                str(output_root),
            ]
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = evidence.main(build_args, repo_root=root)
            payload = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            artifact = root / payload["output_path"]
            self.assertTrue(artifact.is_file())

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = evidence.main(
                    [
                        "verify",
                        "--artifact",
                        str(artifact),
                        "--raw",
                        str(RAW),
                        "--predecessor",
                        str(PREDECESSOR),
                    ],
                    repo_root=root,
                )
            verified = json.loads(stream.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(
                verified["code"],
                "candidate_evidence_verified",
            )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = evidence.main(build_args, repo_root=root)
            refused = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["code"], "successor_already_exists")

    def test_cli_rejects_output_escape_with_stable_error(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = evidence.main(
                [
                    "build",
                    "--raw",
                    str(RAW),
                    "--predecessor",
                    str(PREDECESSOR),
                    "--artifact-id",
                    ARTIFACT_ID,
                    "--benchmark-commit",
                    COMMIT,
                    "--verifier-commit",
                    COMMIT,
                    "--reason",
                    REASON,
                    "--output-root",
                    "../escape",
                ],
                repo_root=REPO_ROOT,
            )
        payload = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(
            payload["code"],
            "output_path_outside_approved_root",
        )

    def test_raw_evidence_without_response_text_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.jsonl"
            raw.write_text(
                '{"task_id":"memory_boundary_001"}\n',
                encoding="utf-8",
            )
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.build_successor(
                    raw,
                    PREDECESSOR,
                    artifact_id=ARTIFACT_ID,
                    benchmark_commit=COMMIT,
                    verifier_commit=COMMIT,
                    reason=REASON,
                )
        self.assertEqual(
            caught.exception.code,
            "raw_evidence_response_text_missing",
        )

    def test_tampered_captured_raw_response_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.jsonl"
            rows = [
                json.loads(line)
                for line in RAW.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            rows[0]["raw_response_sha256"] = "0" * 64
            raw.write_text(
                "".join(
                    json.dumps(row, sort_keys=True) + "\n"
                    for row in rows
                ),
                encoding="utf-8",
            )
            with self.assertRaises(evidence.CandidateEvidenceError) as caught:
                evidence.build_successor(
                    raw,
                    PREDECESSOR,
                    artifact_id=ARTIFACT_ID,
                    benchmark_commit=COMMIT,
                    verifier_commit=COMMIT,
                    reason=REASON,
                )
        self.assertEqual(
            caught.exception.code,
            "captured_raw_response_digest_mismatch",
        )
