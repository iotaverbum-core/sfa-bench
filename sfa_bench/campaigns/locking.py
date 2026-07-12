"""Deterministic benchmark-lock construction and verification."""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from typing import Any, Iterable

from .protocol import (
    BENCHMARK_LOCK_SCHEMA,
    GIT_SHA_RE,
    Issue,
    RELEASE_RE,
    SHA256_RE,
    issue,
    sort_issues,
    validate_campaign,
    validate_finite_numbers,
    validate_repo_relative_path,
    validate_unicode_scalars,
)


_PACKAGE_VERSION_RE = re.compile(
    r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE
)
_PRERELEASE_VERSION_RE = re.compile(
    r"^(\d+\.\d+\.\d+)(a|b|rc)(\d+)$"
)
_ENVELOPE_FIELDS = frozenset({"created_at"})


# These paths implement the fixed judge or its shared deterministic contracts.
# Campaign authors cannot remove them from a lock declaration.
FIXED_VERIFIER_PATHS: tuple[str, ...] = (
    "sfa/categories.py",
    "sfa/hashing.py",
    "sfa/rederive.py",
    "sfa/validation.py",
    "sfa/verifier.py",
    "sfa_bench/frontier_delta/schemas.py",
    "sfa_bench/frontier_delta/scorers/__init__.py",
    "sfa_bench/frontier_delta/scorers/checks.py",
)

_IGNORED_DIRECTORY_NAMES = frozenset(
    {".git", ".hg", ".pytest_cache", ".svn", "__pycache__"}
)
_IGNORED_FILE_NAMES = frozenset({".DS_Store", "Thumbs.db"})
_IGNORED_FILE_SUFFIXES = frozenset({".pyc", ".pyo"})

_DECLARED_BINDING_FIELDS: tuple[tuple[str, str], ...] = (
    ("cases", "case_paths"),
    ("evidence", "evidence_paths"),
    ("rules", "rule_paths"),
    ("taxonomy", "taxonomy_paths"),
    ("normalizer", "normalizer_paths"),
    ("adapter", "adapter_paths"),
    ("schemas", "schema_paths"),
)
_REFERENCE_BINDING_FIELDS: tuple[tuple[str, str], ...] = (
    ("system_prompt", "system_prompt"),
    ("user_prompt_or_case_set", "user_prompt_or_case_set"),
)

_BINDING_MISMATCH_CODES = {
    "protected_verifier": "VERIFIER_BINDING_MISMATCH",
    "cases": "CASE_BINDING_MISMATCH",
    "evidence": "EVIDENCE_BINDING_MISMATCH",
    "rules": "RULE_BINDING_MISMATCH",
    "taxonomy": "TAXONOMY_BINDING_MISMATCH",
    "normalizer": "NORMALIZER_BINDING_MISMATCH",
    "adapter": "ADAPTER_BINDING_MISMATCH",
    "schemas": "SCHEMA_BINDING_MISMATCH",
    "system_prompt": "SYSTEM_PROMPT_BINDING_MISMATCH",
    "user_prompt_or_case_set": "USER_PROMPT_BINDING_MISMATCH",
}


class LockingError(ValueError):
    """Raised when a lock cannot be constructed without weakening its scope."""

    def __init__(self, issues: Iterable[Issue]):
        self.issues = sort_issues(issues)
        super().__init__("; ".join(entry["code"] for entry in self.issues))


@dataclass(frozen=True)
class RepositoryContext:
    """Observed provenance supplied to deterministic lock construction."""

    repository_commit: str
    verifier_commit: str
    release_identifier: str


