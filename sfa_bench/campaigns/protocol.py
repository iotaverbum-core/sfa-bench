"""Deterministic validation for governed external-model campaigns.

The campaign documents are capture and governance inputs. They never become
verifier inputs. Validation is manual and standard-library-only so the same
issues, in the same order, are produced offline on every run.
"""
from __future__ import annotations

import math
import re
from pathlib import PurePosixPath
from typing import Any, Iterable


CAMPAIGN_SCHEMA = "sfa_bench.campaign.v1"
CANDIDATE_MANIFEST_SCHEMA = "sfa_bench.candidate_manifest.v1"
EXECUTION_PLAN_SCHEMA = "sfa_bench.execution_plan.v1"
RATIFICATION_POLICY_SCHEMA = "sfa_bench.ratification_policy.v1"
BENCHMARK_LOCK_SCHEMA = "sfa_bench.benchmark_lock.v1"

SUPPORTED_SCHEMAS = frozenset(
    {
        CAMPAIGN_SCHEMA,
        CANDIDATE_MANIFEST_SCHEMA,
        EXECUTION_PLAN_SCHEMA,
        RATIFICATION_POLICY_SCHEMA,
        BENCHMARK_LOCK_SCHEMA,
    }
)

RUN_CLASSIFICATIONS = frozenset({"development", "pilot", "official"})
CAMPAIGN_STATUSES = frozenset(
    {"draft_not_executed", "preregistered", "halted_before_execution"}
)
ALIAS_STATUSES = frozenset(
    {"fixed_snapshot", "mutable_alias", "to_be_confirmed"}
)
RATIFICATION_DECISIONS = frozenset({"prepare", "ratify", "reject", "halt"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
RELEASE_RE = re.compile(
    r"^v\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$"
)

_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token|"
    r"authorization[_-]?token|password|passwd|client[_-]?secret|"
    r"private[_-]?key|credentials?)",
    re.IGNORECASE,
)
_SECRET_VALUE_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
)

_CAMPAIGN_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "campaign_title",
        "status",
        "research_question",
        "candidate_provider",
        "provider_model_identifier",
        "candidate_snapshot_or_alias_status",
        "mutable_alias_use_declared",
        "api_or_execution_surface",
        "system_prompt",
        "user_prompt_or_case_set",
        "tool_permissions",
        "reasoning_configuration",
        "sampling_configuration",
        "run_count",
        "run_classification",
        "benchmark_commit_sha",
        "verifier_commit_sha",
        "normalizer_version",
        "adapter_version",
        "release_identifier",
        "frozen_case_set_digest",
        "frozen_taxonomy_digest",
        "frozen_rule_digest",
        "success_criteria",
        "failure_criteria",
        "invalid_output_policy",
        "retry_policy",
        "exclusion_policy",
        "halt_conditions",
        "ratification_policy",
        "holdout_commitment",
        "declared_limitations",
        "benchmark_inputs",
        "execution_plan",
        "benchmark_lock",
    }
)
_CAMPAIGN_REQUIRED = tuple(sorted(_CAMPAIGN_FIELDS - {"benchmark_lock"}))

_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "candidate_id",
        "campaign_id",
        "provider",
        "model_string_supplied_at_execution",
        "snapshot_or_alias_status",
        "mutable_alias_use_declared",
        "observed_provider_model_metadata",
        "configuration",
        "tool_state",
        "environment",
        "capture_boundary_version",
        "campaign_reference",
        "judgment_boundary",
    }
)
_SELF_RATIFICATION_KEYS = frozenset(
    {
        "ratified",
        "isratified",
        "ratificationdecision",
        "ratificationstatus",
        "promoted",
        "ispromoted",
        "promotionready",
        "promotionstatus",
        "automaticratification",
        "automaticpromotion",
        "autopromote",
    }
)
_GOVERNANCE_VALUE_KEYS = frozenset(
    {
        "decision",
        "outcome",
        "result",
        "state",
        "status",
    }
)
_DRAFT_COMPLETION_KEYS = frozenset(
    {
        "completed",
        "executionresult",
        "official",
        "officialresult",
        "passed",
        "providerranking",
        "score",
    }
)
_DRAFT_COMPLETION_VALUE_KEYS = frozenset(
    {
        "classification",
        "decision",
        "outcome",
        "result",
        "runclassification",
        "runstatus",
        "state",
        "status",
    }
)
_DRAFT_COMPLETION_VALUE_RE = re.compile(
    r"\b(?:complete(?:d)?|official|pass(?:ed)?|rank(?:ed|ing)?)\b",
    re.IGNORECASE,
)
_CAMPAIGN_UNTRUSTED_TEXT_SURFACES = frozenset(
    {"reasoning_configuration", "sampling_configuration"}
)
_CANDIDATE_UNTRUSTED_TEXT_SURFACES = frozenset(
    {
        "configuration",
        "environment",
        "observed_provider_model_metadata",
        "tool_state",
    }
)


Issue = dict[str, str]


def issue(code: str, path: str, message: str) -> Issue:
    """Build one stable, machine-readable validation issue."""
    return {"code": code, "path": path, "message": message}


def sort_issues(issues: Iterable[Issue]) -> list[Issue]:
    """Return issues in a stable order independent of traversal accidents."""
    return sorted(
        issues,
        key=lambda item: (item["path"], item["code"], item["message"]),
    )


def _join(path: str, key: str | int) -> str:
    return f"{path}.{key}" if path != "$" else f"$.{key}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_fields(
    document: dict[str, Any], required: Iterable[str], issues: list[Issue], path: str
) -> None:
    for field in required:
        if field not in document:
            issues.append(
                issue(
                    "MISSING_REQUIRED_FIELD",
                    _join(path, field),
                    f"required field {field!r} is missing",
                )
            )


