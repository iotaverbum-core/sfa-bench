"""Benchmark-lock and implementation-binding checks for alpha.2 capture."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sfa_bench.campaigns.locking import verify_benchmark_lock
from sfa_bench.campaigns.protocol import validate_campaign

from .canonical import CaptureError, sha256_bytes, validate_repo_relative_path


REQUIRED_ALPHA2_BINDINGS = frozenset(
    {
        "campaign_capture_cli.py",
        "campaign_capture_check.py",
        "sfa_bench/campaigns/capture/__init__.py",
        "sfa_bench/campaigns/capture/adapters.py",
        "sfa_bench/campaigns/capture/authorization.py",
        "sfa_bench/campaigns/capture/canonical.py",
        "sfa_bench/campaigns/capture/context.py",
        "sfa_bench/campaigns/capture/judgment.py",
        "sfa_bench/campaigns/capture/lifecycle.py",
        "sfa_bench/campaigns/capture/review.py",
        "sfa_bench/campaigns/capture/run.py",
        "sfa_bench/campaigns/capture/storage.py",
        "campaigns/alpha2/schemas/capture-manifest.schema.json",
        "campaigns/alpha2/schemas/execution-authorization.schema.json",
        "campaigns/alpha2/schemas/judgment.schema.json",
        "campaigns/alpha2/schemas/lifecycle-event.schema.json",
        "campaigns/alpha2/schemas/review-bundle.schema.json",
    }
)


def lock_binding_map(lock: Any) -> dict[str, str]:
    if not isinstance(lock, dict) or not isinstance(lock.get("bindings"), dict):
        raise CaptureError("INVALID_BENCHMARK_LOCK", "lock has no binding map")
    result: dict[str, str] = {}
    for entries in lock["bindings"].values():
        if not isinstance(entries, list):
            raise CaptureError("INVALID_BENCHMARK_LOCK", "lock binding group is malformed")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
                raise CaptureError("INVALID_BENCHMARK_LOCK", "lock binding entry is malformed")
            path = entry.get("path")
            digest = entry.get("sha256")
            if not isinstance(path, str) or not isinstance(digest, str):
                raise CaptureError("INVALID_BENCHMARK_LOCK", "lock binding values are malformed")
            if path in result and result[path] != digest:
                raise CaptureError("CONTRADICTORY_LOCK_BINDING", "path has conflicting lock digests", path)
            result[path] = digest
    return result


def verify_governed_context(
    campaign: Any,
    lock: Any,
    repo_root: Path,
) -> dict[str, str]:
    campaign_issues = validate_campaign(campaign)
    if campaign_issues:
        first = campaign_issues[0]
        raise CaptureError(first.code, first.message, first.path)
    lock_issues = verify_benchmark_lock(campaign, lock, repo_root)
    if lock_issues:
        first = lock_issues[0]
        raise CaptureError(first.code, first.message, first.path)
    bindings = lock_binding_map(lock)
    missing = sorted(REQUIRED_ALPHA2_BINDINGS - set(bindings))
    if missing:
        raise CaptureError(
            "CAPTURE_IMPLEMENTATION_UNBOUND",
            "benchmark lock does not bind the complete alpha.2 capture core: " + ", ".join(missing),
            "$.bindings",
        )
    for path in sorted(REQUIRED_ALPHA2_BINDINGS):
        target = repo_root.joinpath(*path.split("/"))
        if not target.is_file() or sha256_bytes(target.read_bytes()) != bindings[path]:
            raise CaptureError(
                "CAPTURE_IMPLEMENTATION_BINDING_MISMATCH",
                "alpha.2 implementation bytes do not match the benchmark lock",
                path,
            )
    return bindings


def require_bound_reference(
    lock: Any,
    reference: Any,
    path: str,
) -> tuple[str, str]:
    relative = validate_repo_relative_path(reference, path)
    bindings = lock_binding_map(lock)
    digest = bindings.get(relative)
    if digest is None:
        raise CaptureError(
            "REFERENCE_NOT_LOCK_BOUND",
            "reference is not an exact file binding in the benchmark lock",
            path,
        )
    return relative, digest
