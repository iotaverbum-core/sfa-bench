"""Deterministic, secret-free, explicitly unratified human-review bundle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import CaptureError, assert_secret_free, require_exact_fields, sha256_value, validate_timestamp
from .judgment import verify_judgment
from .lifecycle import append_transition, verify_ledger
from .run import verify_run
from .storage import read_record, write_record


REVIEW_BUNDLE_SCHEMA = "sfa_bench.campaign_capture.review_bundle.v1"
REVIEW_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "execution_id",
        "preregistration",
        "benchmark_lock",
        "execution_authorization",
        "lifecycle_ledger",
        "raw_evidence_hashes",
        "capture_manifest",
        "adapter_provenance",
        "integrity_verification_report",
        "deterministic_judgment",
        "claims_and_limitations",
        "unresolved_warnings",
        "lineage_references",
        "ratification_status",
        "packaging_is_approval",
        "raw_bodies_included",
        "bundle_sha256",
    }
)


def _bundle_digest(bundle: dict[str, Any]) -> str:
    content = dict(bundle)
    content.pop("bundle_sha256", None)
    return sha256_value(content)


def build_review_bundle(
    run_dir: Path,
    *,
    repo_root: Path,
    observed_at: str,
) -> dict[str, Any]:
    """Package verified hashes and public artifacts; never package raw bodies."""
    validate_timestamp(observed_at, "$.observed_at")
    target = run_dir / "review-bundle.json"
    if target.exists():
        return verify_review_bundle(run_dir, repo_root=repo_root)
    integrity = verify_run(run_dir, repo_root=repo_root)
    state = integrity["lifecycle_state"]
    judgment = None
    if state == "judged":
        judgment = verify_judgment(run_dir, repo_root=repo_root)
    elif state == "sealed":
        manifest = read_record(run_dir / "capture-manifest.json")
        if manifest["capture_state"] != "aborted":
            raise CaptureError(
                "REVIEW_REQUIRES_JUDGMENT",
                "completed sealed capture must be judged before review packaging",
            )
    else:
        raise CaptureError("REVIEW_NOT_READY", "run is not ready for human review")
    append_transition(
        run_dir,
        "review_required",
        observed_at=observed_at,
        payload={"ratification_status": "unratified", "packaging_is_approval": False},
    )
    integrity = verify_run(run_dir, repo_root=repo_root)
    run = read_record(run_dir / "run.json")
    campaign = read_record(run_dir / "preregistration.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    authorization = read_record(run_dir / "execution-authorization.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    ledger = verify_ledger(run_dir)
    warnings = sorted(set(integrity["warnings"]) | set(manifest["warnings"]))
    bundle: dict[str, Any] = {
        "schema_version": REVIEW_BUNDLE_SCHEMA,
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "preregistration": campaign,
        "benchmark_lock": lock,
        "execution_authorization": authorization,
        "lifecycle_ledger": {
            "events": list(ledger.events),
            "root_sha256": ledger.root_sha256,
            "state": ledger.state,
        },
        "raw_evidence_hashes": manifest["raw_evidence_hashes"],
        "capture_manifest": manifest,
        "adapter_provenance": {
            **run["adapter"],
            "source_class": "adapter_declared",
            "identity_verified": False,
        },
        "integrity_verification_report": integrity,
        "deterministic_judgment": judgment,
        "claims_and_limitations": {
            "supported": [
                "adapter-boundary bytes are preserved by exact SHA-256 and byte length",
                "covered integrity and lifecycle checks are deterministic and offline",
                "judgment metadata projection is empty",
            ],
            "unsupported": [
                "live provider success or provider/model identity",
                "provider rankings or comparative quality",
                "regulatory or legal conformity",
                "semantic completeness or human-free evaluation",
                "autonomous authority, ratification, promotion, publication, or release",
            ],
            "capture_boundary_qualification": (
                "Exact means bytes observed by the named adapter at the declared capture boundary; "
                "it does not prove provider-side origin or upstream wire fidelity."
            ),
        },
        "unresolved_warnings": warnings,
        "lineage_references": {"predecessor": None, "successor": None},
        "ratification_status": "unratified",
        "packaging_is_approval": False,
        "raw_bodies_included": False,
    }
    bundle["bundle_sha256"] = _bundle_digest(bundle)
    assert_secret_free(bundle)
    write_record(target, bundle)
    return bundle


def verify_review_bundle(run_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    integrity = verify_run(run_dir, repo_root=repo_root)
    if integrity["lifecycle_state"] != "review_required":
        raise CaptureError("REVIEW_STATE_MISMATCH", "review bundle requires review_required state")
    bundle = read_record(run_dir / "review-bundle.json")
    require_exact_fields(bundle, REVIEW_BUNDLE_FIELDS)
    if bundle["schema_version"] != REVIEW_BUNDLE_SCHEMA:
        raise CaptureError("UNSUPPORTED_REVIEW_BUNDLE", "unsupported review bundle schema")
    if bundle["bundle_sha256"] != _bundle_digest(bundle):
        raise CaptureError("REVIEW_BUNDLE_DIGEST_MISMATCH", "review bundle was modified")
    if bundle["ratification_status"] != "unratified" or bundle["packaging_is_approval"] is not False:
        raise CaptureError("REVIEW_BUNDLE_AUTHORITY_CLAIM", "review packaging cannot grant authority")
    if bundle["raw_bodies_included"] is not False:
        raise CaptureError("RAW_BODY_PUBLICATION_FORBIDDEN", "review bundle must exclude raw bodies")
    run = read_record(run_dir / "run.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    ledger = verify_ledger(run_dir)
    if (
        bundle["campaign_id"] != run["campaign_id"]
        or bundle["execution_id"] != run["execution_id"]
        or bundle["capture_manifest"] != manifest
        or bundle["lifecycle_ledger"]["root_sha256"] != ledger.root_sha256
        or bundle["lifecycle_ledger"]["state"] != "review_required"
    ):
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "review bundle binds different evidence")
    if (run_dir / "judgment.json").is_file():
        judgment = verify_judgment(run_dir, repo_root=repo_root)
        if bundle["deterministic_judgment"] != judgment:
            raise CaptureError("REVIEW_JUDGMENT_MISMATCH", "bundle judgment differs from sealed judgment")
    elif bundle["deterministic_judgment"] is not None:
        raise CaptureError("UNSEALED_REVIEW_JUDGMENT", "bundle contains an unsealed judgment")
    assert_secret_free(bundle)
    return bundle
