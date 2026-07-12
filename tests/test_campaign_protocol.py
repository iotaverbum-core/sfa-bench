"""Adversarial tests for the V2 alpha.1 campaign foundation."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import campaign_cli
from sfa_bench.campaigns import locking
from sfa_bench.frontier_delta import candidate_adapter
from sfa_bench.campaigns.locking import (
    LockingError,
    RepositoryContext,
    _build_benchmark_lock_content,
    _verify_benchmark_lock_content,
    benchmark_lock_digest,
    build_benchmark_lock,
    reference_digest,
    verify_benchmark_lock,
)
from sfa_bench.campaigns.protocol import (
    candidate_judgment_projection,
    validate_campaign,
    validate_campaign_collection,
    validate_candidate_manifest,
)


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "campaigns" / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _campaign() -> dict:
    return _load("gpt56-draft-preregistration.json")


def _manifest() -> dict:
    return _load("gpt56-draft-candidate-manifest.json")


def _codes(issues: list[dict[str, str]]) -> set[str]:
    return {entry["code"] for entry in issues}


def _context(campaign: dict | None = None) -> RepositoryContext:
    declaration = campaign or _campaign()
    return RepositoryContext(
        repository_commit=declaration["benchmark_commit_sha"],
        verifier_commit=declaration["verifier_commit_sha"],
        release_identifier=declaration["release_identifier"],
    )


def _build(campaign: dict, repo: Path = ROOT, **kwargs) -> dict:
    return _build_benchmark_lock_content(
        campaign, repo, context=_context(campaign), **kwargs
    )


def _verify(campaign: dict, lock: dict, repo: Path = ROOT) -> list[dict[str, str]]:
    return _verify_benchmark_lock_content(
        campaign, lock, repo, context=_context(campaign)
    )


def _copy_lock_inputs(destination: Path) -> None:
    for relative in ("sfa", "sfa_bench", "cases"):
        shutil.copytree(ROOT / relative, destination / relative)
    (destination / "campaigns").mkdir()
    shutil.copytree(ROOT / "campaigns" / "schemas", destination / "campaigns" / "schemas")
    shutil.copytree(
        ROOT / "campaigns" / "examples" / "prompts",
        destination / "campaigns" / "examples" / "prompts",
    )
    shutil.copy2(ROOT / "campaign_cli.py", destination / "campaign_cli.py")
    shutil.copy2(ROOT / "families.json", destination / "families.json")


def _official_campaign() -> dict:
    campaign = _campaign()
    campaign["status"] = "preregistered"
    campaign["run_classification"] = "official"
    campaign["execution_plan"]["run_classification"] = "official"
    campaign["candidate_snapshot_or_alias_status"] = "fixed_snapshot"
    campaign["provider_model_identifier"] = "provider-snapshot-2026-07-10"
    campaign["system_prompt"]["sha256"] = reference_digest(
        ROOT, campaign["system_prompt"]["reference"]
    )
    campaign["user_prompt_or_case_set"]["sha256"] = reference_digest(
        ROOT, campaign["user_prompt_or_case_set"]["reference"]
    )
    campaign["benchmark_lock"] = {
        "path": "out/campaign_locks/official.benchmark-lock.json",
        "lock_digest": "6" * 64,
        "repository_commit": campaign["benchmark_commit_sha"],
        "verifier_commit": campaign["verifier_commit_sha"],
        "status": "frozen",
    }
    return campaign


class ExampleValidationTests(unittest.TestCase):
    def test_draft_preregistration_validates(self):
        self.assertEqual(validate_campaign(_campaign()), [])

    def test_draft_candidate_manifest_validates(self):
        self.assertEqual(validate_candidate_manifest(_manifest()), [])

    def test_validation_is_deterministic(self):
        invalid = _campaign()
        del invalid["invalid_output_policy"]
        invalid["run_count"] = "three"
        self.assertEqual(validate_campaign(invalid), validate_campaign(invalid))

    def test_bound_example_system_prompt_is_blinded(self):
        campaign = _campaign()
        prompt = ROOT.joinpath(
            *campaign["system_prompt"]["reference"].split("/")
        ).read_text(encoding="utf-8")
        candidate_adapter.assert_no_forbidden_tokens(prompt)


class CampaignValidationTests(unittest.TestCase):
    def test_missing_invalid_output_policy_is_rejected(self):
        campaign = _campaign()
        del campaign["invalid_output_policy"]
        issues = validate_campaign(campaign)
        self.assertIn("MISSING_REQUIRED_FIELD", _codes(issues))
        self.assertTrue(
            any(entry["path"] == "$.invalid_output_policy" for entry in issues),
            issues,
        )

    def test_invalid_output_policy_cannot_award_credit_or_dispatch(self):
        for field, value in (
            ("invalid_output_score", 0.25),
            ("canonicaliser_dispatch", "all_outputs"),
            ("preserve_raw_response", False),
        ):
            with self.subTest(field=field):
                campaign = _campaign()
                campaign["invalid_output_policy"][field] = value
                self.assertIn(
                    "INVALID_OUTPUT_POLICY_WEAKENED",
                    _codes(validate_campaign(campaign)),
                )

    def test_old_schema_requires_migration(self):
        campaign = _campaign()
        campaign["schema_version"] = "sfa_bench.campaign.v0"
        issues = validate_campaign(campaign)
        self.assertIn("SCHEMA_MIGRATION_REQUIRED", _codes(issues))
        self.assertTrue(any("migrate" in entry["message"] for entry in issues))

    def test_unknown_future_schema_fails_safely(self):
        campaign = _campaign()
        campaign["schema_version"] = "sfa_bench.campaign.v99"
        self.assertIn("UNSUPPORTED_SCHEMA_VERSION", _codes(validate_campaign(campaign)))

    def test_recursive_secret_detection(self):
        campaign = _campaign()
        campaign["reasoning_configuration"]["nested"] = {
            "api_key": "sk-example-secret-material"
        }
        codes = _codes(validate_campaign(campaign))
        self.assertIn("SECRET_FIELD_FORBIDDEN", codes)

    def test_likely_secret_value_detection(self):
        campaign = _campaign()
        campaign["reasoning_configuration"]["opaque"] = (
            "Bearer abcdefghijklmnopqrstuvwxyz"
        )
        self.assertIn("LIKELY_SECRET_DETECTED", _codes(validate_campaign(campaign)))

    def test_mutable_alias_requires_declaration(self):
        campaign = _campaign()
        campaign["candidate_snapshot_or_alias_status"] = "mutable_alias"
        campaign["mutable_alias_use_declared"] = False
        self.assertIn("MUTABLE_ALIAS_UNDECLARED", _codes(validate_campaign(campaign)))

    def test_official_campaign_requires_frozen_lock(self):
        campaign = _official_campaign()
        del campaign["benchmark_lock"]
        self.assertIn(
            "OFFICIAL_CAMPAIGN_REQUIRES_LOCK", _codes(validate_campaign(campaign))
        )

    def test_official_lock_can_be_built_before_adding_its_reference(self):
        campaign = _official_campaign()
        del campaign["benchmark_lock"]
        self.assertIn(
            "OFFICIAL_CAMPAIGN_REQUIRES_LOCK", _codes(validate_campaign(campaign))
        )
        lock = _build(campaign)
        campaign["benchmark_lock"] = {
            "path": "out/campaign_locks/official.benchmark-lock.json",
            "lock_digest": lock["lock_digest"],
            "repository_commit": lock["repository_commit"],
            "verifier_commit": lock["verifier_commit"],
            "status": "frozen",
        }
        self.assertEqual(validate_campaign(campaign), [])
        self.assertEqual(_verify(campaign, lock), [])

    def test_official_campaign_references_must_match_lock(self):
        campaign = _official_campaign()
        campaign["benchmark_lock"]["verifier_commit"] = "0" * 40
        self.assertIn(
            "OFFICIAL_LOCK_REFERENCE_MISMATCH", _codes(validate_campaign(campaign))
        )

    def test_automatic_ratification_and_promotion_are_rejected(self):
        campaign = _campaign()
        campaign["ratification_policy"]["automatic_ratification"] = True
        campaign["ratification_policy"]["automatic_promotion"] = True
        codes = _codes(validate_campaign(campaign))
        self.assertIn("AUTOMATIC_RATIFICATION_FORBIDDEN", codes)
        self.assertIn("AUTOMATIC_PROMOTION_FORBIDDEN", codes)

    def test_nested_governance_claim_keys_are_normalized_and_rejected(self):
        for surface, key in (
            ("reasoning_configuration", "automatic_promotion"),
            ("sampling_configuration", "automaticPromotion"),
            ("reasoning_configuration", "ratification-status"),
            ("reasoning_configuration", "auto_ratify"),
            ("sampling_configuration", "auto_ratification"),
            ("reasoning_configuration", "auto_promotion"),
            ("sampling_configuration", "self_ratified"),
            ("reasoning_configuration", "ratify"),
            ("sampling_configuration", "promote"),
            ("reasoning_configuration", "ratification_result"),
            ("sampling_configuration", "promotion_result"),
        ):
            with self.subTest(surface=surface, key=key):
                campaign = _campaign()
                campaign[surface][key] = True
                self.assertIn(
                    "CAMPAIGN_GOVERNANCE_CLAIM_FORBIDDEN",
                    _codes(validate_campaign(campaign)),
                )

    def test_untrusted_campaign_text_cannot_assert_governance(self):
        for key, value in (
            ("status", "ratified"),
            ("decision", "promote"),
            ("outcome", "human ratification complete"),
            ("result", "promotion approved"),
            ("state", "RATIFIED"),
            ("message", "candidate ratified and promoted"),
            ("provider_note", "promotion complete"),
        ):
            with self.subTest(key=key):
                campaign = _campaign()
                campaign["reasoning_configuration"][key] = value
                self.assertIn(
                    "CAMPAIGN_GOVERNANCE_CLAIM_FORBIDDEN",
                    _codes(validate_campaign(campaign)),
                )

    def test_nonfinite_campaign_numbers_are_rejected(self):
        campaign = _campaign()
        campaign["sampling_configuration"]["temperature"] = float("nan")
        self.assertIn(
            "NONFINITE_NUMBER_FORBIDDEN",
            _codes(validate_campaign(campaign)),
        )

    def test_retry_metadata_cannot_influence_verdict(self):
        campaign = _campaign()
        campaign["retry_policy"]["retry_metadata_may_affect_verdict"] = True
        self.assertIn(
            "RETRY_METADATA_VERDICT_INFLUENCE", _codes(validate_campaign(campaign))
        )

    def test_path_traversal_and_output_escape_are_rejected(self):
        campaign = _campaign()
        campaign["benchmark_inputs"]["case_paths"] = ["../private-cases"]
        campaign["system_prompt"]["reference"] = "../../private-prompt.txt"
        campaign["execution_plan"]["output_path"] = "../campaign-output"
        codes = _codes(validate_campaign(campaign))
        self.assertIn("PATH_TRAVERSAL", codes)
        self.assertIn("OUTPUT_PATH_NOT_APPROVED", codes)

    def test_noncanonical_and_nonportable_paths_are_rejected(self):
        for reference in (
            "foo//bar",
            "foo/./bar",
            "./foo",
            "foo/.",
            "foo/",
            "foo:bar",
            "CON",
            "out/campaign_locks/base:lock.json",
        ):
            with self.subTest(reference=reference):
                campaign = _campaign()
                campaign["system_prompt"]["reference"] = reference
                self.assertTrue(
                    {"PATH_TRAVERSAL", "INVALID_PATH"}
                    & _codes(validate_campaign(campaign))
                )

    def test_duplicate_policy_surfaces_must_agree(self):
        campaign = _campaign()
        campaign["execution_plan"]["retry_rules"]["max_attempts"] = 2
        campaign["execution_plan"]["retry_rules"]["retry_conditions"] = [
            "provider transport failure"
        ]
        self.assertIn(
            "POLICY_SURFACE_MISMATCH", _codes(validate_campaign(campaign))
        )

    def test_deterministic_shuffle_requires_a_seed(self):
        campaign = _campaign()
        campaign["execution_plan"]["ordering_policy"] = (
            "deterministic_shuffle_with_declared_seed"
        )
        self.assertIn("ORDERING_SEED_REQUIRED", _codes(validate_campaign(campaign)))
        campaign["execution_plan"]["ordering_seed"] = 17
        self.assertNotIn(
            "ORDERING_SEED_REQUIRED", _codes(validate_campaign(campaign))
        )

    def test_duplicate_campaign_ids_are_deterministic(self):
        campaigns = [_campaign(), _campaign()]
        first = validate_campaign_collection(campaigns)
        second = validate_campaign_collection(campaigns)
        self.assertEqual(first, second)
        self.assertIn("DUPLICATE_CAMPAIGN_ID", _codes(first))

    def test_draft_cannot_claim_official_or_completed(self):
        campaign = _campaign()
        campaign["run_classification"] = "official"
        campaign["execution_plan"]["run_classification"] = "official"
        campaign["score"] = 1.0
        codes = _codes(validate_campaign(campaign))
        self.assertIn("DRAFT_OFFICIAL_CONFLICT", codes)
        self.assertIn("DRAFT_COMPLETION_CLAIM", codes)

    def test_draft_completion_claims_fail_recursively(self):
        for key, value in (
            ("completed", True),
            ("execution_result", {"score": 1}),
            ("official_result", "pass"),
            ("provider_ranking", 1),
            ("score", 1),
            ("passed", True),
            ("run_status", "completed"),
            ("classification", "official"),
            ("message", "campaign completed successfully"),
        ):
            with self.subTest(key=key):
                campaign = _campaign()
                campaign["reasoning_configuration"][key] = value
                self.assertIn(
                    "DRAFT_COMPLETION_CLAIM",
                    _codes(validate_campaign(campaign)),
                )

    def test_campaign_unicode_scalars_fail_closed_for_values_and_keys(self):
        campaign = _campaign()
        campaign["campaign_title"] = chr(0xD800)
        campaign["reasoning_configuration"][chr(0xDC00)] = 1
        issues = validate_campaign(campaign)
        self.assertGreaterEqual(
            [entry["code"] for entry in issues].count(
                "INVALID_UNICODE_SCALAR"
            ),
            2,
        )

    def test_field_types_fail_closed(self):
        campaign = _campaign()
        campaign["run_count"] = True
        campaign["tool_permissions"] = "none"
        codes = _codes(validate_campaign(campaign))
        self.assertIn("INVALID_FIELD_VALUE", codes)
        self.assertIn("INVALID_FIELD_TYPE", codes)


class CandidateManifestBoundaryTests(unittest.TestCase):
    def test_malformed_manifest_fails_closed(self):
        self.assertIn("MALFORMED_DOCUMENT", _codes(validate_candidate_manifest([])))
        manifest = _manifest()
        del manifest["campaign_reference"]
        self.assertIn("MISSING_REQUIRED_FIELD", _codes(validate_candidate_manifest(manifest)))

    def test_candidate_cannot_declare_itself_ratified(self):
        manifest = _manifest()
        manifest["observed_provider_model_metadata"] = {"ratified": True}
        self.assertIn(
            "CANDIDATE_SELF_RATIFICATION_FORBIDDEN",
            _codes(validate_candidate_manifest(manifest)),
        )

    def test_candidate_governance_key_variants_are_rejected(self):
        for key in (
            "ratification-status",
            "ratificationStatus",
            "promotionStatus",
            "is_ratified",
            "auto_ratify",
            "auto_ratification",
            "auto_promotion",
            "self_ratified",
            "ratify",
            "promote",
            "ratification",
            "promotion",
            "ratification_result",
            "promotion_result",
        ):
            with self.subTest(key=key):
                manifest = _manifest()
                manifest["observed_provider_model_metadata"] = {key: True}
                self.assertIn(
                    "CANDIDATE_SELF_RATIFICATION_FORBIDDEN",
                    _codes(validate_candidate_manifest(manifest)),
                )

    def test_untrusted_candidate_text_cannot_assert_governance(self):
        for key, value in (
            ("status", "ratified"),
            ("decision", "promote"),
            ("outcome", "human ratification complete"),
            ("result", "promotion approved"),
            ("state", "RATIFIED"),
            ("note", "candidate ratified and promoted"),
            ("description", "promotion approved"),
        ):
            with self.subTest(key=key):
                manifest = _manifest()
                manifest["observed_provider_model_metadata"] = {key: value}
                self.assertIn(
                    "CANDIDATE_SELF_RATIFICATION_FORBIDDEN",
                    _codes(validate_candidate_manifest(manifest)),
                )

    def test_manifest_unicode_scalars_fail_closed_for_values_and_keys(self):
        manifest = _manifest()
        manifest["candidate_id"] = chr(0xD800)
        manifest["observed_provider_model_metadata"] = {chr(0xDC00): 1}
        issues = validate_candidate_manifest(manifest)
        self.assertGreaterEqual(
            [entry["code"] for entry in issues].count(
                "INVALID_UNICODE_SCALAR"
            ),
            2,
        )

    def test_nonfinite_manifest_numbers_are_rejected(self):
        manifest = _manifest()
        manifest["configuration"]["temperature"] = float("inf")
        self.assertIn(
            "NONFINITE_NUMBER_FORBIDDEN",
            _codes(validate_candidate_manifest(manifest)),
        )

    def test_candidate_manifest_rejects_nested_secret(self):
        manifest = _manifest()
        manifest["environment"]["authorization_token"] = "secret"
        self.assertIn(
            "SECRET_FIELD_FORBIDDEN", _codes(validate_candidate_manifest(manifest))
        )

    def test_provider_metadata_is_not_a_judgment_input(self):
        first = _manifest()
        second = _manifest()
        first["observed_provider_model_metadata"] = {"model": "alias-a"}
        second["observed_provider_model_metadata"] = {
            "model": "alias-b",
            "provider_status": "preferred",
        }
        self.assertEqual(
            candidate_judgment_projection(first), candidate_judgment_projection(second)
        )
        self.assertEqual(candidate_judgment_projection(first), {})

    def test_manifest_metadata_influence_flags_must_be_false(self):
        manifest = _manifest()
        manifest["judgment_boundary"]["provider_metadata_may_affect_verdict"] = True
        self.assertIn(
            "METADATA_VERDICT_INFLUENCE_FORBIDDEN",
            _codes(validate_candidate_manifest(manifest)),
        )


class BenchmarkLockTests(unittest.TestCase):
    def test_lock_is_deterministic_and_verifies(self):
        campaign = _campaign()
        first = _build(campaign)
        second = _build(campaign)
        self.assertEqual(first, second)
        self.assertEqual(_verify(campaign, first), [])

    def test_envelope_is_outside_deterministic_digest(self):
        campaign = _campaign()
        first = _build(
            campaign, envelope={"created_at": "2026-07-11T00:00:00Z"}
        )
        second = _build(
            campaign, envelope={"created_at": "2099-01-01T00:00:00Z"}
        )
        self.assertEqual(first["lock_digest"], second["lock_digest"])
        changed = copy.deepcopy(first)
        changed["envelope"] = {"created_at": "2077-01-01T00:00:00Z"}
        self.assertEqual(benchmark_lock_digest(changed), first["lock_digest"])
        self.assertEqual(_verify(campaign, changed), [])

    def test_envelope_cannot_carry_unhashed_outcome_claims(self):
        campaign = _campaign()
        cases = [
            ({"score": "1.0"}, "ENVELOPE_FIELD_FORBIDDEN"),
            ({"created_by": "reviewer"}, "ENVELOPE_FIELD_FORBIDDEN"),
            ({"created_at": "campaign passed"}, "ENVELOPE_TIMESTAMP_INVALID"),
        ]
        cases.extend(
            (
                {"environment_note": claim},
                "ENVELOPE_FIELD_FORBIDDEN",
            )
            for claim in (
                "campaign completed successfully",
                "approved by regulator",
                "certified compliant with EU law",
                "legal conformity established",
                "official provider ranking: first",
                "execution occurred",
                "api key sk-12345678901234567890",
            )
        )
        for envelope, expected_code in cases:
            with self.subTest(envelope=envelope):
                with self.assertRaises(LockingError) as caught:
                    _build(campaign, envelope=envelope)
                self.assertIn(expected_code, _codes(caught.exception.issues))

    def test_repository_and_release_context_must_match_declaration(self):
        campaign = _campaign()
        wrong_commit = RepositoryContext(
            repository_commit="0" * 40,
            verifier_commit=campaign["verifier_commit_sha"],
            release_identifier=campaign["release_identifier"],
        )
        with self.assertRaises(LockingError) as caught:
            _build_benchmark_lock_content(
                campaign, ROOT, context=wrong_commit
            )
        self.assertIn("REPOSITORY_COMMIT_MISMATCH", _codes(caught.exception.issues))

        wrong_release = RepositoryContext(
            repository_commit=campaign["benchmark_commit_sha"],
            verifier_commit=campaign["verifier_commit_sha"],
            release_identifier="v1.1.0",
        )
        with self.assertRaises(LockingError) as caught:
            _build_benchmark_lock_content(
                campaign, ROOT, context=wrong_release
            )
        self.assertIn("RELEASE_IDENTIFIER_MISMATCH", _codes(caught.exception.issues))

        wrong_verifier = RepositoryContext(
            repository_commit=campaign["benchmark_commit_sha"],
            verifier_commit="0" * 40,
            release_identifier=campaign["release_identifier"],
        )
        with self.assertRaises(LockingError) as caught:
            _build_benchmark_lock_content(
                campaign, ROOT, context=wrong_verifier
            )
        self.assertIn("VERIFIER_COMMIT_MISMATCH", _codes(caught.exception.issues))

    def test_nonexistent_verifier_commit_is_rejected(self):
        campaign = _campaign()
        campaign["verifier_commit_sha"] = "0" * 40
        with self.assertRaises(LockingError) as caught:
            build_benchmark_lock(campaign, ROOT)
        self.assertIn("VERIFIER_COMMIT_UNRESOLVED", _codes(caught.exception.issues))

    def test_public_api_does_not_accept_injected_provenance_context(self):
        campaign = _campaign()
        false_context = RepositoryContext(
            repository_commit="0" * 40,
            verifier_commit="1" * 40,
            release_identifier=campaign["release_identifier"],
        )
        with self.assertRaises(TypeError):
            build_benchmark_lock(campaign, ROOT, context=false_context)
        with self.assertRaises(TypeError):
            verify_benchmark_lock(campaign, {}, ROOT, context=false_context)

    def test_nonexistent_benchmark_commit_is_rejected(self):
        campaign = _campaign()
        campaign["benchmark_commit_sha"] = "0" * 40
        with self.assertRaises(LockingError) as caught:
            build_benchmark_lock(campaign, ROOT)
        self.assertIn(
            "REPOSITORY_COMMIT_UNRESOLVED", _codes(caught.exception.issues)
        )

    def test_threshold_or_policy_change_is_detected(self):
        campaign = _campaign()
        lock = _build(campaign)
        changed = copy.deepcopy(campaign)
        changed["success_criteria"].append("new post-observation threshold")
        codes = _codes(_verify(changed, lock))
        self.assertIn("CAMPAIGN_CONTENT_MISMATCH", codes)
        self.assertIn("LOCK_CURRENT_STATE_MISMATCH", codes)

    def test_declared_command_change_is_detected(self):
        campaign = _campaign()
        lock = _build(campaign)
        changed = copy.deepcopy(campaign)
        changed["benchmark_inputs"]["declared_commands"].append("py -3 invented.py")
        codes = _codes(_verify(changed, lock))
        self.assertIn("DECLARED_COMMANDS_MISMATCH", codes)

    def test_declared_aggregate_digests_are_enforced(self):
        fields = (
            ("frozen_case_set_digest", "DECLARED_CASE_SET_DIGEST_MISMATCH"),
            ("frozen_rule_digest", "DECLARED_RULE_DIGEST_MISMATCH"),
            ("frozen_taxonomy_digest", "DECLARED_TAXONOMY_DIGEST_MISMATCH"),
        )
        for field, expected_code in fields:
            with self.subTest(field=field):
                campaign = _campaign()
                campaign[field] = "0" * 64
                with self.assertRaises(LockingError) as caught:
                    _build(campaign)
                self.assertIn(expected_code, _codes(caught.exception.issues))

    def test_declared_prompt_digests_are_enforced(self):
        for field, expected_code in (
            ("system_prompt", "DECLARED_SYSTEM_PROMPT_DIGEST_MISMATCH"),
            (
                "user_prompt_or_case_set",
                "DECLARED_USER_PROMPT_DIGEST_MISMATCH",
            ),
        ):
            with self.subTest(field=field):
                campaign = _campaign()
                campaign[field]["sha256"] = "0" * 64
                with self.assertRaises(LockingError) as caught:
                    _build(campaign)
                self.assertIn(expected_code, _codes(caught.exception.issues))

    def test_nonfinite_lock_content_cannot_be_canonicalized(self):
        with self.assertRaises(ValueError):
            benchmark_lock_digest({"temperature": float("nan")})

    def test_runtime_cache_files_do_not_change_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            _copy_lock_inputs(repo)
            campaign = _campaign()
            before = _build(campaign, repo)
            cache = repo / "sfa_bench" / "frontier_delta" / "scorers" / "__pycache__"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "checks.cpython-311.pyc").write_bytes(b"runtime cache")
            (repo / "sfa_bench" / "frontier_delta" / "tasks" / ".pytest_cache").mkdir()
            after = _build(campaign, repo)
            self.assertEqual(before, after)

    def test_each_protected_input_class_detects_mutation(self):
        targets = (
            ("sfa_bench/frontier_delta/tasks/planning_drift_001.json", "CASE_BINDING_MISMATCH"),
            ("cases/case_001_grounded_pass/evidence.json", "EVIDENCE_BINDING_MISMATCH"),
            ("sfa/verifier.py", "VERIFIER_BINDING_MISMATCH"),
            ("families.json", "TAXONOMY_BINDING_MISMATCH"),
            ("sfa_bench/frontier_delta/scorers/checks.py", "RULE_BINDING_MISMATCH"),
            ("sfa_bench/frontier_delta/candidate_adapter.py", "NORMALIZER_BINDING_MISMATCH"),
            ("sfa_bench/frontier_delta/candidate_adapter.py", "ADAPTER_BINDING_MISMATCH"),
            ("campaigns/schemas/candidate-manifest.schema.json", "SCHEMA_BINDING_MISMATCH"),
            ("sfa_bench/campaigns/protocol.py", "SCHEMA_BINDING_MISMATCH"),
            (
                "campaigns/examples/prompts/gpt56-study-system-prompt.txt",
                "SYSTEM_PROMPT_BINDING_MISMATCH",
            ),
            (
                "sfa_bench/frontier_delta/tasks/planning_drift_001.json",
                "USER_PROMPT_BINDING_MISMATCH",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            _copy_lock_inputs(repo)
            campaign = _campaign()
            lock = _build(campaign, repo)
            for relative, expected_code in targets:
                with self.subTest(relative=relative, code=expected_code):
                    target = repo.joinpath(*relative.split("/"))
                    original = target.read_bytes()
                    try:
                        target.write_bytes(original + b"\nmutation")
                        self.assertIn(
                            expected_code,
                            _codes(_verify(campaign, lock, repo)),
                        )
                    finally:
                        target.write_bytes(original)

    def test_post_lock_prompt_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            _copy_lock_inputs(repo)
            campaign = _campaign()
            lock = _build(campaign, repo)
            prompt = (
                repo
                / "campaigns"
                / "examples"
                / "prompts"
                / "gpt56-study-system-prompt.txt"
            )
            prompt.write_bytes(prompt.read_bytes() + b"\nmutation")
            codes = _codes(_verify(campaign, lock, repo))
        self.assertIn("SYSTEM_PROMPT_BINDING_MISMATCH", codes)
        self.assertIn("DECLARED_SYSTEM_PROMPT_DIGEST_MISMATCH", codes)


class CampaignCliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, dict]:
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(
                locking, "observe_repository_context", return_value=_context()
            ),
            mock.patch.object(
                locking, "_binding_commit_issues", return_value=[]
            ),
        ):
            returncode = campaign_cli.main(argv)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        return returncode, json.loads(lines[0])

    def test_validate_commands_emit_one_json_object(self):
        returncode, result = self._run(
            [
                "validate",
                "--campaign",
                "campaigns/examples/gpt56-draft-preregistration.json",
            ]
        )
        self.assertEqual(returncode, 0)
        self.assertTrue(result["ok"])

    def test_official_validate_loads_and_verifies_referenced_lock(self):
        campaign = _official_campaign()
        del campaign["benchmark_lock"]
        lock = _build(campaign)
        campaign["benchmark_lock"] = {
            "path": "out/campaign_locks/official.benchmark-lock.json",
            "lock_digest": lock["lock_digest"],
            "repository_commit": lock["repository_commit"],
            "verifier_commit": lock["verifier_commit"],
            "status": "frozen",
        }
        with mock.patch.object(
            campaign_cli, "_load_json", side_effect=[campaign, lock]
        ):
            returncode, result = self._run(
                ["validate", "--campaign", "official.json"]
            )
        self.assertEqual(returncode, 0, result)
        self.assertTrue(result["ok"])

    def test_official_validate_rejects_missing_lock_artifact(self):
        campaign = _official_campaign()
        missing = ROOT / "out" / "campaign_locks" / "missing.json"
        error = campaign_cli.JsonInputError(
            "INPUT_NOT_FOUND", missing, "input file does not exist"
        )
        with mock.patch.object(
            campaign_cli, "_load_json", side_effect=[campaign, error]
        ):
            returncode, result = self._run(
                ["validate", "--campaign", "official.json"]
            )
        self.assertEqual(returncode, 2)
        self.assertIn("INPUT_NOT_FOUND", _codes(result["issues"]))
        returncode, result = self._run(
            [
                "validate-candidate",
                "--manifest",
                "campaigns/examples/gpt56-draft-candidate-manifest.json",
            ]
        )
        self.assertEqual(returncode, 0)
        self.assertTrue(result["ok"])

    def test_lock_verify_atomic_write_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            approved = Path(temporary) / "campaign_locks"
            output = approved / "draft-lock.json"
            with mock.patch.object(campaign_cli, "LOCK_OUTPUT_ROOT", approved):
                returncode, created = self._run(
                    [
                        "lock",
                        "--campaign",
                        "campaigns/examples/gpt56-draft-preregistration.json",
                        "--output",
                        str(output),
                    ]
                )
                self.assertEqual(returncode, 0, created)
                self.assertTrue(output.is_file())
                self.assertEqual(list(approved.glob("*.tmp")), [])

                returncode, verified = self._run(
                    [
                        "verify-lock",
                        "--campaign",
                        "campaigns/examples/gpt56-draft-preregistration.json",
                        "--lock",
                        str(output),
                    ]
                )
                self.assertEqual(returncode, 0, verified)
                self.assertTrue(verified["ok"])

                returncode, refused = self._run(
                    [
                        "lock",
                        "--campaign",
                        "campaigns/examples/gpt56-draft-preregistration.json",
                        "--output",
                        str(output),
                    ]
                )
                self.assertEqual(returncode, 2)
                self.assertIn("OUTPUT_EXISTS", _codes(refused["issues"]))

    def test_cli_can_create_initial_official_lock(self):
        campaign = _official_campaign()
        del campaign["benchmark_lock"]
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            campaign_path = temporary_root / "official.json"
            campaign_path.write_text(
                json.dumps(campaign, sort_keys=True) + "\n", encoding="utf-8"
            )
            approved = temporary_root / "campaign_locks"
            output = approved / "official-lock.json"
            with mock.patch.object(campaign_cli, "LOCK_OUTPUT_ROOT", approved):
                returncode, result = self._run(
                    [
                        "lock",
                        "--campaign",
                        str(campaign_path),
                        "--output",
                        str(output),
                    ]
                )
        self.assertEqual(returncode, 0, result)
        self.assertTrue(result["ok"])
        self.assertRegex(result["lock_digest"], r"^[0-9a-f]{64}$")

    def test_output_cannot_escape_approved_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            approved = Path(temporary) / "approved"
            escaped = Path(temporary) / "escaped.json"
            with mock.patch.object(campaign_cli, "LOCK_OUTPUT_ROOT", approved):
                returncode, result = self._run(
                    [
                        "lock",
                        "--campaign",
                        "campaigns/examples/gpt56-draft-preregistration.json",
                        "--output",
                        str(escaped),
                    ]
                )
            self.assertEqual(returncode, 2)
            self.assertFalse(escaped.exists())
            self.assertIn("OUTPUT_PATH_NOT_APPROVED", _codes(result["issues"]))

    def test_output_rejects_nonportable_windows_forms(self):
        for filename in ("base:lock.json", "CON.json"):
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as temporary:
                    approved = Path(temporary) / "approved"
                    output = approved / filename
                    with mock.patch.object(
                        campaign_cli, "LOCK_OUTPUT_ROOT", approved
                    ):
                        returncode, result = self._run(
                            [
                                "lock",
                                "--campaign",
                                "campaigns/examples/"
                                "gpt56-draft-preregistration.json",
                                "--output",
                                str(output),
                            ]
                        )
                self.assertEqual(returncode, 2)
                self.assertIn("OUTPUT_PATH_INVALID", _codes(result["issues"]))

    def test_invalid_document_exits_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.json"
            invalid.write_text("[]\n", encoding="utf-8")
            returncode, result = self._run(
                ["validate", "--campaign", str(invalid)]
            )
        self.assertEqual(returncode, 2)
        self.assertFalse(result["ok"])
        self.assertIn("MALFORMED_DOCUMENT", _codes(result["issues"]))

    def test_nonstandard_json_constants_exit_two(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                with tempfile.TemporaryDirectory() as temporary:
                    invalid = Path(temporary) / "invalid.json"
                    invalid.write_text(
                        '{"schema_version":' + constant + '}\n',
                        encoding="utf-8",
                    )
                    returncode, result = self._run(
                        ["validate", "--campaign", str(invalid)]
                    )
                self.assertEqual(returncode, 2)
                self.assertFalse(result["ok"])
                self.assertIn("MALFORMED_JSON", _codes(result["issues"]))

    def test_unpaired_surrogate_json_exits_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "campaign.json"
            campaign = _campaign()
            campaign["campaign_title"] = chr(0xD800)
            invalid.write_text(
                json.dumps(campaign, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            returncode, result = self._run(
                ["validate", "--campaign", str(invalid)]
            )
        self.assertEqual(returncode, 2)
        self.assertIn("INVALID_UNICODE_SCALAR", _codes(result["issues"]))


if __name__ == "__main__":
    unittest.main()