def _unknown_fields(
    document: dict[str, Any], allowed: frozenset[str], issues: list[Issue], path: str
) -> None:
    for field in sorted(set(document) - allowed):
        issues.append(
            issue(
                "UNKNOWN_FIELD",
                _join(path, field),
                f"field {field!r} is not allowed by this schema",
            )
        )


def _nonempty_string(
    document: dict[str, Any], field: str, issues: list[Issue], path: str = "$"
) -> str | None:
    if field not in document:
        return None
    value = document[field]
    if not isinstance(value, str) or not value.strip():
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                _join(path, field),
                f"field {field!r} must be a non-empty string",
            )
        )
        return None
    return value


def _mapping(
    document: dict[str, Any], field: str, issues: list[Issue], path: str = "$"
) -> dict[str, Any] | None:
    if field not in document:
        return None
    value = document[field]
    if not isinstance(value, dict):
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                _join(path, field),
                f"field {field!r} must be an object",
            )
        )
        return None
    return value


def _string_list(
    document: dict[str, Any],
    field: str,
    issues: list[Issue],
    path: str = "$",
    *,
    nonempty: bool = False,
) -> list[str] | None:
    field_path = _join(path, field)
    if field not in document:
        return None
    value = document[field]
    if not isinstance(value, list):
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                field_path,
                f"field {field!r} must be an array of strings",
            )
        )
        return None
    if nonempty and not value:
        issues.append(
            issue("EMPTY_REQUIRED_LIST", field_path, f"field {field!r} must not be empty")
        )
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            issues.append(
                issue(
                    "INVALID_FIELD_TYPE",
                    _join(field_path, index),
                    "array item must be a non-empty string",
                )
            )
        else:
            result.append(item)
    if len(result) != len(set(result)):
        issues.append(
            issue("DUPLICATE_LIST_ENTRY", field_path, "array entries must be unique")
        )
    return result


def _bool_field(
    document: dict[str, Any], field: str, issues: list[Issue], path: str = "$"
) -> bool | None:
    if field not in document:
        return None
    value = document[field]
    if not isinstance(value, bool):
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                _join(path, field),
                f"field {field!r} must be a boolean",
            )
        )
        return None
    return value


def _positive_int(
    document: dict[str, Any], field: str, issues: list[Issue], path: str = "$"
) -> int | None:
    if field not in document:
        return None
    value = document[field]
    if not _is_int(value) or value < 1:
        issues.append(
            issue(
                "INVALID_FIELD_VALUE",
                _join(path, field),
                f"field {field!r} must be a positive integer",
            )
        )
        return None
    return value


def _enum_field(
    document: dict[str, Any],
    field: str,
    allowed: frozenset[str],
    issues: list[Issue],
    path: str = "$",
) -> str | None:
    value = _nonempty_string(document, field, issues, path)
    if value is not None and value not in allowed:
        issues.append(
            issue(
                "INVALID_FIELD_VALUE",
                _join(path, field),
                f"field {field!r} must be one of {sorted(allowed)!r}",
            )
        )
    return value


def _validate_schema_version(
    document: dict[str, Any], expected: str, issues: list[Issue], path: str = "$"
) -> None:
    value = _nonempty_string(document, "schema_version", issues, path)
    if value is None or value == expected:
        return
    family = expected.rsplit(".", 1)[0]
    if value.startswith(family + ".v"):
        suffix = value[len(family) + 2 :]
        if suffix.isdigit() and int(suffix) < int(expected.rsplit(".v", 1)[1]):
            issues.append(
                issue(
                    "SCHEMA_MIGRATION_REQUIRED",
                    _join(path, "schema_version"),
                    f"schema {value!r} is obsolete; migrate to {expected!r}",
                )
            )
            return
    issues.append(
        issue(
            "UNSUPPORTED_SCHEMA_VERSION",
            _join(path, "schema_version"),
            f"schema {value!r} is not supported; expected {expected!r}",
        )
    )


def _scan_secrets(value: Any, path: str = "$") -> list[Issue]:
    issues: list[Issue] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child_path = _join(path, str(key))
            child = value[key]
            if _SECRET_KEY_RE.search(str(key)):
                issues.append(
                    issue(
                        "SECRET_FIELD_FORBIDDEN",
                        child_path,
                        "credential-like fields are forbidden in campaign documents",
                    )
                )
                continue
            issues.extend(_scan_secrets(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_scan_secrets(child, _join(path, index)))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _SECRET_VALUE_RES):
            issues.append(
                issue(
                    "LIKELY_SECRET_DETECTED",
                    path,
                    "value resembles a credential and must not be stored here",
                )
            )
    return issues