def package_release_identifier(repo_root: Path) -> str:
    """Read the package version of record and return its public release label."""
    init_path = repo_root / "sfa" / "__init__.py"
    try:
        text = init_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LockingError(
            [issue("RELEASE_SOURCE_UNAVAILABLE", "$.release_identifier", str(exc))]
        ) from exc
    match = _PACKAGE_VERSION_RE.search(text)
    if match is None:
        raise LockingError(
            [
                issue(
                    "RELEASE_SOURCE_INVALID",
                    "$.release_identifier",
                    "sfa.__version__ is missing",
                )
            ]
        )
    package_version = match.group(1)
    if re.fullmatch(r"\d+\.\d+\.\d+", package_version):
        return "v" + package_version
    prerelease = _PRERELEASE_VERSION_RE.fullmatch(package_version)
    if prerelease is None:
        raise LockingError(
            [
                issue(
                    "RELEASE_SOURCE_INVALID",
                    "$.release_identifier",
                    f"unsupported package version {package_version!r}",
                )
            ]
        )
    stage = {"a": "alpha", "b": "beta", "rc": "rc"}[prerelease.group(2)]
    return f"v{prerelease.group(1)}-{stage}.{prerelease.group(3)}"


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise LockingError(
            [issue("GIT_PROVENANCE_UNAVAILABLE", "$.repository_commit", detail)]
        )
    return result.stdout


def observe_repository_context(
    repo_root: Path, benchmark_commit: str, verifier_commit: str
) -> RepositoryContext:
    """Resolve a declared benchmark commit and the current release of record."""
    try:
        resolved = _git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{benchmark_commit}^{{commit}}",
        ).strip().lower()
    except LockingError as exc:
        raise LockingError(
            [
                issue(
                    "REPOSITORY_COMMIT_UNRESOLVED",
                    "$.benchmark_commit_sha",
                    "declared benchmark commit is not available in Git history",
                )
            ]
        ) from exc
    if resolved != benchmark_commit.lower():
        raise LockingError(
            [
                issue(
                    "REPOSITORY_COMMIT_MISMATCH",
                    "$.benchmark_commit_sha",
                    "declared benchmark commit does not resolve exactly",
                )
            ]
        )
    try:
        resolved_verifier = _git(
            repo_root,
            "rev-parse",
            "--verify",
            f"{verifier_commit}^{{commit}}",
        ).strip().lower()
    except LockingError as exc:
        raise LockingError(
            [
                issue(
                    "VERIFIER_COMMIT_UNRESOLVED",
                    "$.verifier_commit_sha",
                    "declared verifier commit is not available in Git history",
                )
            ]
        ) from exc
    if resolved_verifier != verifier_commit.lower():
        raise LockingError(
            [
                issue(
                    "VERIFIER_COMMIT_MISMATCH",
                    "$.verifier_commit_sha",
                    "declared verifier commit does not resolve exactly",
                )
            ]
        )
    return RepositoryContext(
        repository_commit=resolved,
        verifier_commit=resolved_verifier,
        release_identifier=package_release_identifier(repo_root),
    )


def _context_issues(
    campaign: dict[str, Any], context: RepositoryContext
) -> list[Issue]:
    issues: list[Issue] = []
    if campaign.get("benchmark_commit_sha") != context.repository_commit:
        issues.append(
            issue(
                "REPOSITORY_COMMIT_MISMATCH",
                "$.benchmark_commit_sha",
                "campaign benchmark commit does not match observed repository context",
            )
        )
    if campaign.get("release_identifier") != context.release_identifier:
        issues.append(
            issue(
                "RELEASE_IDENTIFIER_MISMATCH",
                "$.release_identifier",
                "campaign release does not match the package version of record",
            )
        )
    if campaign.get("verifier_commit_sha") != context.verifier_commit:
        issues.append(
            issue(
                "VERIFIER_COMMIT_MISMATCH",
                "$.verifier_commit_sha",
                "campaign verifier commit does not match observed repository context",
            )
        )
    return sort_issues(issues)


