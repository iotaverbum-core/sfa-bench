"""Deterministic, secret-free, explicitly unratified human-review bundle."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import CaptureError, assert_secret_free, require_exact_fields, sha256_value, validate_timestamp
from .judgment import _validate_judgment_artifact, verify_judgment
from .lifecycle import append_transition, verify_ledger
from .run import _verify_run_core, verify_run
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


def _authorization_projection(authorization: dict[str, Any]) -> dict[str, Any]:
    """Publish the execution authorization without declared operator identity."""
    return {
        "schema_version": authorization["schema_version"],
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["authorization_digest"],
        "campaign_id": authorization["campaign_id"],
        "benchmark_lock_digest": authorization["benchmark_lock_digest"],
        "benchmark_commit": authorization["benchmark_commit"],
        "verifier_commit": authorization["verifier_commit"],
        "release_identifier": authorization["release_identifier"],
        "execution_id": authorization["execution_id"],
        "adapter": authorization["adapter"],
        "request": authorization["request"],
        "retry_policy": authorization["retry_policy"],
        "operator_declaration": {
            "identity_redacted": True,
            "authority_type": authorization["operator_declaration"]["authority_type"],
            "authorization_scope": authorization["operator_declaration"]["authorization_scope"],
        },
        "issued_at": authorization["issued_at"],
        "ratification_status": "unratified",
        "automatic_actions": authorization["automatic_actions"],
    }


def build_review_bundle(
    run_dir: Path,
    *,
    repo_root: Path,
    observed_at: str,
) -> dict[str, Any]:
    """Package verified hashes and public artifacts; never package raw bodies."""
    validate_timestamp(observed_at, "$.observed_at")
    target = run_dir / "review-bundle.json"
    ledger = verify_ledger(run_dir)
    if target.is_file():
        if ledger.state == "review_required":
            return verify_review_bundle(run_dir, repo_root=repo_root)
        if ledger.state not in {"sealed", "judged"}:
            raise CaptureError("REVIEW_NOT_READY", "stored review bundle is not reconcilable")
        integrity = _verify_run_core(run_dir, repo_root=repo_root, allow_uncommitted="bundle")
        bundle = _validate_review_bundle_artifact(
            run_dir,
            repo_root=repo_root,
            integrity=integrity,
            require_event=False,
        )
        append_transition(
            run_dir,
            "review_required",
            observed_at=observed_at,
            payload={
                "bundle_sha256": bundle["bundle_sha256"],
                "ratification_status": "unratified",
                "packaging_is_approval": False,
            },
        )
        return bundle
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
    run = read_record(run_dir / "run.json")
    campaign = read_record(run_dir / "preregistration.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    authorization = read_record(run_dir / "execution-authorization.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    warnings = sorted(set(integrity["warnings"]) | set(manifest["warnings"]))
    bundle: dict[str, Any] = {
        "schema_version": REVIEW_BUNDLE_SCHEMA,
        "campaign_id": run["campaign_id"],
        "execution_id": run["execution_id"],
        "preregistration": campaign,
        "benchmark_lock": lock,
        "execution_authorization": _authorization_projection(authorization),
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
                "global execution-ID uniqueness across independently configured capture roots",
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
    append_transition(
        run_dir,
        "review_required",
        observed_at=observed_at,
        payload={
            "bundle_sha256": bundle["bundle_sha256"],
            "ratification_status": "unratified",
            "packaging_is_approval": False,
        },
    )
    return bundle


def _validate_review_bundle_artifact(
    run_dir: Path,
    *,
    repo_root: Path,
    integrity: dict[str, Any],
    require_event: bool,
) -> dict[str, Any]:
    if require_event and integrity["lifecycle_state"] != "review_required":
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
    campaign = read_record(run_dir / "preregistration.json")
    lock = read_record(run_dir / "benchmark-lock.json")
    authorization = read_record(run_dir / "execution-authorization.json")
    manifest = read_record(run_dir / "capture-manifest.json")
    ledger = verify_ledger(run_dir)
    if (
        bundle["campaign_id"] != run["campaign_id"]
        or bundle["execution_id"] != run["execution_id"]
        or bundle["preregistration"] != campaign
        or bundle["benchmark_lock"] != lock
        or bundle["execution_authorization"] != _authorization_projection(authorization)
        or bundle["capture_manifest"] != manifest
        or bundle["raw_evidence_hashes"] != manifest["raw_evidence_hashes"]
        or bundle["adapter_provenance"] != {
            **run["adapter"],
            "source_class": "adapter_declared",
            "identity_verified": False,
        }
    ):
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "review bundle binds different evidence")
    bundled_ledger = bundle["lifecycle_ledger"]
    if not isinstance(bundled_ledger, dict) or set(bundled_ledger) != {"events", "root_sha256", "state"}:
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "bundled ledger shape is invalid")
    review_events = [
        event for event in ledger.events if event["to_state"] == "review_required" and event["transition"]
    ]
    if require_event:
        expected_payload = {
            "bundle_sha256": bundle["bundle_sha256"],
            "ratification_status": "unratified",
            "packaging_is_approval": False,
        }
        if (
            len(review_events) != 1
            or review_events[0]["payload"] != expected_payload
            or review_events[0]["previous_event_sha256"] != bundled_ledger["root_sha256"]
            or review_events[0]["from_state"] != bundled_ledger["state"]
            or list(ledger.events[:-1]) != bundled_ledger["events"]
        ):
            raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "review event does not bind the bundle")
    elif (
        review_events
        or list(ledger.events) != bundled_ledger["events"]
        or ledger.root_sha256 != bundled_ledger["root_sha256"]
        or ledger.state != bundled_ledger["state"]
    ):
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "uncommitted bundle binds another ledger")
    if bundled_ledger["state"] not in {"sealed", "judged"}:
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "bundle predecessor state is invalid")
    report = bundle["integrity_verification_report"]
    if not isinstance(report, dict):
        raise CaptureError("REVIEW_INTEGRITY_REPORT_MISMATCH", "bundled integrity report is invalid")
    report_content = dict(report)
    report_digest = report_content.pop("integrity_report_sha256", None)
    if (
        report_digest != sha256_value(report_content)
        or report.get("status") != "verified"
        or report.get("campaign_id") != run["campaign_id"]
        or report.get("execution_id") != run["execution_id"]
        or report.get("lifecycle_state") != bundled_ledger["state"]
        or report.get("ledger_root") != bundled_ledger["root_sha256"]
        or report.get("ledger_events") != len(bundled_ledger["events"])
        or report.get("capture_manifest_sha256") != manifest["manifest_sha256"]
    ):
        raise CaptureError("REVIEW_INTEGRITY_REPORT_MISMATCH", "bundled integrity report does not reproduce")
    expected_warnings = sorted(set(report["warnings"]) | set(manifest["warnings"]))
    if (
        bundle["unresolved_warnings"] != expected_warnings
        or bundle["lineage_references"] != {"predecessor": None, "successor": None}
    ):
        raise CaptureError("REVIEW_BUNDLE_BINDING_MISMATCH", "bundle warnings or lineage differ from source")
    if (run_dir / "judgment.json").is_file():
        judgment = _validate_judgment_artifact(
            run_dir,
            repo_root=repo_root,
            integrity=integrity,
            require_event=True,
        )
        if bundle["deterministic_judgment"] != judgment:
            raise CaptureError("REVIEW_JUDGMENT_MISMATCH", "bundle judgment differs from sealed judgment")
    elif bundle["deterministic_judgment"] is not None:
        raise CaptureError("UNSEALED_REVIEW_JUDGMENT", "bundle contains an unsealed judgment")
    elif manifest["capture_state"] != "aborted":
        raise CaptureError("REVIEW_REQUIRES_JUDGMENT", "completed capture cannot skip judgment")
    assert_secret_free(bundle)
    return bundle


def verify_review_bundle(run_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    integrity = _verify_run_core(run_dir, repo_root=repo_root)
    return _validate_review_bundle_artifact(
        run_dir,
        repo_root=repo_root,
        integrity=integrity,
        require_event=True,
    )