def validate_finite_numbers(value: Any, path: str = "$") -> list[Issue]:
    """Reject non-standard JSON numbers throughout a protocol document."""
    issues: list[Issue] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            issues.extend(
                validate_finite_numbers(value[key], _join(path, str(key)))
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(validate_finite_numbers(child, _join(path, index)))
    elif isinstance(value, float) and not math.isfinite(value):
        issues.append(
            issue(
                "NONFINITE_NUMBER_FORBIDDEN",
                path,
                "NaN and infinite values are not valid protocol numbers",
            )
        )
    return issues


def validate_unicode_scalars(value: Any, path: str = "$") -> list[Issue]:
    """Reject strings containing unpaired UTF-16 surrogate code points."""
    issues: list[Issue] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            invalid_key = isinstance(key, str) and any(
                0xD800 <= ord(character) <= 0xDFFF for character in key
            )
            child_path = (
                f"{path}.<invalid-key>"
                if invalid_key
                else _join(path, str(key))
            )
            if invalid_key:
                issues.append(
                    issue(
                        "INVALID_UNICODE_SCALAR",
                        child_path,
                        "object keys must not contain unpaired surrogate code points",
                    )
                )
            issues.extend(
                validate_unicode_scalars(value[key], child_path)
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(validate_unicode_scalars(child, _join(path, index)))
    elif isinstance(value, str) and any(
        0xD800 <= ord(character) <= 0xDFFF for character in value
    ):
        issues.append(
            issue(
                "INVALID_UNICODE_SCALAR",
                path,
                "strings must not contain unpaired surrogate code points",
            )
        )
    return issues


def validate_repo_relative_path(value: Any, path: str) -> list[Issue]:
    """Validate a canonical repository-relative POSIX path."""
    if not isinstance(value, str) or not value.strip():
        return [issue("INVALID_PATH", path, "path must be a non-empty string")]
    if "\\" in value:
        return [issue("INVALID_PATH", path, "paths must use forward slashes")]
    if "\x00" in value:
        return [issue("INVALID_PATH", path, "path contains a NUL byte")]
    pure = PurePosixPath(value)
    if pure.is_absolute() or re.match(r"^[A-Za-z]:", value):
        return [issue("PATH_ESCAPE", path, "absolute paths are forbidden")]
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        return [
            issue(
                "PATH_TRAVERSAL",
                path,
                "path must not contain empty, dot, or parent segments",
            )
        ]
    if ":" in value:
        return [
            issue(
                "INVALID_PATH",
                path,
                "colon is forbidden in portable repository paths",
            )
        ]
    if any(
        segment.lower() in {".git", ".hg", ".svn"}
        for segment in segments
    ):
        return [
            issue(
                "INVALID_PATH",
                path,
                "repository-control directories are forbidden",
            )
        ]
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    for segment in segments:
        if segment.endswith((" ", ".")):
            return [
                issue(
                    "INVALID_PATH",
                    path,
                    "path segments must not end with a space or dot",
                )
            ]
        stem = segment.split(".", 1)[0].upper()
        if stem in reserved:
            return [
                issue(
                    "INVALID_PATH",
                    path,
                    f"reserved path segment is forbidden: {segment}",
                )
            ]
    return []


def _validate_reference(
    reference: dict[str, Any] | None,
    issues: list[Issue],
    path: str,
    *,
    allow_placeholder: bool,
) -> None:
    if reference is None:
        return
    _require_fields(reference, ("reference", "sha256"), issues, path)
    _unknown_fields(reference, frozenset({"reference", "sha256"}), issues, path)
    reference_value = _nonempty_string(reference, "reference", issues, path)
    if reference_value is not None and not (
        allow_placeholder and reference_value == "TO_BE_CONFIRMED_AT_EXECUTION"
    ):
        issues.extend(
            validate_repo_relative_path(reference_value, _join(path, "reference"))
        )
    digest = _nonempty_string(reference, "sha256", issues, path)
    if digest is not None and not SHA256_RE.fullmatch(digest):
        if not (allow_placeholder and digest == "TO_BE_CONFIRMED_AT_EXECUTION"):
            issues.append(
                issue(
                    "INVALID_DIGEST",
                    _join(path, "sha256"),
                    "sha256 must be 64 lowercase hexadecimal characters",
                )
            )


def _validate_invalid_output_policy(
    policy: dict[str, Any] | None, issues: list[Issue], path: str
) -> None:
    if policy is None:
        return
    expected: dict[str, Any] = {
        "empty_response": "no_model_output",
        "no_json_object": "unparseable_model_output",
        "non_object_json": "invalid_model_output",
        "invalid_output_score": 0,
        "canonicaliser_dispatch": "valid_json_objects_only",
        "preserve_raw_response": True,
        "preserve_parse_notes": True,
    }
    _require_fields(policy, expected, issues, path)
    _unknown_fields(policy, frozenset(expected), issues, path)
    for field, required_value in expected.items():
        if field in policy and policy[field] != required_value:
            issues.append(
                issue(
                    "INVALID_OUTPUT_POLICY_WEAKENED",
                    _join(path, field),
                    f"field must equal {required_value!r}",
                )
            )


def _validate_retry_policy(
    policy: dict[str, Any] | None, issues: list[Issue], path: str
) -> None:
    if policy is None:
        return
    allowed = frozenset(
        {
            "max_attempts",
            "retry_conditions",
            "preserve_all_attempts",
            "retry_metadata_may_affect_verdict",
        }
    )
    _require_fields(policy, allowed, issues, path)
    _unknown_fields(policy, allowed, issues, path)
    attempts = _positive_int(policy, "max_attempts", issues, path)
    conditions = _string_list(policy, "retry_conditions", issues, path)
    preserve = _bool_field(policy, "preserve_all_attempts", issues, path)
    influences = _bool_field(
        policy, "retry_metadata_may_affect_verdict", issues, path
    )
    if attempts is not None and attempts > 1 and conditions == []:
        issues.append(
            issue(
                "UNDECLARED_RETRY_CONDITIONS",
                _join(path, "retry_conditions"),
                "more than one attempt requires explicit retry conditions",
            )
        )
    if preserve is False:
        issues.append(
            issue(
                "FAILURE_PRESERVATION_REQUIRED",
                _join(path, "preserve_all_attempts"),
                "all attempts must remain preserved",
            )
        )
    if influences is True:
        issues.append(
            issue(
                "RETRY_METADATA_VERDICT_INFLUENCE",
                _join(path, "retry_metadata_may_affect_verdict"),
                "retry metadata must remain outside verifier judgment",
            )
        )


def _validate_exclusion_policy(
    policy: dict[str, Any] | None, issues: list[Issue], path: str
) -> None:
    if policy is None:
        return
    allowed = frozenset(
        {
            "declared_reasons",
            "preserve_excluded_evidence",
            "post_observation_changes_forbidden",
        }
    )
    _require_fields(policy, allowed, issues, path)
    _unknown_fields(policy, allowed, issues, path)
    _string_list(policy, "declared_reasons", issues, path)
    preserve = _bool_field(policy, "preserve_excluded_evidence", issues, path)
    frozen = _bool_field(policy, "post_observation_changes_forbidden", issues, path)
    if preserve is False:
        issues.append(
            issue(
                "EXCLUDED_EVIDENCE_MUST_BE_PRESERVED",
                _join(path, "preserve_excluded_evidence"),
                "excluded evidence must remain preserved",
            )
        )
    if frozen is False:
        issues.append(
            issue(
                "POST_OBSERVATION_MUTATION_FORBIDDEN",
                _join(path, "post_observation_changes_forbidden"),
                "exclusion policy cannot change after observation",
            )
        )


def validate_ratification_policy(
    policy: Any, path: str = "$.ratification_policy"
) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(policy, dict):
        return [issue("INVALID_FIELD_TYPE", path, "ratification policy must be an object")]
    allowed = frozenset(
        {
            "schema_version",
            "allowed_decisions",
            "reviewer_identity_required",
            "evidence_references_required",
            "reason_required",
            "lineage_linkage_required",
            "automatic_ratification",
            "automatic_promotion",
        }
    )
    _require_fields(policy, allowed, issues, path)
    _unknown_fields(policy, allowed, issues, path)
    _validate_schema_version(policy, RATIFICATION_POLICY_SCHEMA, issues, path)
    decisions = _string_list(
        policy, "allowed_decisions", issues, path, nonempty=True
    )
    if decisions is not None:
        unknown = sorted(set(decisions) - RATIFICATION_DECISIONS)
        if unknown:
            issues.append(
                issue(
                    "INVALID_RATIFICATION_DECISION",
                    _join(path, "allowed_decisions"),
                    f"unsupported decisions: {unknown!r}",
                )
            )
        required = {"ratify", "reject", "halt"}
        missing = sorted(required - set(decisions))
        if missing:
            issues.append(
                issue(
                    "MISSING_RATIFICATION_DECISION",
                    _join(path, "allowed_decisions"),
                    f"required human decisions missing: {missing!r}",
                )
            )
    for field in (
        "reviewer_identity_required",
        "evidence_references_required",
        "reason_required",
        "lineage_linkage_required",
    ):
        value = _bool_field(policy, field, issues, path)
        if value is False:
            issues.append(
                issue(
                    "RATIFICATION_EVIDENCE_REQUIRED",
                    _join(path, field),
                    f"field {field!r} must be true",
                )
            )
    automatic_ratification = _bool_field(
        policy, "automatic_ratification", issues, path
    )
    automatic_promotion = _bool_field(policy, "automatic_promotion", issues, path)
    if automatic_ratification is True:
        issues.append(
            issue(
                "AUTOMATIC_RATIFICATION_FORBIDDEN",
                _join(path, "automatic_ratification"),
                "ratification requires an explicit human decision",
            )
        )
    if automatic_promotion is True:
        issues.append(
            issue(
                "AUTOMATIC_PROMOTION_FORBIDDEN",
                _join(path, "automatic_promotion"),
                "promotion must never be automatic",
            )
        )
    return sort_issues(issues)


def validate_execution_plan(
    plan: Any,
    path: str = "$.execution_plan",
    *,
    campaign_id: str | None = None,
    run_count: int | None = None,
    run_classification: str | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(plan, dict):
        return [issue("INVALID_FIELD_TYPE", path, "execution plan must be an object")]
    allowed = frozenset(
        {
            "schema_version",
            "campaign_id",
            "run_classification",
            "planned_repetitions",
            "ordering_policy",
            "ordering_seed",
            "concurrency_policy",
            "retry_rules",
            "error_handling",
            "exclusion_rules",
            "output_path",
            "halt_conditions",
        }
    )
    _require_fields(plan, allowed - {"ordering_seed"}, issues, path)
    _unknown_fields(plan, allowed, issues, path)
    _validate_schema_version(plan, EXECUTION_PLAN_SCHEMA, issues, path)
    plan_campaign_id = _nonempty_string(plan, "campaign_id", issues, path)
    classification = _enum_field(
        plan, "run_classification", RUN_CLASSIFICATIONS, issues, path
    )
    repetitions = _positive_int(plan, "planned_repetitions", issues, path)
    ordering = _enum_field(
        plan,
        "ordering_policy",
        frozenset(
            {
                "fixed",
                "deterministic_shuffle_with_declared_seed",
                "provider_neutral_round_robin",
            }
        ),
        issues,
        path,
    )
    if ordering == "deterministic_shuffle_with_declared_seed":
        if "ordering_seed" not in plan:
            issues.append(
                issue(
                    "ORDERING_SEED_REQUIRED",
                    _join(path, "ordering_seed"),
                    "deterministic shuffle requires a declared positive seed",
                )
            )
        else:
            _positive_int(plan, "ordering_seed", issues, path)
    elif "ordering_seed" in plan:
        issues.append(
            issue(
                "ORDERING_SEED_NOT_APPLICABLE",
                _join(path, "ordering_seed"),
                "ordering_seed is only valid for deterministic shuffle",
            )
        )
    if campaign_id is not None and plan_campaign_id != campaign_id:
        issues.append(
            issue(
                "CAMPAIGN_REFERENCE_MISMATCH",
                _join(path, "campaign_id"),
                "execution plan campaign_id does not match its campaign",
            )
        )
    if run_count is not None and repetitions != run_count:
        issues.append(
            issue(
                "RUN_COUNT_MISMATCH",
                _join(path, "planned_repetitions"),
                "planned repetitions must equal campaign run_count",
            )
        )
    if run_classification is not None and classification != run_classification:
        issues.append(
            issue(
                "RUN_CLASSIFICATION_MISMATCH",
                _join(path, "run_classification"),
                "execution plan classification does not match its campaign",
            )
        )

    concurrency = _mapping(plan, "concurrency_policy", issues, path)
    if concurrency is not None:
        concurrency_path = _join(path, "concurrency_policy")
        concurrency_allowed = frozenset({"mode", "max_workers"})
        _require_fields(concurrency, concurrency_allowed, issues, concurrency_path)
        _unknown_fields(concurrency, concurrency_allowed, issues, concurrency_path)
        _enum_field(
            concurrency,
            "mode",
            frozenset({"serial", "fixed"}),
            issues,
            concurrency_path,
        )
        _positive_int(concurrency, "max_workers", issues, concurrency_path)

    retry = _mapping(plan, "retry_rules", issues, path)
    _validate_retry_policy(retry, issues, _join(path, "retry_rules"))

    error_handling = _mapping(plan, "error_handling", issues, path)
    if error_handling is not None:
        error_path = _join(path, "error_handling")
        error_allowed = frozenset({"preserve_failures", "invalid_output_verdicts"})
        _require_fields(error_handling, error_allowed, issues, error_path)
        _unknown_fields(error_handling, error_allowed, issues, error_path)
        preserves = _bool_field(error_handling, "preserve_failures", issues, error_path)
        verdicts = _string_list(
            error_handling, "invalid_output_verdicts", issues, error_path, nonempty=True
        )
        if preserves is False:
            issues.append(
                issue(
                    "FAILURE_PRESERVATION_REQUIRED",
                    _join(error_path, "preserve_failures"),
                    "execution must preserve failures",
                )
            )
        expected_verdicts = {
            "no_model_output",
            "unparseable_model_output",
            "invalid_model_output",
        }
        if verdicts is not None and set(verdicts) != expected_verdicts:
            issues.append(
                issue(
                    "INVALID_OUTPUT_POLICY_MISMATCH",
                    _join(error_path, "invalid_output_verdicts"),
                    f"invalid verdicts must equal {sorted(expected_verdicts)!r}",
                )
            )

    exclusion = _mapping(plan, "exclusion_rules", issues, path)
    _validate_exclusion_policy(exclusion, issues, _join(path, "exclusion_rules"))

    output = _nonempty_string(plan, "output_path", issues, path)
    if output is not None:
        output_path = _join(path, "output_path")
        issues.extend(validate_repo_relative_path(output, output_path))
        if not output.startswith("out/campaign_runs/"):
            issues.append(
                issue(
                    "OUTPUT_PATH_NOT_APPROVED",
                    output_path,
                    "campaign outputs must remain under out/campaign_runs/",
                )
            )
    _string_list(plan, "halt_conditions", issues, path, nonempty=True)
    return sort_issues(issues)


def _validate_benchmark_inputs(
    inputs: dict[str, Any] | None, issues: list[Issue], path: str
) -> None:
    if inputs is None:
        return
    allowed = frozenset(
        {
            "case_paths",
            "evidence_paths",
            "rule_paths",
            "taxonomy_paths",
            "normalizer_paths",
            "adapter_paths",
            "schema_paths",
            "declared_commands",
        }
    )
    _require_fields(inputs, allowed, issues, path)
    _unknown_fields(inputs, allowed, issues, path)
    for field in sorted(allowed - {"declared_commands"}):
        paths = _string_list(inputs, field, issues, path, nonempty=True)
        if paths is not None:
            field_path = _join(path, field)
            for index, value in enumerate(paths):
                issues.extend(validate_repo_relative_path(value, _join(field_path, index)))
    commands = _string_list(
        inputs, "declared_commands", issues, path, nonempty=True
    )
    if commands is not None:
        for index, command in enumerate(commands):
            if "\n" in command or "\r" in command:
                issues.append(
                    issue(
                        "INVALID_COMMAND",
                        _join(_join(path, "declared_commands"), index),
                        "declared commands must be single-line strings",
                    )
                )


def _validate_holdout(
    holdout: dict[str, Any] | None, issues: list[Issue], path: str
) -> None:
    if holdout is None:
        return
    allowed = frozenset(
        {"committed", "case_set_reference", "commitment_digest", "access_policy"}
    )
    _require_fields(holdout, allowed, issues, path)
    _unknown_fields(holdout, allowed, issues, path)
    committed = _bool_field(holdout, "committed", issues, path)
    _nonempty_string(holdout, "case_set_reference", issues, path)
    digest = _nonempty_string(holdout, "commitment_digest", issues, path)
    _nonempty_string(holdout, "access_policy", issues, path)
    if committed is True and digest is not None and not SHA256_RE.fullmatch(digest):
        issues.append(
            issue(
                "INVALID_DIGEST",
                _join(path, "commitment_digest"),
                "a committed holdout requires a SHA-256 digest",
            )
        )


def _validate_lock_reference(
    lock_ref: Any,
    issues: list[Issue],
    path: str,
    *,
    required: bool,
    repository_commit: str | None,
    verifier_commit: str | None,
) -> None:
    if lock_ref is None:
        if required:
            issues.append(
                issue(
                    "OFFICIAL_CAMPAIGN_REQUIRES_LOCK",
                    path,
                    "official campaigns require a frozen benchmark lock",
                )
            )
        return
    if not isinstance(lock_ref, dict):
        issues.append(issue("INVALID_FIELD_TYPE", path, "benchmark_lock must be an object"))
        return
    allowed = frozenset(
        {"path", "lock_digest", "repository_commit", "verifier_commit", "status"}
    )
    _require_fields(lock_ref, allowed, issues, path)
    _unknown_fields(lock_ref, allowed, issues, path)
    lock_path = _nonempty_string(lock_ref, "path", issues, path)
    if lock_path is not None:
        issues.extend(validate_repo_relative_path(lock_path, _join(path, "path")))
        if not lock_path.startswith("out/campaign_locks/"):
            issues.append(
                issue(
                    "BENCHMARK_LOCK_PATH_NOT_APPROVED",
                    _join(path, "path"),
                    "benchmark lock must remain under out/campaign_locks/",
                )
            )
    digest = _nonempty_string(lock_ref, "lock_digest", issues, path)
    if digest is not None and not SHA256_RE.fullmatch(digest):
        issues.append(
            issue(
                "INVALID_DIGEST",
                _join(path, "lock_digest"),
                "lock_digest must be a SHA-256 digest",
            )
        )
    lock_repo = _nonempty_string(lock_ref, "repository_commit", issues, path)
    lock_verifier = _nonempty_string(lock_ref, "verifier_commit", issues, path)
    status = _nonempty_string(lock_ref, "status", issues, path)
    if status is not None and status != "frozen":
        issues.append(
            issue(
                "BENCHMARK_LOCK_NOT_FROZEN",
                _join(path, "status"),
                "benchmark lock status must be 'frozen'",
            )
        )
    if repository_commit is not None and lock_repo != repository_commit:
        issues.append(
            issue(
                "OFFICIAL_LOCK_REFERENCE_MISMATCH",
                _join(path, "repository_commit"),
                "campaign and lock repository commits differ",
            )
        )
    if verifier_commit is not None and lock_verifier != verifier_commit:
        issues.append(
            issue(
                "OFFICIAL_LOCK_REFERENCE_MISMATCH",
                _join(path, "verifier_commit"),
                "campaign and lock verifier commits differ",
            )
        )


def validate_campaign(campaign: Any, *, for_lock_build: bool = False) -> list[Issue]:
    """Validate one campaign pre-registration and return stable issues."""
    issues: list[Issue] = []
    if not isinstance(campaign, dict):
        return [issue("MALFORMED_DOCUMENT", "$", "campaign must be a JSON object")]
    unicode_issues = validate_unicode_scalars(campaign)
    if unicode_issues:
        return sort_issues(unicode_issues)

    _require_fields(campaign, _CAMPAIGN_REQUIRED, issues, "$")
    _unknown_fields(campaign, _CAMPAIGN_FIELDS, issues, "$")
    _validate_schema_version(campaign, CAMPAIGN_SCHEMA, issues)
    campaign_id = _nonempty_string(campaign, "campaign_id", issues)
    _nonempty_string(campaign, "campaign_title", issues)
    status = _enum_field(campaign, "status", CAMPAIGN_STATUSES, issues)
    _nonempty_string(campaign, "research_question", issues)
    _nonempty_string(campaign, "candidate_provider", issues)
    model_id = _nonempty_string(campaign, "provider_model_identifier", issues)
    alias_status = _enum_field(
        campaign, "candidate_snapshot_or_alias_status", ALIAS_STATUSES, issues
    )
    alias_declared = _bool_field(campaign, "mutable_alias_use_declared", issues)
    if alias_status == "mutable_alias" and alias_declared is not True:
        issues.append(
            issue(
                "MUTABLE_ALIAS_UNDECLARED",
                "$.mutable_alias_use_declared",
                "mutable model aliases require an explicit declaration",
            )
        )
    _nonempty_string(campaign, "api_or_execution_surface", issues)

    allow_placeholder = status == "draft_not_executed" and not for_lock_build
    system_prompt = _mapping(campaign, "system_prompt", issues)
    _validate_reference(
        system_prompt, issues, "$.system_prompt", allow_placeholder=allow_placeholder
    )
    user_prompt = _mapping(campaign, "user_prompt_or_case_set", issues)
    _validate_reference(
        user_prompt,
        issues,
        "$.user_prompt_or_case_set",
        allow_placeholder=allow_placeholder,
    )
    _string_list(campaign, "tool_permissions", issues)
    _mapping(campaign, "reasoning_configuration", issues)
    _mapping(campaign, "sampling_configuration", issues)
    run_count = _positive_int(campaign, "run_count", issues)
    classification = _enum_field(
        campaign, "run_classification", RUN_CLASSIFICATIONS, issues
    )

    repository_commit = _nonempty_string(campaign, "benchmark_commit_sha", issues)
    verifier_commit = _nonempty_string(campaign, "verifier_commit_sha", issues)
    for field, value in (
        ("benchmark_commit_sha", repository_commit),
        ("verifier_commit_sha", verifier_commit),
    ):
        if value is not None and not GIT_SHA_RE.fullmatch(value):
            issues.append(
                issue(
                    "INVALID_GIT_COMMIT",
                    _join("$", field),
                    f"field {field!r} must be a 40- or 64-character lowercase commit ID",
                )
            )
    _nonempty_string(campaign, "normalizer_version", issues)
    _nonempty_string(campaign, "adapter_version", issues)
    release_identifier = _nonempty_string(campaign, "release_identifier", issues)
    if release_identifier is not None and not RELEASE_RE.fullmatch(release_identifier):
        issues.append(
            issue(
                "INVALID_RELEASE_IDENTIFIER",
                "$.release_identifier",
                "release_identifier must be a public SFA-Bench release label",
            )
        )
    for field in (
        "frozen_case_set_digest",
        "frozen_taxonomy_digest",
        "frozen_rule_digest",
    ):
        digest = _nonempty_string(campaign, field, issues)
        if digest is not None and not SHA256_RE.fullmatch(digest):
            if not (allow_placeholder and digest == "TO_BE_CONFIRMED_AT_EXECUTION"):
                issues.append(
                    issue(
                        "INVALID_DIGEST",
                        _join("$", field),
                        f"field {field!r} must be a SHA-256 digest",
                    )
                )

    _string_list(campaign, "success_criteria", issues, nonempty=True)
    _string_list(campaign, "failure_criteria", issues, nonempty=True)
    invalid_output = _mapping(campaign, "invalid_output_policy", issues)
    _validate_invalid_output_policy(invalid_output, issues, "$.invalid_output_policy")
    retry = _mapping(campaign, "retry_policy", issues)
    _validate_retry_policy(retry, issues, "$.retry_policy")
    exclusion = _mapping(campaign, "exclusion_policy", issues)
    _validate_exclusion_policy(exclusion, issues, "$.exclusion_policy")
    _string_list(campaign, "halt_conditions", issues, nonempty=True)

    ratification = campaign.get("ratification_policy")
    issues.extend(validate_ratification_policy(ratification))
    holdout = _mapping(campaign, "holdout_commitment", issues)
    _validate_holdout(holdout, issues, "$.holdout_commitment")
    _string_list(campaign, "declared_limitations", issues, nonempty=True)
    benchmark_inputs = _mapping(campaign, "benchmark_inputs", issues)
    _validate_benchmark_inputs(benchmark_inputs, issues, "$.benchmark_inputs")

    plan = campaign.get("execution_plan")
    issues.extend(
        validate_execution_plan(
            plan,
            campaign_id=campaign_id,
            run_count=run_count,
            run_classification=classification,
        )
    )
    if isinstance(plan, dict):
        policy_pairs = (
            ("retry_policy", "retry_rules"),
            ("exclusion_policy", "exclusion_rules"),
            ("halt_conditions", "halt_conditions"),
        )
        for campaign_field, plan_field in policy_pairs:
            if campaign.get(campaign_field) != plan.get(plan_field):
                issues.append(
                    issue(
                        "POLICY_SURFACE_MISMATCH",
                        _join("$.execution_plan", plan_field),
                        f"execution plan {plan_field!r} must equal campaign "
                        f"{campaign_field!r}",
                    )
                )

    official = classification == "official"
    _validate_lock_reference(
        campaign.get("benchmark_lock"),
        issues,
        "$.benchmark_lock",
        required=official and not for_lock_build,
        repository_commit=repository_commit,
        verifier_commit=verifier_commit,
    )
    if official and alias_status == "to_be_confirmed":
        issues.append(
            issue(
                "OFFICIAL_MODEL_ID_UNRESOLVED",
                "$.provider_model_identifier",
                "official campaigns require a resolved model identifier",
            )
        )
    if official and model_id == "TO_BE_CONFIRMED_AT_EXECUTION":
        issues.append(
            issue(
                "OFFICIAL_MODEL_ID_UNRESOLVED",
                "$.provider_model_identifier",
                "official campaigns require a resolved model identifier",
            )
        )
    if status == "draft_not_executed" and official:
        issues.append(
            issue(
                "DRAFT_OFFICIAL_CONFLICT",
                "$.run_classification",
                "a draft_not_executed campaign cannot claim official classification",
            )
        )
    for field in sorted(campaign):
        if status == "draft_not_executed":
            issues.extend(
                _scan_draft_completion_claims(
                    campaign[field],
                    _join("$", field),
                    claim_context=(
                        field in _CAMPAIGN_UNTRUSTED_TEXT_SURFACES
                    ),
                )
            )
        if field == "ratification_policy":
            continue
        issues.extend(
            _scan_governance_claims(
                campaign[field],
                _join("$", field),
                code="CAMPAIGN_GOVERNANCE_CLAIM_FORBIDDEN",
                message=(
                    "campaign configuration cannot assert ratification "
                    "or automatic promotion"
                ),
                claim_context=(
                    field in _CAMPAIGN_UNTRUSTED_TEXT_SURFACES
                ),
            )
        )
    issues.extend(validate_finite_numbers(campaign))
    issues.extend(_scan_secrets(campaign))
    return sort_issues(issues)


def _normalized_control_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_governance_control_key(key: Any) -> bool:
    normalized = _normalized_control_key(key)
    return (
        normalized in _SELF_RATIFICATION_KEYS
        or "ratif" in normalized
        or "promot" in normalized
    )


def _contains_governance_term(value: str) -> bool:
    lowered = value.lower()
    return "ratif" in lowered or "promot" in lowered


def _scan_governance_claims(
    value: Any,
    path: str = "$",
    *,
    code: str,
    message: str,
    claim_context: bool = False,
) -> list[Issue]:
    issues: list[Issue] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child_path = _join(path, str(key))
            normalized = _normalized_control_key(key)
            if _is_governance_control_key(key):
                issues.append(issue(code, child_path, message))
            issues.extend(
                _scan_governance_claims(
                    value[key],
                    child_path,
                    code=code,
                    message=message,
                    claim_context=(
                        claim_context
                        or normalized in _GOVERNANCE_VALUE_KEYS
                    ),
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(
                _scan_governance_claims(
                    child,
                    _join(path, index),
                    code=code,
                    message=message,
                    claim_context=claim_context,
                )
            )
    elif (
        claim_context
        and isinstance(value, str)
        and _contains_governance_term(value)
    ):
        issues.append(issue(code, path, message))
    return issues


def _scan_draft_completion_claims(
    value: Any,
    path: str = "$",
    *,
    claim_context: bool = False,
) -> list[Issue]:
    issues: list[Issue] = []
    if isinstance(value, dict):
        for key in sorted(value, key=str):
            child_path = _join(path, str(key))
            normalized = _normalized_control_key(key)
            if normalized in _DRAFT_COMPLETION_KEYS:
                issues.append(
                    issue(
                        "DRAFT_COMPLETION_CLAIM",
                        child_path,
                        "draft campaigns cannot contain execution or completion claims",
                    )
                )
            issues.extend(
                _scan_draft_completion_claims(
                    value[key],
                    child_path,
                    claim_context=(
                        claim_context
                        or normalized in _DRAFT_COMPLETION_VALUE_KEYS
                    ),
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(
                _scan_draft_completion_claims(
                    child,
                    _join(path, index),
                    claim_context=claim_context,
                )
            )
    elif (
        claim_context
        and isinstance(value, str)
        and _DRAFT_COMPLETION_VALUE_RE.search(value)
    ):
        issues.append(
            issue(
                "DRAFT_COMPLETION_CLAIM",
                path,
                "draft campaigns cannot contain execution or completion claims",
            )
        )
    return issues


def validate_candidate_manifest(manifest: Any) -> list[Issue]:
    """Validate a provider-neutral capture manifest."""
    issues: list[Issue] = []
    if not isinstance(manifest, dict):
        return [
            issue("MALFORMED_DOCUMENT", "$", "candidate manifest must be a JSON object")
        ]
    unicode_issues = validate_unicode_scalars(manifest)
    if unicode_issues:
        return sort_issues(unicode_issues)
    _require_fields(manifest, _CANDIDATE_FIELDS, issues, "$")
    _unknown_fields(manifest, _CANDIDATE_FIELDS, issues, "$")
    _validate_schema_version(manifest, CANDIDATE_MANIFEST_SCHEMA, issues)
    status = _nonempty_string(manifest, "status", issues)
    if status is not None and status != "draft_not_executed":
        issues.append(
            issue(
                "CANDIDATE_MANIFEST_STATUS_INVALID",
                "$.status",
                "alpha.1 candidate manifests must be draft_not_executed",
            )
        )
    _nonempty_string(manifest, "candidate_id", issues)
    _nonempty_string(manifest, "campaign_id", issues)
    _nonempty_string(manifest, "provider", issues)
    _nonempty_string(manifest, "model_string_supplied_at_execution", issues)
    alias_status = _enum_field(
        manifest, "snapshot_or_alias_status", ALIAS_STATUSES, issues
    )
    alias_declared = _bool_field(manifest, "mutable_alias_use_declared", issues)
    if alias_status == "mutable_alias" and alias_declared is not True:
        issues.append(
            issue(
                "MUTABLE_ALIAS_UNDECLARED",
                "$.mutable_alias_use_declared",
                "mutable model aliases require an explicit declaration",
            )
        )
    metadata = manifest.get("observed_provider_model_metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                "$.observed_provider_model_metadata",
                "observed provider metadata must be null or an object",
            )
        )
    for field in ("configuration", "tool_state", "environment"):
        _mapping(manifest, field, issues)
    _nonempty_string(manifest, "capture_boundary_version", issues)

    campaign_ref = _mapping(manifest, "campaign_reference", issues)
    if campaign_ref is not None:
        path = "$.campaign_reference"
        allowed = frozenset({"campaign_id", "path", "sha256"})
        _require_fields(campaign_ref, allowed, issues, path)
        _unknown_fields(campaign_ref, allowed, issues, path)
        ref_campaign_id = _nonempty_string(campaign_ref, "campaign_id", issues, path)
        if ref_campaign_id != manifest.get("campaign_id"):
            issues.append(
                issue(
                    "CAMPAIGN_REFERENCE_MISMATCH",
                    _join(path, "campaign_id"),
                    "manifest and campaign reference IDs differ",
                )
            )
        ref_path = _nonempty_string(campaign_ref, "path", issues, path)
        if ref_path is not None:
            issues.extend(validate_repo_relative_path(ref_path, _join(path, "path")))
        digest = _nonempty_string(campaign_ref, "sha256", issues, path)
        if digest is not None and not SHA256_RE.fullmatch(digest):
            if not (status == "draft_not_executed" and digest == "TO_BE_CONFIRMED_AT_EXECUTION"):
                issues.append(
                    issue(
                        "INVALID_DIGEST",
                        _join(path, "sha256"),
                        "campaign reference digest must be SHA-256",
                    )
                )

    boundary = _mapping(manifest, "judgment_boundary", issues)
    if boundary is not None:
        path = "$.judgment_boundary"
        allowed = frozenset(
            {
                "provider_metadata_may_affect_verdict",
                "adapter_metadata_may_affect_verdict",
                "retry_metadata_may_affect_verdict",
            }
        )
        _require_fields(boundary, allowed, issues, path)
        _unknown_fields(boundary, allowed, issues, path)
        for field in sorted(allowed):
            value = _bool_field(boundary, field, issues, path)
            if value is True:
                issues.append(
                    issue(
                        "METADATA_VERDICT_INFLUENCE_FORBIDDEN",
                        _join(path, field),
                        "capture metadata must remain outside verifier judgment",
                    )
                )

    for field in sorted(manifest):
        issues.extend(
            _scan_governance_claims(
                manifest[field],
                _join("$", field),
                code="CANDIDATE_SELF_RATIFICATION_FORBIDDEN",
                message=(
                    "candidate manifests cannot assert ratification "
                    "or promotion"
                ),
                claim_context=(
                    field in _CANDIDATE_UNTRUSTED_TEXT_SURFACES
                ),
            )
        )
        if status == "draft_not_executed":
            issues.extend(
                _scan_draft_completion_claims(
                    manifest[field],
                    _join("$", field),
                    claim_context=(
                        field in _CANDIDATE_UNTRUSTED_TEXT_SURFACES
                    ),
                )
            )
    issues.extend(validate_finite_numbers(manifest))
    issues.extend(_scan_secrets(manifest))
    return sort_issues(issues)


def candidate_judgment_projection(manifest: Any) -> dict[str, Any]:
    """Return the verifier-input projection of a candidate manifest.

    It is deliberately empty: campaign and provider metadata is audit evidence,
    never judgment evidence. Candidate content enters the verifier through the
    separate frozen candidate contract.
    """
    del manifest
    return {}


def validate_campaign_collection(campaigns: Any) -> list[Issue]:
    """Validate multiple campaigns and reject duplicate IDs predictably."""
    if not isinstance(campaigns, list):
        return [issue("MALFORMED_DOCUMENT", "$", "campaign collection must be an array")]
    issues: list[Issue] = []
    first_index: dict[str, int] = {}
    for index, campaign in enumerate(campaigns):
        path = f"$[{index}]"
        for entry in validate_campaign(campaign):
            suffix = entry["path"][1:] if entry["path"].startswith("$") else entry["path"]
            issues.append(issue(entry["code"], path + suffix, entry["message"]))
        if not isinstance(campaign, dict):
            continue
        campaign_id = campaign.get("campaign_id")
        if not isinstance(campaign_id, str) or not campaign_id:
            continue
        if campaign_id in first_index:
            issues.append(
                issue(
                    "DUPLICATE_CAMPAIGN_ID",
                    f"$[{index}].campaign_id",
                    f"campaign ID duplicates entry {first_index[campaign_id]}",
                )
            )
        else:
            first_index[campaign_id] = index
    return sort_issues(issues)