def _validate_envelope(envelope: Any) -> list[Issue]:
    if envelope is None:
        return []
    if not isinstance(envelope, dict):
        return [issue("INVALID_FIELD_TYPE", "$.envelope", "envelope must be an object")]
    issues: list[Issue] = []
    for field in sorted(set(envelope) - _ENVELOPE_FIELDS):
        issues.append(
            issue(
                "ENVELOPE_FIELD_FORBIDDEN",
                f"$.envelope.{field}",
                "only nondeterministic provenance metadata is allowed",
            )
        )
    for field in sorted(set(envelope) & _ENVELOPE_FIELDS):
        value = envelope[field]
        if not isinstance(value, str) or not value.strip():
            issues.append(
                issue(
                    "INVALID_FIELD_TYPE",
                    f"$.envelope.{field}",
                    "envelope metadata must be a non-empty string",
                )
            )
            continue
        try:
            timestamp = dt.datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            timestamp = None
        if timestamp is None or timestamp.tzinfo is None:
            issues.append(
                issue(
                    "ENVELOPE_TIMESTAMP_INVALID",
                    f"$.envelope.{field}",
                    "created_at must be a timezone-qualified ISO timestamp",
                )
            )
    return sort_issues(issues)


def canonical_bytes(value: Any) -> bytes:
    """Encode JSON content in the repository's canonical form."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    """Return stable, inspectable JSON text with a trailing newline."""
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def campaign_lock_content(campaign: dict[str, Any]) -> dict[str, Any]:
    """Return campaign content sealed by a lock.

    Only the lock reference is excluded because including the lock's own digest
    would create a circular dependency. All thresholds and policies remain in
    scope.
    """
    return {key: value for key, value in campaign.items() if key != "benchmark_lock"}


def benchmark_lock_digest(lock: dict[str, Any]) -> str:
    """Hash a lock while excluding its digest and nondeterministic envelope."""
    payload = {
        key: value
        for key, value in lock.items()
        if key not in {"lock_digest", "envelope"}
    }
    return sha256_value(payload)


def _safe_repo_path(repo_root: Path, relative: str, issue_path: str) -> Path:
    path_issues = validate_repo_relative_path(relative, issue_path)
    if path_issues:
        raise LockingError(path_issues)
    root = repo_root.resolve()
    candidate = root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise LockingError(
            [issue("LOCK_INPUT_MISSING", issue_path, f"lock input does not exist: {relative}")]
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LockingError(
            [issue("PATH_ESCAPE", issue_path, f"lock input escapes repository: {relative}")]
        ) from exc
    if candidate.is_symlink():
        raise LockingError(
            [issue("LOCK_INPUT_SYMLINK", issue_path, f"symlink inputs are forbidden: {relative}")]
        )
    return resolved


def _binding_entries(
    repo_root: Path, declared_paths: list[str], issue_path: str
) -> list[dict[str, str]]:
    root = repo_root.resolve()
    files: dict[str, Path] = {}
    for index, relative in enumerate(declared_paths):
        current_issue_path = f"{issue_path}.{index}"
        resolved = _safe_repo_path(repo_root, relative, current_issue_path)
        if resolved.is_file():
            files[resolved.relative_to(root).as_posix()] = resolved
            continue
        if not resolved.is_dir():
            raise LockingError(
                [
                    issue(
                        "LOCK_INPUT_UNSUPPORTED",
                        current_issue_path,
                        f"lock input is not a regular file or directory: {relative}",
                    )
                ]
            )
        discovered = 0
        for child in sorted(resolved.rglob("*"), key=lambda item: item.as_posix()):
            relative_child = child.relative_to(resolved)
            if (
                any(part in _IGNORED_DIRECTORY_NAMES for part in relative_child.parts)
                or child.name in _IGNORED_FILE_NAMES
                or child.suffix.lower() in _IGNORED_FILE_SUFFIXES
            ):
                continue
            if child.is_symlink():
                raise LockingError(
                    [
                        issue(
                            "LOCK_INPUT_SYMLINK",
                            current_issue_path,
                            f"symlink input is forbidden: {child.relative_to(root).as_posix()}",
                        )
                    ]
                )
            if child.is_file():
                files[child.relative_to(root).as_posix()] = child
                discovered += 1
        if discovered == 0:
            raise LockingError(
                [
                    issue(
                        "LOCK_INPUT_EMPTY",
                        current_issue_path,
                        f"lock input directory has no files: {relative}",
                    )
                ]
            )
    return [
        {"path": relative, "sha256": sha256_file(files[relative])}
        for relative in sorted(files)
    ]


def binding_set_digest(entries: list[dict[str, str]]) -> str:
    """Digest one canonical, sorted binding set."""
    return sha256_value(entries)


def _reference_binding_digest(
    reference: str, entries: list[dict[str, str]]
) -> str:
    if len(entries) == 1 and entries[0]["path"] == reference:
        return entries[0]["sha256"]
    return binding_set_digest(entries)


def reference_digest(repo_root: Path, reference: str) -> str:
    """Hash a safe file reference or canonical directory binding set."""
    entries = _binding_entries(
        repo_root, [reference], "$.reference"
    )
    return _reference_binding_digest(reference, entries)


def _declared_digest_issues(
    campaign: dict[str, Any], bindings: dict[str, Any]
) -> list[Issue]:
    checks = (
        ("frozen_case_set_digest", "cases", "DECLARED_CASE_SET_DIGEST_MISMATCH"),
        ("frozen_rule_digest", "rules", "DECLARED_RULE_DIGEST_MISMATCH"),
        ("frozen_taxonomy_digest", "taxonomy", "DECLARED_TAXONOMY_DIGEST_MISMATCH"),
    )
    issues: list[Issue] = []
    for campaign_field, binding_group, code in checks:
        computed = binding_set_digest(bindings[binding_group])
        if campaign.get(campaign_field) != computed:
            issues.append(
                issue(
                    code,
                    f"$.{campaign_field}",
                    f"declared digest does not match computed {binding_group} bindings",
                )
            )
    reference_checks = (
        (
            "system_prompt",
            "system_prompt",
            "DECLARED_SYSTEM_PROMPT_DIGEST_MISMATCH",
        ),
        (
            "user_prompt_or_case_set",
            "user_prompt_or_case_set",
            "DECLARED_USER_PROMPT_DIGEST_MISMATCH",
        ),
    )
    for campaign_field, binding_group, code in reference_checks:
        declaration = campaign[campaign_field]
        computed = _reference_binding_digest(
            declaration["reference"], bindings[binding_group]
        )
        if declaration.get("sha256") != computed:
            issues.append(
                issue(
                    code,
                    f"$.{campaign_field}.sha256",
                    "declared digest does not match referenced repository content",
                )
            )
    return sort_issues(issues)


def _build_bindings(campaign: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    inputs = campaign["benchmark_inputs"]
    bindings: dict[str, Any] = {
        "protected_verifier": _binding_entries(
            repo_root, list(FIXED_VERIFIER_PATHS), "$.protected_verifier_paths"
        )
    }
    for binding_name, field in _DECLARED_BINDING_FIELDS:
        bindings[binding_name] = _binding_entries(
            repo_root,
            list(inputs[field]),
            f"$.benchmark_inputs.{field}",
        )
    for binding_name, field in _REFERENCE_BINDING_FIELDS:
        reference = campaign[field]["reference"]
        bindings[binding_name] = _binding_entries(
            repo_root,
            [reference],
            f"$.{field}.reference",
        )
    return bindings


def _changed_or_untracked_paths(
    repo_root: Path,
    commit: str,
) -> set[str]:
    changed = {
        path.replace("\\", "/")
        for path in _git(
            repo_root, "diff", "--name-only", commit, "--"
        ).splitlines()
        if path
    }
    untracked = {
        path.replace("\\", "/")
        for path in _git(
            repo_root, "ls-files", "--others", "--exclude-standard"
        ).splitlines()
        if path
    }
    return changed | untracked


def _binding_commit_issues(
    repo_root: Path,
    bindings: dict[str, Any],
    context: RepositoryContext,
) -> list[Issue]:
    """Prove bound files match their declared benchmark or verifier commit."""
    verifier_paths = {entry["path"] for entry in bindings["protected_verifier"]}
    benchmark_paths = {
        entry["path"]
        for group, entries in bindings.items()
        if group != "protected_verifier"
        for entry in entries
    }
    benchmark_drift = sorted(
        benchmark_paths
        & _changed_or_untracked_paths(repo_root, context.repository_commit)
    )
    verifier_drift = sorted(
        verifier_paths
        & _changed_or_untracked_paths(repo_root, context.verifier_commit)
    )
    drift = benchmark_drift + verifier_drift
    if not drift:
        return []
    return [
        issue(
            "LOCK_INPUT_NOT_AT_COMMIT",
            "$.bindings",
            "bound inputs differ from their declared benchmark/verifier commit: "
            + ", ".join(sorted(set(drift))),
        )
    ]


def _assemble_lock(
    campaign: dict[str, Any],
    bindings: dict[str, Any],
    *,
    context: RepositoryContext,
    envelope: dict[str, Any] | None,
) -> dict[str, Any]:
    lock: dict[str, Any] = {
        "schema_version": BENCHMARK_LOCK_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "campaign_digest": sha256_value(campaign_lock_content(campaign)),
        "repository_commit": context.repository_commit,
        "verifier_commit": context.verifier_commit,
        "release_identifier": context.release_identifier,
        "declared_commands": sorted(campaign["benchmark_inputs"]["declared_commands"]),
        "declared_input_digests": {
            "cases": campaign["frozen_case_set_digest"],
            "rules": campaign["frozen_rule_digest"],
            "taxonomy": campaign["frozen_taxonomy_digest"],
            "system_prompt": campaign["system_prompt"]["sha256"],
            "user_prompt_or_case_set": (
                campaign["user_prompt_or_case_set"]["sha256"]
            ),
        },
        "bindings": bindings,
        "digest_scope": {
            "excluded_fields": ["envelope", "lock_digest"],
            "campaign_excluded_fields": ["benchmark_lock"],
        },
    }
    if envelope is not None:
        lock["envelope"] = dict(envelope)
    lock["lock_digest"] = benchmark_lock_digest(lock)
    return lock


def _build_benchmark_lock(
    campaign: dict[str, Any],
    repo_root: Path,
    *,
    context: RepositoryContext | None = None,
    envelope: dict[str, Any] | None = None,
    verify_repository: bool,
) -> dict[str, Any]:
    """Build a deterministic lock from a valid campaign and repository tree."""
    validation_issues = validate_campaign(campaign, for_lock_build=True)
    if validation_issues:
        raise LockingError(validation_issues)
    envelope_issues = _validate_envelope(envelope)
    if envelope_issues:
        raise LockingError(envelope_issues)
    observed = context or observe_repository_context(
        repo_root,
        campaign["benchmark_commit_sha"],
        campaign["verifier_commit_sha"],
    )
    context_issues = _context_issues(campaign, observed)
    if context_issues:
        raise LockingError(context_issues)
    bindings = _build_bindings(campaign, repo_root)
    if verify_repository:
        commit_issues = _binding_commit_issues(
            repo_root, bindings, observed
        )
        if commit_issues:
            raise LockingError(commit_issues)
    digest_issues = _declared_digest_issues(campaign, bindings)
    if digest_issues:
        raise LockingError(digest_issues)
    return _assemble_lock(
        campaign, bindings, context=observed, envelope=envelope
    )


def build_benchmark_lock(
    campaign: dict[str, Any],
    repo_root: Path,
    *,
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a governed lock only from Git-observed repository provenance."""
    return _build_benchmark_lock(
        campaign,
        repo_root,
        context=None,
        envelope=envelope,
        verify_repository=True,
    )


