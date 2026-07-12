"""Adversarial tests for alpha.2 locked campaign capture."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import unittest
from unittest import mock

from sfa_bench.campaigns.capture.adapters import (
    LockedCaptureRequest,
    SyntheticAdapter,
    TransportResult,
    sanitize_transport_metadata,
)
from sfa_bench.campaigns.capture.authorization import (
    AUTHORIZATION_SCHEMA,
    seal_authorization,
    validate_authorization,
)
from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    canonical_bytes,
    ensure_no_reparse_ancestors,
    sha256_bytes,
    strict_json_loads,
    validate_repo_relative_path,
    validate_safe_id,
    write_exclusive_json,
)
from sfa_bench.campaigns.capture.judgment import judge_run, verify_judgment
from sfa_bench.campaigns.capture.lifecycle import (
    append_occurrence,
    append_transition,
    verify_ledger,
)
from sfa_bench.campaigns.capture.review import build_review_bundle, verify_review_bundle
from sfa_bench.campaigns.capture.run import (
    capture_attempt,
    initialize_run,
    recover_run,
    seal_run,
    verify_run,
)
from sfa_bench.campaigns.capture.storage import read_blob, reserve_run


ROOT = Path(__file__).resolve().parents[1]
TASK_REFERENCE = "sfa_bench/frontier_delta/tasks/memory_boundary_001.json"
PROMPT_REFERENCE = "campaigns/examples/prompts/gpt56-study-system-prompt.txt"
REQUEST = b'{"synthetic":"request"}'
NOW = "2026-07-12T20:00:00+02:00"


class CaptureUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output_root = Path(self.temp.name) / "runs"

    def tearDown(self):
        self.temp.cleanup()

    def context(self, *, max_attempts=1, reasons=None, execution_id="exec-1"):
        reasons = list(reasons or [])
        adapter = SyntheticAdapter("valid_json_object")
        task_digest = sha256_bytes((ROOT / TASK_REFERENCE).read_bytes())
        prompt_digest = sha256_bytes((ROOT / PROMPT_REFERENCE).read_bytes())
        bindings = {
            adapter.implementation_path: "a" * 64,
            TASK_REFERENCE: task_digest,
            PROMPT_REFERENCE: prompt_digest,
        }
        lock = {
            "lock_digest": "b" * 64,
            "repository_commit": "c" * 40,
            "verifier_commit": "d" * 40,
            "release_identifier": "v2.0.0-alpha.1",
            "bindings": {
                "adapter": [{"path": adapter.implementation_path, "sha256": "a" * 64}],
                "cases": [{"path": TASK_REFERENCE, "sha256": task_digest}],
                "system_prompt": [{"path": PROMPT_REFERENCE, "sha256": prompt_digest}],
            },
        }
        campaign = {
            "campaign_id": "campaign-1",
            "retry_policy": {"max_attempts": max_attempts, "retry_conditions": reasons},
        }
        authorization = seal_authorization(
            {
                "schema_version": AUTHORIZATION_SCHEMA,
                "authorization_id": f"auth-{execution_id}",
                "campaign_id": campaign["campaign_id"],
                "benchmark_lock_digest": lock["lock_digest"],
                "benchmark_commit": lock["repository_commit"],
                "verifier_commit": lock["verifier_commit"],
                "release_identifier": lock["release_identifier"],
                "execution_id": execution_id,
                "adapter": {
                    "adapter_id": adapter.adapter_id,
                    "adapter_version": adapter.adapter_version,
                    "implementation_path": adapter.implementation_path,
                },
                "request": {
                    "sha256": sha256_bytes(REQUEST),
                    "byte_length": len(REQUEST),
                    "prompt_reference": PROMPT_REFERENCE,
                    "case_reference": TASK_REFERENCE,
                },
                "retry_policy": {"max_attempts": max_attempts, "allowed_reasons": reasons},
                "operator_declaration": {
                    "identity": "declared-test-operator",
                    "authority_type": "declared_human_operator",
                    "authorization_scope": "execution_only",
                },
                "issued_at": NOW,
                "ratification_status": "unratified",
                "automatic_actions": {
                    "ratify": False,
                    "promote": False,
                    "publish": False,
                    "release": False,
                },
            }
        )
        return campaign, lock, authorization, adapter, bindings

    def initialize(self, *, max_attempts=1, reasons=None, execution_id="exec-1", mode="valid_json_object"):
        campaign, lock, authorization, _adapter, bindings = self.context(
            max_attempts=max_attempts, reasons=reasons, execution_id=execution_id
        )
        adapter = SyntheticAdapter(mode)
        with mock.patch(
            "sfa_bench.campaigns.capture.run.verify_governed_context",
            return_value=bindings,
        ):
            run_dir = initialize_run(
                campaign=campaign,
                lock=lock,
                authorization=authorization,
                request_bytes=REQUEST,
                adapter=adapter,
                repo_root=ROOT,
                output_root=self.output_root,
                observed_at=NOW,
            )
        return run_dir, campaign, lock, authorization, adapter, bindings

    def trusted(self, bindings):
        return mock.patch(
            "sfa_bench.campaigns.capture.run.verify_governed_context",
            return_value=bindings,
        )


class CanonicalBoundaryTests(CaptureUnitTest):
    def test_strict_json_rejects_duplicate_nonfinite_and_unpaired_unicode(self):
        for payload, code in (
            ('{"x":1,"x":2}', "DUPLICATE_JSON_KEY"),
            ('{"x":NaN}', "NONSTANDARD_JSON_CONSTANT"),
            ('{"x":"\\ud800"}', "INVALID_UNICODE_SCALAR"),
        ):
            with self.subTest(payload=payload), self.assertRaises(CaptureError) as caught:
                strict_json_loads(payload)
            self.assertEqual(caught.exception.code, code)

    def test_noncanonical_json_has_one_canonical_form(self):
        self.assertEqual(canonical_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_portable_paths_reject_escape_reserved_and_control_paths(self):
        for value in ("../x", "C:/x", "//host/x", ".git/config", "out/.git/config", "out/CON/file", "x:/ads"):
            with self.subTest(value=value), self.assertRaises(CaptureError):
                validate_repo_relative_path(value, "$.path")

    def test_reparse_ancestor_is_rejected(self):
        root = Path(self.temp.name) / "root"
        link = root / "link"
        link.mkdir(parents=True)
        with mock.patch(
            "sfa_bench.campaigns.capture.canonical._is_reparse_point",
            side_effect=lambda path: path == link,
        ), self.assertRaises(CaptureError) as caught:
            ensure_no_reparse_ancestors(root, link / "artifact.json")
        self.assertEqual(caught.exception.code, "REPARSE_POINT_REJECTED")

    def test_ids_reject_unicode_and_windows_reserved_names(self):
        for value in ("Upper", "é", "CON", ".."):
            with self.subTest(value=value), self.assertRaises(CaptureError):
                validate_safe_id(value, "$.id")

    def test_metadata_rejects_credentials_and_governance_claims(self):
        with self.assertRaises(CaptureError) as credential:
            sanitize_transport_metadata({"authorization": "Bearer abcdefghijklmnop"})
        self.assertEqual(credential.exception.code, "TRANSPORT_METADATA_NOT_ALLOWLISTED")
        with self.assertRaises(CaptureError) as governance:
            sanitize_transport_metadata({"provider_model_label": "official approved model"})
        self.assertEqual(governance.exception.code, "GOVERNANCE_CLAIM_REJECTED")

    def test_raw_line_endings_and_binary_bytes_are_not_normalized(self):
        self.assertNotEqual(sha256_bytes(b"a\n"), sha256_bytes(b"a\r\n"))
        self.assertEqual(bytes.fromhex("fffe0080"), b"\xff\xfe\x00\x80")


class LifecycleTests(CaptureUnitTest):
    def ledger_run(self):
        run = reserve_run(self.output_root, "campaign-1", "exec-1")
        write_exclusive_json(run / "run.json", {"execution_id": "exec-1"})
        return run

    def test_full_legal_lifecycle_is_explicit(self):
        run = self.ledger_run()
        for state in (
            "draft", "validated", "locked", "execution_authorized", "capturing",
            "captured", "sealed", "judged", "review_required",
        ):
            append_transition(run, state, observed_at=NOW)
        self.assertEqual(verify_ledger(run).state, "review_required")

    def test_skipped_repeated_and_contradictory_transitions_fail(self):
        run = self.ledger_run()
        append_transition(run, "draft", observed_at=NOW)
        for state in ("locked", "draft"):
            with self.subTest(state=state), self.assertRaises(CaptureError) as caught:
                append_transition(run, state, observed_at=NOW)
            self.assertEqual(caught.exception.code, "ILLEGAL_LIFECYCLE_TRANSITION")

    def test_removed_reordered_inserted_and_modified_events_are_detected(self):
        run = self.ledger_run()
        for state in ("draft", "validated", "locked"):
            append_transition(run, state, observed_at=NOW)
        events = run / "ledger/events"
        original = (events / "00000001.json").read_bytes()
        (events / "00000001.json").unlink()
        with self.assertRaises(CaptureError):
            verify_ledger(run)
        (events / "00000001.json").write_bytes(original)
        value = json.loads((events / "00000001.json").read_text(encoding="utf-8"))
        value["payload"]["injected"] = True
        (events / "00000001.json").write_bytes(canonical_bytes(value))
        with self.assertRaises(CaptureError) as caught:
            verify_ledger(run)
        self.assertEqual(caught.exception.code, "EVENT_HASH_MISMATCH")

    def test_concurrent_next_event_collision_has_one_winner(self):
        run = self.ledger_run()
        append_transition(run, "draft", observed_at=NOW)
        barrier = threading.Barrier(2)
        outcomes = []

        def writer():
            barrier.wait()
            try:
                append_transition(run, "validated", observed_at=NOW)
                outcomes.append("ok")
            except CaptureError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=writer) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(verify_ledger(run).state, "validated")


class AuthorizationTests(CaptureUnitTest):
    def test_authorization_binds_campaign_lock_execution_adapter_request_and_retry(self):
        campaign, lock, authorization, adapter, _bindings = self.context()
        summary = validate_authorization(
            authorization,
            campaign=campaign,
            lock=lock,
            request_bytes=REQUEST,
            adapter=adapter,
        )
        self.assertEqual(summary["scope"], "execution_only")
        mutations = (
            ("campaign_id", "other"),
            ("benchmark_lock_digest", "e" * 64),
            ("release_identifier", "v9.9.9"),
        )
        for field, value in mutations:
            changed = copy.deepcopy(authorization)
            changed[field] = value
            changed = seal_authorization(changed)
            with self.subTest(field=field), self.assertRaises(CaptureError):
                validate_authorization(
                    changed, campaign=campaign, lock=lock, request_bytes=REQUEST, adapter=adapter
                )
        changed = copy.deepcopy(authorization)
        changed["execution_id"] = "other-exec"
        with self.assertRaises(CaptureError) as execution_scope:
            validate_authorization(
                changed, campaign=campaign, lock=lock, request_bytes=REQUEST, adapter=adapter
            )
        self.assertEqual(execution_scope.exception.code, "AUTHORIZATION_DIGEST_MISMATCH")

    def test_automatic_governance_and_ratification_fail_closed(self):
        campaign, lock, authorization, adapter, _bindings = self.context()
        for field in ("ratify", "promote", "publish", "release"):
            changed = copy.deepcopy(authorization)
            changed["automatic_actions"][field] = True
            changed = seal_authorization(changed)
            with self.subTest(field=field), self.assertRaises(CaptureError) as caught:
                validate_authorization(
                    changed, campaign=campaign, lock=lock, request_bytes=REQUEST, adapter=adapter
                )
            self.assertEqual(caught.exception.code, "AUTOMATIC_GOVERNANCE_FORBIDDEN")
        changed = copy.deepcopy(authorization)
        changed["ratification_status"] = "ratified"
        changed = seal_authorization(changed)
        with self.assertRaises(CaptureError) as caught:
            validate_authorization(changed, campaign=campaign, lock=lock, request_bytes=REQUEST, adapter=adapter)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_CANNOT_RATIFY")

    def test_false_request_and_retry_policy_are_rejected(self):
        campaign, lock, authorization, adapter, _bindings = self.context()
        with self.assertRaises(CaptureError) as request_error:
            validate_authorization(
                authorization, campaign=campaign, lock=lock, request_bytes=b"changed", adapter=adapter
            )
        self.assertEqual(request_error.exception.code, "AUTHORIZATION_SCOPE_MISMATCH")
        changed = copy.deepcopy(authorization)
        changed["retry_policy"]["max_attempts"] = 2
        changed = seal_authorization(changed)
        with self.assertRaises(CaptureError) as retry_error:
            validate_authorization(changed, campaign=campaign, lock=lock, request_bytes=REQUEST, adapter=adapter)
        self.assertEqual(retry_error.exception.code, "RETRY_POLICY_MISMATCH")


class CaptureFlowTests(CaptureUnitTest):
    def full_run(self, mode="valid_json_object", execution_id="exec-1"):
        run, _campaign, _lock, _authorization, adapter, bindings = self.initialize(
            mode=mode, execution_id=execution_id
        )
        with self.trusted(bindings):
            attempt = capture_attempt(
                run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW
            )
        return run, attempt, bindings

    def test_valid_synthetic_capture_seals_judges_and_bundles_unratified(self):
        run, attempt, bindings = self.full_run()
        self.assertTrue(attempt["complete"])
        self.assertEqual(read_blob(run, attempt["request_blob"]), REQUEST)
        with self.trusted(bindings):
            manifest = seal_run(run, repo_root=ROOT, observed_at=NOW)
            judgment = judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
            bundle = build_review_bundle(run, repo_root=ROOT, observed_at=NOW)
            report = verify_run(run, repo_root=ROOT)
            verify_review_bundle(run, repo_root=ROOT)
        self.assertEqual(report["lifecycle_state"], "review_required")
        self.assertEqual(manifest["ratification_status"], "unratified")
        self.assertEqual(judgment["judgment_input_projection"]["provider_metadata"], {})
        self.assertEqual(bundle["ratification_status"], "unratified")
        self.assertFalse(bundle["packaging_is_approval"])
        self.assertFalse(bundle["raw_bodies_included"])
        self.assertTrue(bundle["execution_authorization"]["operator_declaration"]["identity_redacted"])
        self.assertNotIn("declared-test-operator", canonical_bytes(bundle).decode("utf-8"))

    def test_invalid_and_binary_outputs_get_explicit_zero_credit(self):
        modes = (
            "empty_output", "refusal_plaintext", "malformed_json", "non_object_json",
            "non_finite_json", "binary_non_utf8",
        )
        for index, mode in enumerate(modes):
            with self.subTest(mode=mode):
                run, attempt, bindings = self.full_run(mode, f"invalid-{index}")
                self.assertTrue(attempt["complete"])
                with self.trusted(bindings):
                    seal_run(run, repo_root=ROOT, observed_at=NOW)
                    judgment = judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
                self.assertEqual(judgment["deterministic_result"]["score"], 0.0)
                self.assertEqual(judgment["deterministic_result"]["verdict"], "fail")

    def test_timeout_partial_and_transport_error_never_invent_completion(self):
        for index, mode in enumerate(("timeout", "partial_stream", "interrupted_write", "transport_error")):
            with self.subTest(mode=mode):
                run, attempt, bindings = self.full_run(mode, f"interrupt-{index}")
                self.assertFalse(attempt["complete"])
                self.assertEqual(verify_ledger(run).state, "interrupted")
                with self.trusted(bindings):
                    with self.assertRaises(CaptureError):
                        seal_run(run, repo_root=ROOT, observed_at=NOW)
                recover_run(run, action="abort", reason="operator abort", observed_at=NOW)
                with self.trusted(bindings):
                    manifest = seal_run(run, repo_root=ROOT, observed_at=NOW)
                    bundle = build_review_bundle(run, repo_root=ROOT, observed_at=NOW)
                self.assertEqual(manifest["capture_state"], "aborted")
                self.assertIsNone(bundle["deterministic_judgment"])

    def test_misleading_and_credential_metadata_are_rejected_not_published(self):
        for index, mode in enumerate(("misleading_provider_metadata", "credential_like_metadata")):
            run, attempt, _bindings = self.full_run(mode, f"metadata-{index}")
            self.assertFalse(attempt["complete"])
            self.assertEqual(attempt["transport_status"], "metadata_rejected")
            serialized = canonical_bytes(attempt).decode("utf-8")
            self.assertNotIn("Bearer", serialized)
            self.assertNotIn("official approved", serialized)

    def test_duplicate_execution_id_has_one_atomic_winner(self):
        campaign, lock, authorization, _adapter, bindings = self.context(execution_id="collision")
        barrier = threading.Barrier(2)
        outcomes = []

        def initialize_once():
            barrier.wait()
            try:
                with self.trusted(bindings):
                    initialize_run(
                        campaign=campaign,
                        lock=lock,
                        authorization=authorization,
                        request_bytes=REQUEST,
                        adapter=SyntheticAdapter("valid_json_object"),
                        repo_root=ROOT,
                        output_root=self.output_root,
                        observed_at=NOW,
                    )
                outcomes.append("ok")
            except CaptureError as exc:
                outcomes.append(exc.code)

        threads = [threading.Thread(target=initialize_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("ok"), 1)
        self.assertEqual(outcomes.count("DUPLICATE_EXECUTION_ID"), 1)

    def test_duplicate_attempt_and_retry_policy_are_fail_closed(self):
        run, _campaign, _lock, _authorization, adapter, bindings = self.initialize(
            max_attempts=2, reasons=["timeout"], mode="timeout"
        )
        with self.trusted(bindings):
            capture_attempt(run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW)
        recover_run(run, action="resume", reason="timeout", observed_at=NOW)
        with self.trusted(bindings), self.assertRaises(CaptureError) as duplicate:
            capture_attempt(
                run,
                request_bytes=REQUEST,
                adapter=SyntheticAdapter("valid_json_object"),
                repo_root=ROOT,
                observed_at=NOW,
                attempt_number=1,
            )
        self.assertEqual(duplicate.exception.code, "ATTEMPT_ALREADY_EXISTS_IDENTICAL")

    def test_response_and_manifest_tamper_block_sealing_or_verification(self):
        run, attempt, bindings = self.full_run()
        response_path = run.joinpath(*attempt["response_blob"]["path"].split("/"))
        response_path.write_bytes(response_path.read_bytes() + b"x")
        with self.trusted(bindings), self.assertRaises(CaptureError) as response_error:
            seal_run(run, repo_root=ROOT, observed_at=NOW)
        self.assertEqual(response_error.exception.code, "RAW_BLOB_DIGEST_MISMATCH")

        run2, _attempt2, bindings2 = self.full_run(execution_id="manifest-tamper")
        with self.trusted(bindings2):
            seal_run(run2, repo_root=ROOT, observed_at=NOW)
        manifest_path = run2 / "capture-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["warnings"] = ["inserted"]
        manifest_path.write_bytes(canonical_bytes(manifest))
        with self.trusted(bindings2), self.assertRaises(CaptureError) as manifest_error:
            verify_run(run2, repo_root=ROOT)
        self.assertEqual(manifest_error.exception.code, "CAPTURE_MANIFEST_DIGEST_MISMATCH")

    def test_partial_attempt_directory_is_not_capture_completion(self):
        run, _campaign, _lock, _authorization, _adapter, bindings = self.initialize()
        append_transition(run, "capturing", observed_at=NOW)
        (run / "attempts/000001").mkdir()
        with self.trusted(bindings), self.assertRaises(CaptureError) as caught:
            verify_run(run, repo_root=ROOT)
        self.assertEqual(caught.exception.code, "PARTIAL_CAPTURE_DETECTED")

    def test_explicit_abort_can_seal_attempt_directory_creation_crash(self):
        run, _campaign, _lock, _authorization, _adapter, bindings = self.initialize(
            execution_id="attempt-directory-crash"
        )
        append_transition(run, "capturing", observed_at=NOW, payload={"attempt_number": 1})
        (run / "attempts/000001").mkdir()
        recover_run(run, action="abort", reason="operator abort", observed_at=NOW)
        with self.trusted(bindings):
            manifest = seal_run(run, repo_root=ROOT, observed_at=NOW)
            verify_run(run, repo_root=ROOT)
        self.assertEqual(manifest["capture_state"], "aborted")
        self.assertEqual(manifest["attempts"][0]["transport_status"], "interrupted_uncommitted")
        self.assertIn(sha256_bytes(REQUEST), manifest["raw_evidence_hashes"])

    def test_review_bundle_tamper_cannot_claim_ratification(self):
        run, _attempt, bindings = self.full_run()
        with self.trusted(bindings):
            seal_run(run, repo_root=ROOT, observed_at=NOW)
            judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
            build_review_bundle(run, repo_root=ROOT, observed_at=NOW)
        path = run / "review-bundle.json"
        bundle = json.loads(path.read_text(encoding="utf-8"))
        bundle["ratification_status"] = "ratified"
        path.write_bytes(canonical_bytes(bundle))
        with self.trusted(bindings), self.assertRaises(CaptureError):
            verify_review_bundle(run, repo_root=ROOT)

    def test_invented_terminal_states_and_deleted_artifacts_fail_closed(self):
        run, _campaign, _lock, _authorization, _adapter, bindings = self.initialize(
            execution_id="invented-captured"
        )
        append_transition(run, "capturing", observed_at=NOW, payload={"attempt_number": 1})
        append_transition(run, "captured", observed_at=NOW, payload={"attempt_number": 1, "complete": True})
        with self.trusted(bindings), self.assertRaises(CaptureError) as empty_capture:
            verify_run(run, repo_root=ROOT)
        self.assertEqual(empty_capture.exception.code, "FALSE_CAPTURE_COMPLETION")

        judged, _attempt, judged_bindings = self.full_run(execution_id="missing-judgment")
        with self.trusted(judged_bindings):
            seal_run(judged, repo_root=ROOT, observed_at=NOW)
            judge_run(judged, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
        (judged / "judgment.json").unlink()
        with self.trusted(judged_bindings), self.assertRaises(CaptureError) as missing_judgment:
            verify_run(judged, repo_root=ROOT)
        self.assertEqual(missing_judgment.exception.code, "MISSING_JUDGMENT")

        bundled, _attempt, bundle_bindings = self.full_run(execution_id="missing-bundle")
        with self.trusted(bundle_bindings):
            seal_run(bundled, repo_root=ROOT, observed_at=NOW)
            judge_run(bundled, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
            build_review_bundle(bundled, repo_root=ROOT, observed_at=NOW)
        (bundled / "review-bundle.json").unlink()
        with self.trusted(bundle_bindings), self.assertRaises(CaptureError) as missing_bundle:
            verify_run(bundled, repo_root=ROOT)
        self.assertEqual(missing_bundle.exception.code, "MISSING_REVIEW_BUNDLE")

    def test_seal_judgment_and_bundle_crash_windows_reconcile_idempotently(self):
        later = "2026-07-12T20:05:00+02:00"
        run, _attempt, bindings = self.full_run(execution_id="reconcile")
        with self.trusted(bindings), mock.patch(
            "sfa_bench.campaigns.capture.run.append_transition",
            side_effect=RuntimeError("simulated crash after manifest publication"),
        ), self.assertRaises(RuntimeError):
            seal_run(run, repo_root=ROOT, observed_at=NOW)
        manifest_bytes = (run / "capture-manifest.json").read_bytes()
        with self.trusted(bindings):
            manifest = seal_run(run, repo_root=ROOT, observed_at=later)
        self.assertEqual((run / "capture-manifest.json").read_bytes(), manifest_bytes)
        self.assertEqual(manifest["capture_completed_at"], NOW)
        self.assertEqual(sum(event["to_state"] == "sealed" for event in verify_ledger(run).events), 1)

        with self.trusted(bindings), mock.patch(
            "sfa_bench.campaigns.capture.judgment.append_transition",
            side_effect=RuntimeError("simulated crash after judgment publication"),
        ), self.assertRaises(RuntimeError):
            judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
        judgment_bytes = (run / "judgment.json").read_bytes()
        with self.trusted(bindings):
            judgment = judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=later)
        self.assertEqual((run / "judgment.json").read_bytes(), judgment_bytes)
        self.assertEqual(judgment["judged_at"], NOW)
        self.assertEqual(sum(event["to_state"] == "judged" for event in verify_ledger(run).events), 1)

        with self.trusted(bindings), mock.patch(
            "sfa_bench.campaigns.capture.review.append_transition",
            side_effect=RuntimeError("simulated crash after bundle publication"),
        ), self.assertRaises(RuntimeError):
            build_review_bundle(run, repo_root=ROOT, observed_at=NOW)
        bundle_bytes = (run / "review-bundle.json").read_bytes()
        with self.trusted(bindings):
            bundle = build_review_bundle(run, repo_root=ROOT, observed_at=later)
            verify_review_bundle(run, repo_root=ROOT)
        self.assertEqual((run / "review-bundle.json").read_bytes(), bundle_bytes)
        self.assertEqual(bundle["ratification_status"], "unratified")
        self.assertEqual(sum(event["to_state"] == "review_required" for event in verify_ledger(run).events), 1)

        with self.trusted(bindings):
            self.assertEqual(seal_run(run, repo_root=ROOT, observed_at=later), manifest)
            self.assertEqual(
                judge_run(run, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=later),
                judgment,
            )
            self.assertEqual(build_review_bundle(run, repo_root=ROOT, observed_at=later), bundle)

    def test_context_failure_prevents_transport_and_scoring(self):
        run, _campaign, _lock, _authorization, adapter, _bindings = self.initialize(
            execution_id="binding-before-transport"
        )
        with mock.patch(
            "sfa_bench.campaigns.capture.run.verify_governed_context",
            side_effect=CaptureError("BINDING_DIGEST_MISMATCH", "changed bound implementation"),
        ), self.assertRaises(CaptureError):
            capture_attempt(run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW)
        self.assertEqual(adapter.calls, 0)

        judged, _attempt, bindings = self.full_run(execution_id="binding-before-score")
        with self.trusted(bindings):
            seal_run(judged, repo_root=ROOT, observed_at=NOW)
        with mock.patch(
            "sfa_bench.campaigns.capture.run.verify_governed_context",
            side_effect=CaptureError("BINDING_DIGEST_MISMATCH", "changed bound schema"),
        ), mock.patch(
            "sfa_bench.frontier_delta.candidate_adapter.score_response"
        ) as scorer, self.assertRaises(CaptureError):
            judge_run(judged, repo_root=ROOT, task_reference=TASK_REFERENCE, observed_at=NOW)
        scorer.assert_not_called()

    def test_recovery_partial_bytes_are_verified_and_sealed(self):
        run, _campaign, _lock, _authorization, adapter, bindings = self.initialize(
            execution_id="recovery-evidence",
            mode="timeout",
        )
        with self.trusted(bindings):
            capture_attempt(run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW)
        record = recover_run(
            run,
            action="abort",
            reason="operator abort",
            observed_at=NOW,
            partial_bytes=b"partial-response-evidence",
        )
        with self.trusted(bindings):
            manifest = seal_run(run, repo_root=ROOT, observed_at=NOW)
            verify_run(run, repo_root=ROOT)
        self.assertIn(record["partial_blob"]["sha256"], manifest["raw_evidence_hashes"])
        self.assertIn(sha256_bytes(REQUEST), manifest["raw_evidence_hashes"])

    def test_resumed_success_detects_reused_provider_identifier(self):
        class SequenceAdapter:
            adapter_id = SyntheticAdapter.adapter_id
            adapter_version = SyntheticAdapter.adapter_version
            implementation_path = SyntheticAdapter.implementation_path

            def __init__(self):
                self.calls = 0

            def transport(self, _request):
                self.calls += 1
                metadata = {
                    "content_type": "application/json",
                    "provider_request_id": "provider-declared-duplicate",
                }
                if self.calls == 1:
                    return TransportResult(
                        "interrupted",
                        b'{"claimed_state_keys":[',
                        metadata,
                        "SYNTHETIC_INTERRUPTION",
                    )
                return TransportResult(
                    "completed",
                    b'{"claimed_state_keys":["customer_id"],"used_off_limits_keys":[]}',
                    metadata,
                )

        campaign, lock, authorization, _adapter, bindings = self.context(
            execution_id="resumed-duplicate",
            max_attempts=2,
            reasons=["timeout"],
        )
        adapter = SequenceAdapter()
        with self.trusted(bindings):
            run = initialize_run(
                campaign=campaign, lock=lock, authorization=authorization, request_bytes=REQUEST,
                adapter=adapter, repo_root=ROOT, output_root=self.output_root, observed_at=NOW,
            )
            first = capture_attempt(
                run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW,
            )
        self.assertFalse(first["complete"])
        recover_run(run, action="resume", reason="timeout", observed_at=NOW)
        with self.trusted(bindings):
            second = capture_attempt(
                run, request_bytes=REQUEST, adapter=adapter, repo_root=ROOT, observed_at=NOW,
            )
            manifest = seal_run(run, repo_root=ROOT, observed_at=NOW)
        self.assertTrue(second["complete"])
        self.assertEqual(adapter.calls, 2)
        self.assertIn("PROVIDER_REQUEST_ID_REUSED", second["warnings"])
        self.assertEqual(len(manifest["attempts"]), 2)

    def test_execution_id_uniqueness_is_capture_store_local(self):
        campaign, lock, authorization, adapter, bindings = self.context(execution_id="store-local")
        second_root = Path(self.temp.name) / "other-runs"
        with self.trusted(bindings):
            first = initialize_run(
                campaign=campaign, lock=lock, authorization=authorization, request_bytes=REQUEST,
                adapter=adapter, repo_root=ROOT, output_root=self.output_root, observed_at=NOW,
            )
            second = initialize_run(
                campaign=campaign, lock=lock, authorization=authorization, request_bytes=REQUEST,
                adapter=SyntheticAdapter("valid_json_object"), repo_root=ROOT,
                output_root=second_root, observed_at=NOW,
            )
        self.assertEqual(first.name, second.name)
        self.assertNotEqual(first.parent.parent, second.parent.parent)


class SyntheticLaboratoryTests(unittest.TestCase):
    def test_all_declared_modes_are_offline_and_deterministic(self):
        request = LockedCaptureRequest(
            campaign_id="campaign-1",
            execution_id="exec-1",
            attempt_number=1,
            benchmark_lock_digest="a" * 64,
            request_bytes=REQUEST,
            prompt_reference=PROMPT_REFERENCE,
            case_reference=TASK_REFERENCE,
        )
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
            for mode in sorted(SyntheticAdapter.MODES):
                adapter = SyntheticAdapter(mode)
                first = adapter.transport(request)
                second = SyntheticAdapter(mode).transport(request)
                self.assertEqual(first, second, mode)


if __name__ == "__main__":
    unittest.main()