def _build_benchmark_lock_content(
    campaign: dict[str, Any],
    repo_root: Path,
    *,
    context: RepositoryContext,
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic test content without making a provenance claim."""
    return _build_benchmark_lock(
        campaign,
        repo_root,
        context=context,
        envelope=envelope,
        verify_repository=False,
    )


def validate_benchmark_lock(lock: Any) -> list[Issue]:
    """Validate the stable structure and self-digest of a benchmark lock."""
    if not isinstance(lock, dict):
        return [issue("MALFORMED_DOCUMENT", "$", "benchmark lock must be a JSON object")]
    finite_issues = validate_finite_numbers(lock)
    unicode_issues = validate_unicode_scalars(lock)
    if unicode_issues:
        return sort_issues(unicode_issues)
    issues: list[Issue] = [*finite_issues, *unicode_issues]
    required = frozenset(
        {
            "schema_version",
            "campaign_id",
            "campaign_digest",
            "repository_commit",
            "verifier_commit",
            "release_identifier",
            "declared_commands",
            "declared_input_digests",
            "bindings",
            "digest_scope",
            "lock_digest",
        }
    )
    allowed = required | {"envelope"}
    for field in sorted(required - set(lock)):
        issues.append(
            issue(
                "MISSING_REQUIRED_FIELD",
                f"$.{field}",
                f"required field {field!r} is missing",
            )
        )
    for field in sorted(set(lock) - allowed):
        issues.append(
            issue("UNKNOWN_FIELD", f"$.{field}", f"field {field!r} is not allowed")
        )
    schema = lock.get("schema_version")
    if schema != BENCHMARK_LOCK_SCHEMA:
        code = (
            "SCHEMA_MIGRATION_REQUIRED"
            if schema == "sfa_bench.benchmark_lock.v0"
            else "UNSUPPORTED_SCHEMA_VERSION"
        )
        issues.append(
            issue(
                code,
                "$.schema_version",
                f"schema {schema!r} is not supported; expected {BENCHMARK_LOCK_SCHEMA!r}",
            )
        )
    for field in (
        "campaign_id",
        "repository_commit",
        "verifier_commit",
        "release_identifier",
    ):
        if field in lock and (not isinstance(lock[field], str) or not lock[field]):
            issues.append(
                issue("INVALID_FIELD_TYPE", f"$.{field}", "field must be a non-empty string")
            )
    for field in ("repository_commit", "verifier_commit"):
        value = lock.get(field)
        if isinstance(value, str) and value and not GIT_SHA_RE.fullmatch(value):
            issues.append(
                issue(
                    "INVALID_GIT_COMMIT",
                    f"$.{field}",
                    "field must be a full 40- or 64-character commit ID",
                )
            )
    release_identifier = lock.get("release_identifier")
    if (
        isinstance(release_identifier, str)
        and release_identifier
        and not RELEASE_RE.fullmatch(release_identifier)
    ):
        issues.append(
            issue(
                "INVALID_RELEASE_IDENTIFIER",
                "$.release_identifier",
                "field must be a public SFA-Bench release label",
            )
        )
    for field in ("campaign_digest", "lock_digest"):
        value = lock.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            issues.append(
                issue("INVALID_DIGEST", f"$.{field}", "field must be a SHA-256 digest")
            )
    commands = lock.get("declared_commands")
    if not isinstance(commands, list) or not commands or not all(
        isinstance(item, str) and item for item in commands
    ):
        issues.append(
            issue(
                "INVALID_FIELD_TYPE",
                "$.declared_commands",
                "declared_commands must be a non-empty array of strings",
            )
        )
    elif commands != sorted(set(commands)):
        issues.append(
            issue(
                "NONCANONICAL_COMMAND_SET",
                "$.declared_commands",
                "declared_commands must be unique and sorted",
            )
        )
    declared_digests = lock.get("declared_input_digests")
    if not isinstance(declared_digests, dict) or set(declared_digests) != {
        "cases",
        "rules",
        "system_prompt",
        "taxonomy",
        "user_prompt_or_case_set",
    }:
        issues.append(
            issue(
                "INVALID_DECLARED_DIGESTS",
                "$.declared_input_digests",
                "declared input digests must contain cases, prompts, rules, and taxonomy",
            )
        )
    else:
        for field in (
            "cases",
            "rules",
            "system_prompt",
            "taxonomy",
            "user_prompt_or_case_set",
        ):
            value = declared_digests[field]
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                issues.append(
                    issue(
                        "INVALID_DIGEST",
                        f"$.declared_input_digests.{field}",
                        "declared input digest must be SHA-256",
                    )
                )
    bindings = lock.get("bindings")
    expected_groups = {"protected_verifier"} | {
        binding for binding, _ in _DECLARED_BINDING_FIELDS
    } | {binding for binding, _ in _REFERENCE_BINDING_FIELDS}
    if not isinstance(bindings, dict):
        issues.append(issue("INVALID_FIELD_TYPE", "$.bindings", "bindings must be an object"))
    else:
        if set(bindings) != expected_groups:
            issues.append(
                issue(
                    "INVALID_BINDING_GROUPS",
                    "$.bindings",
                    f"binding groups must equal {sorted(expected_groups)!r}",
                )
            )
        for group in sorted(set(bindings) & expected_groups):
            entries = bindings[group]
            group_path = f"$.bindings.{group}"
            if not isinstance(entries, list) or not entries:
                issues.append(
                    issue(
                        "INVALID_FIELD_TYPE",
                        group_path,
                        "binding group must be a non-empty array",
                    )
                )
                continue
            paths: list[str] = []
            for index, entry in enumerate(entries):
                entry_path = f"{group_path}.{index}"
                if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                    issues.append(
                        issue(
                            "INVALID_BINDING_ENTRY",
                            entry_path,
                            "binding entry must contain exactly path and sha256",
                        )
                    )
                    continue
                relative = entry.get("path")
                digest = entry.get("sha256")
                issues.extend(validate_repo_relative_path(relative, f"{entry_path}.path"))
                if isinstance(relative, str):
                    paths.append(relative)
                if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                    issues.append(
                        issue(
                            "INVALID_DIGEST",
                            f"{entry_path}.sha256",
                            "binding digest must be SHA-256",
                        )
                    )
            if paths != sorted(set(paths)):
                issues.append(
                    issue(
                        "NONCANONICAL_BINDINGS",
                        group_path,
                        "binding paths must be unique and sorted",
                    )
                )
    digest_scope = lock.get("digest_scope")
    expected_scope = {
        "excluded_fields": ["envelope", "lock_digest"],
        "campaign_excluded_fields": ["benchmark_lock"],
    }
    if digest_scope != expected_scope:
        issues.append(
            issue(
                "INVALID_DIGEST_SCOPE",
                "$.digest_scope",
                "digest scope does not match the alpha.1 lock contract",
            )
        )
    if "envelope" in lock:
        issues.extend(_validate_envelope(lock["envelope"]))
    stated_digest = lock.get("lock_digest")
    if (
        not finite_issues
        and not unicode_issues
        and isinstance(stated_digest, str)
        and SHA256_RE.fullmatch(stated_digest)
    ):
        if benchmark_lock_digest(lock) != stated_digest:
            issues.append(
                issue(
                    "LOCK_DIGEST_MISMATCH",
                    "$.lock_digest",
                    "lock content does not match its stated digest",
                )
            )
    return sort_issues(issues)


def _verify_benchmark_lock(
    campaign: dict[str, Any],
    lock: Any,
    repo_root: Path,
    *,
    context: RepositoryContext | None = None,
    verify_repository: bool,
) -> list[Issue]:
    """Verify a lock against campaign content and current protected inputs."""
    issues = validate_benchmark_lock(lock)
    campaign_issues = validate_campaign(campaign)
    issues.extend(campaign_issues)
    if issues or not isinstance(lock, dict):
        return sort_issues(issues)
    try:
        observed = context or observe_repository_context(
            repo_root,
            campaign["benchmark_commit_sha"],
            campaign["verifier_commit_sha"],
        )
        issues.extend(_context_issues(campaign, observed))
        current_bindings = _build_bindings(campaign, repo_root)
        if verify_repository:
            issues.extend(
                _binding_commit_issues(
                    repo_root, current_bindings, observed
                )
            )
    except LockingError as exc:
        return sort_issues(exc.issues)
    if issues:
        return sort_issues(issues)
    issues.extend(_declared_digest_issues(campaign, current_bindings))
    expected = _assemble_lock(
        campaign,
        current_bindings,
        context=observed,
        envelope=lock.get("envelope"),
    )

    comparisons = (
        ("campaign_id", "CAMPAIGN_ID_MISMATCH"),
        ("campaign_digest", "CAMPAIGN_CONTENT_MISMATCH"),
        ("repository_commit", "REPOSITORY_COMMIT_MISMATCH"),
        ("verifier_commit", "VERIFIER_COMMIT_MISMATCH"),
        ("release_identifier", "RELEASE_IDENTIFIER_MISMATCH"),
        ("declared_commands", "DECLARED_COMMANDS_MISMATCH"),
        ("declared_input_digests", "DECLARED_INPUT_DIGESTS_MISMATCH"),
    )
    for field, code in comparisons:
        if lock.get(field) != expected[field]:
            issues.append(
                issue(code, f"$.{field}", f"current campaign does not match locked {field}")
            )
    supplied_bindings = lock["bindings"]
    for group in sorted(expected["bindings"]):
        if supplied_bindings.get(group) != expected["bindings"][group]:
            issues.append(
                issue(
                    _BINDING_MISMATCH_CODES[group],
                    f"$.bindings.{group}",
                    f"current {group} inputs do not match the lock",
                )
            )
    if lock.get("lock_digest") != expected["lock_digest"]:
        issues.append(
            issue(
                "LOCK_CURRENT_STATE_MISMATCH",
                "$.lock_digest",
                "current campaign or protected inputs do not reproduce the lock digest",
            )
        )

    reference = campaign.get("benchmark_lock")
    if isinstance(reference, dict):
        if reference.get("lock_digest") != lock.get("lock_digest"):
            issues.append(
                issue(
                    "CAMPAIGN_LOCK_REFERENCE_MISMATCH",
                    "$.benchmark_lock.lock_digest",
                    "campaign lock reference does not identify the supplied lock",
                )
            )
        if reference.get("path") and not str(reference["path"]).endswith(".json"):
            issues.append(
                issue(
                    "CAMPAIGN_LOCK_REFERENCE_INVALID",
                    "$.benchmark_lock.path",
                    "benchmark lock reference must identify a JSON file",
                )
            )
    return sort_issues(issues)


def verify_benchmark_lock(
    campaign: dict[str, Any],
    lock: Any,
    repo_root: Path,
) -> list[Issue]:
    """Verify a governed lock against Git-observed repository provenance."""
    return _verify_benchmark_lock(
        campaign,
        lock,
        repo_root,
        context=None,
        verify_repository=True,
    )


def _verify_benchmark_lock_content(
    campaign: dict[str, Any],
    lock: Any,
    repo_root: Path,
    *,
    context: RepositoryContext,
) -> list[Issue]:
    """Verify deterministic test content without making a provenance claim."""
    return _verify_benchmark_lock(
        campaign,
        lock,
        repo_root,
        context=context,
        verify_repository=False,
    )


def approved_output_path(output: Path, approved_root: Path) -> Path:
    """Resolve an output path and prove it remains inside its approved root."""
    root = approved_root.resolve()
    target = output if output.is_absolute() else root / output
    target = target.resolve(strict=False)
    try:
        relative_target = target.relative_to(root)
    except ValueError as exc:
        raise LockingError(
            [
                issue(
                    "OUTPUT_PATH_NOT_APPROVED",
                    "$.output",
                    f"output must remain under {root.as_posix()}",
                )
            ]
        ) from exc
    portable_issues = validate_repo_relative_path(
        relative_target.as_posix(), "$.output"
    )
    if portable_issues:
        raise LockingError(
            [
                issue(
                    "OUTPUT_PATH_INVALID",
                    "$.output",
                    portable_issues[0]["message"],
                )
            ]
        )
    if target.suffix.lower() != ".json":
        raise LockingError(
            [issue("OUTPUT_PATH_INVALID", "$.output", "lock output must be a .json file")]
        )
    return target


def write_lock_atomic(lock: dict[str, Any], output: Path, approved_root: Path) -> Path:
    """Atomically create a lock beneath an approved root without overwriting."""
    target = approved_output_path(output, approved_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise LockingError(
            [issue("OUTPUT_EXISTS", "$.output", f"refusing to overwrite {target.as_posix()}")]
        )
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = None
            handle.write(canonical_json(lock))
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-linking publishes a fully written file and fails if target exists.
        os.link(temporary, target)
    except FileExistsError as exc:
        raise LockingError(
            [issue("OUTPUT_EXISTS", "$.output", f"refusing to overwrite {target.as_posix()}")]
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return target
