"""Human disposition records for verified campaign review bundles.

This module deliberately writes companion artifacts outside the immutable capture
run. A ratification accepts or disputes one sealed deterministic judgment only;
it never endorses a provider or model, promotes a candidate, publishes evidence,
or creates a release.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sfa_bench.campaigns.capture.canonical import (
    CaptureError,
    assert_secret_free,
    canonical_bytes,
    require_exact_fields,
    require_object,
    sha256_bytes,
    sha256_value,
    strict_json_loads,
    validate_safe_id,
    validate_timestamp,
    write_exclusive_bytes,
    write_exclusive_json,
)
from sfa_bench.campaigns.capture.judgment import JUDGMENT_FIELDS, JUDGMENT_SCHEMA
from sfa_bench.campaigns.capture.review import REVIEW_BUNDLE_FIELDS, REVIEW_BUNDLE_SCHEMA


RATIFICATION_PACKET_SCHEMA = "sfa_bench.campaign_capture.ratification_packet.v1"
RATIFICATION_LINEAGE_SCHEMA = "sfa_bench.campaign_capture.ratification_lineage.v1"
ACTIONS = frozenset({"prepare", "ratify", "reject", "halt"})
ACTION_OUTCOME = {
    "prepare": "RATIFICATION_READY",
    "ratify": "RATIFIED",
    "reject": "REJECTED_BY_HUMAN",
    "halt": "HALTED_BY_HUMAN",
}
ACTION_DISPOSITION = {
    "prepare": "pending",
    "ratify": "accepted",
    "reject": "disputed",
    "halt": "deferred",
}
PACKET_FIELDS = frozenset(
    {
        "schema_version",
        "ratification_id",
        "created_at",
        "source_review_bundle",
        "evidence_binding",
        "deterministic_result",
        "human_action",
        "authority_scope",
        "outcome",
        "ratification_packet_sha256",
    }
)
LINEAGE_FIELDS = frozenset(
    {
        "schema_version",
        "lineage_record_id",
        "created_at",
        "ratification_packet_sha256",
        "source_review_bundle_sha256",
        "campaign_id",
        "execution_id",
        "human_action",
        "ratification_outcome",
        "outcome",
        "lineage_record_sha256",
    }
)


def _require_string(value: Any, path: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CaptureError("INVALID_RATIFICATION_FIELD", "value must be a non-empty bounded string", path)
    return value.strip()


def _require_sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise CaptureError("INVALID_DIGEST", "value must be a lowercase SHA-256 digest", path)
    try:
        int(value, 16)
    except ValueError as exc:
        raise CaptureError("INVALID_DIGEST", "value must be a lowercase SHA-256 digest", path) from exc
    if value != value.lower():
        raise CaptureError("INVALID_DIGEST", "value must be a lowercase SHA-256 digest", path)
    return value


def _bundle_digest(bundle: dict[str, Any]) -> str:
    content = dict(bundle)
    content.pop("bundle_sha256", None)
    return sha256_value(content)


def _judgment_digest(judgment: dict[str, Any]) -> str:
    content = dict(judgment)
    content.pop("judgment_sha256", None)
    return sha256_value(content)


def _judgment_content_digest(judgment: dict[str, Any]) -> str:
    return sha256_value(
        {
            key: value
            for key, value in judgment.items()
            if key not in {"judged_at", "judgment_content_sha256", "judgment_sha256"}
        }
    )


def _integrity_digest(report: dict[str, Any]) -> str:
    content = dict(report)
    content.pop("integrity_report_sha256", None)
    return sha256_value(content)


def _record_digest(record: dict[str, Any], field: str) -> str:
    content = dict(record)
    content.pop(field, None)
    return sha256_value(content)


def validate_review_bundle_bytes(data: bytes) -> dict[str, Any]:
    """Validate a secret-free review bundle without requiring the private run."""
    bundle = require_object(strict_json_loads(data))
    if canonical_bytes(bundle) != data:
        raise CaptureError(
            "NONCANONICAL_REVIEW_BUNDLE",
            "review bundle must retain its canonical stored bytes",
        )
    require_exact_fields(bundle, REVIEW_BUNDLE_FIELDS)
    if bundle.get("schema_version") != REVIEW_BUNDLE_SCHEMA:
        raise CaptureError("UNSUPPORTED_REVIEW_BUNDLE", "unsupported review bundle schema")
    if bundle.get("bundle_sha256") != _bundle_digest(bundle):
        raise CaptureError("REVIEW_BUNDLE_DIGEST_MISMATCH", "review bundle was modified")
    if bundle.get("ratification_status") != "unratified":
        raise CaptureError("SOURCE_ALREADY_DISPOSED", "source review bundle is not unratified")
    if bundle.get("packaging_is_approval") is not False:
        raise CaptureError("REVIEW_BUNDLE_AUTHORITY_CLAIM", "review packaging cannot grant authority")
    if bundle.get("raw_bodies_included") is not False:
        raise CaptureError("RAW_BODY_PUBLICATION_FORBIDDEN", "ratification requires a body-free review bundle")

    campaign_id = _require_string(bundle.get("campaign_id"), "$.campaign_id")
    execution_id = _require_string(bundle.get("execution_id"), "$.execution_id")

    lock = require_object(bundle.get("benchmark_lock"), "$.benchmark_lock")
    lock_digest = _require_sha(lock.get("lock_digest"), "$.benchmark_lock.lock_digest")
    verifier_commit = lock.get("verifier_commit")
    if not isinstance(verifier_commit, str) or len(verifier_commit) != 40:
        raise CaptureError("INVALID_COMMIT", "verifier commit must be a 40-character Git SHA", "$.benchmark_lock.verifier_commit")

    manifest = require_object(bundle.get("capture_manifest"), "$.capture_manifest")
    manifest_sha = _require_sha(manifest.get("manifest_sha256"), "$.capture_manifest.manifest_sha256")
    if manifest.get("campaign_id") != campaign_id or manifest.get("execution_id") != execution_id:
        raise CaptureError("RATIFICATION_SOURCE_BINDING_MISMATCH", "capture manifest identifies another run")
    if manifest.get("benchmark_lock_digest") != lock_digest:
        raise CaptureError("RATIFICATION_SOURCE_BINDING_MISMATCH", "capture manifest binds another lock")
    if manifest.get("capture_state") != "captured":
        raise CaptureError("RATIFICATION_REQUIRES_COMPLETED_CAPTURE", "only a completed captured run can be disposed")
    if manifest.get("ratification_status") != "unratified":
        raise CaptureError("SOURCE_ALREADY_DISPOSED", "capture manifest is not unratified")
    if bundle.get("raw_evidence_hashes") != manifest.get("raw_evidence_hashes"):
        raise CaptureError("RATIFICATION_SOURCE_BINDING_MISMATCH", "raw-evidence hashes differ from the manifest")

    judgment = require_object(bundle.get("deterministic_judgment"), "$.deterministic_judgment")
    require_exact_fields(judgment, JUDGMENT_FIELDS, "$.deterministic_judgment")
    if judgment.get("schema_version") != JUDGMENT_SCHEMA:
        raise CaptureError("UNSUPPORTED_JUDGMENT_SCHEMA", "unsupported judgment schema")
    if judgment.get("judgment_content_sha256") != _judgment_content_digest(judgment):
        raise CaptureError("JUDGMENT_CONTENT_MISMATCH", "judgment content identity changed")
    if judgment.get("judgment_sha256") != _judgment_digest(judgment):
        raise CaptureError("JUDGMENT_DIGEST_MISMATCH", "judgment artifact was modified")
    if judgment.get("ratification_status") != "unratified":
        raise CaptureError("SOURCE_ALREADY_DISPOSED", "deterministic judgment is not unratified")
    if judgment.get("provenance_class") != "derived_deterministic":
        raise CaptureError("INVALID_JUDGMENT_PROVENANCE", "judgment is not deterministic derived evidence")
    if (
        judgment.get("campaign_id") != campaign_id
        or judgment.get("execution_id") != execution_id
        or judgment.get("benchmark_lock_digest") != lock_digest
        or judgment.get("verifier_commit") != verifier_commit
        or judgment.get("capture_manifest_sha256") != manifest_sha
    ):
        raise CaptureError("RATIFICATION_SOURCE_BINDING_MISMATCH", "judgment binds different evidence")
    response_blob_sha = _require_sha(
        judgment.get("response_blob_sha256"),
        "$.deterministic_judgment.response_blob_sha256",
    )

    result = require_object(judgment.get("deterministic_result"), "$.deterministic_judgment.deterministic_result")
    verdict = _require_string(result.get("verdict"), "$.deterministic_judgment.deterministic_result.verdict")
    score = result.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise CaptureError("INVALID_DETERMINISTIC_RESULT", "judgment score must be numeric")
    failure_modes = result.get("detected_failure_modes")
    if not isinstance(failure_modes, list) or not all(isinstance(item, str) for item in failure_modes):
        raise CaptureError("INVALID_DETERMINISTIC_RESULT", "failure modes must be a string list")
    explanation = _require_string(
        result.get("explanation"),
        "$.deterministic_judgment.deterministic_result.explanation",
        maximum=2000,
    )

    integrity = require_object(bundle.get("integrity_verification_report"), "$.integrity_verification_report")
    integrity_sha = _require_sha(
        integrity.get("integrity_report_sha256"),
        "$.integrity_verification_report.integrity_report_sha256",
    )
    if integrity_sha != _integrity_digest(integrity):
        raise CaptureError("INTEGRITY_REPORT_DIGEST_MISMATCH", "integrity report was modified")
    ledger = require_object(bundle.get("lifecycle_ledger"), "$.lifecycle_ledger")
    if set(ledger) != {"events", "root_sha256", "state"}:
        raise CaptureError("INVALID_REVIEW_LEDGER", "review ledger shape is invalid")
    ledger_root = _require_sha(ledger.get("root_sha256"), "$.lifecycle_ledger.root_sha256")
    events = ledger.get("events")
    if not isinstance(events, list):
        raise CaptureError("INVALID_REVIEW_LEDGER", "review ledger events must be a list")
    if ledger.get("state") != "judged":
        raise CaptureError("RATIFICATION_REQUIRES_JUDGMENT", "review bundle predecessor state must be judged")
    if (
        integrity.get("status") != "verified"
        or integrity.get("campaign_id") != campaign_id
        or integrity.get("execution_id") != execution_id
        or integrity.get("benchmark_lock_digest") != lock_digest
        or integrity.get("capture_manifest_sha256") != manifest_sha
        or integrity.get("lifecycle_state") != ledger.get("state")
        or integrity.get("ledger_root") != ledger_root
        or integrity.get("ledger_events") != len(events)
        or integrity.get("ratification_status") != "unratified"
    ):
        raise CaptureError("RATIFICATION_SOURCE_BINDING_MISMATCH", "integrity report binds different evidence")

    assert_secret_free(bundle)
    return bundle


def read_validated_review_bundle(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    return validate_review_bundle_bytes(data), sha256_bytes(data)


def build_ratification_records(
    *,
    bundle: dict[str, Any],
    source_file_sha256: str,
    ratification_id: str,
    action: str,
    reviewer: str,
    rationale: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build sealed packet and lineage records from one validated review bundle."""
    validate_safe_id(ratification_id, "$.ratification_id")
    if action not in ACTIONS:
        raise CaptureError("INVALID_RATIFICATION_ACTION", "action must be prepare, ratify, reject, or halt")
    reviewer = _require_string(reviewer, "$.reviewer")
    validate_timestamp(created_at, "$.created_at")
    if not isinstance(rationale, str) or len(rationale) > 2000:
        raise CaptureError("INVALID_RATIFICATION_RATIONALE", "rationale must be at most 2000 characters")
    rationale = rationale.strip()
    if action != "prepare" and not rationale:
        raise CaptureError("RATIFICATION_RATIONALE_REQUIRED", "explicit human actions require a rationale")

    judgment = bundle["deterministic_judgment"]
    result = judgment["deterministic_result"]
    integrity = bundle["integrity_verification_report"]
    packet: dict[str, Any] = {
        "schema_version": RATIFICATION_PACKET_SCHEMA,
        "ratification_id": ratification_id,
        "created_at": created_at,
        "source_review_bundle": {
            "filename": "review-bundle.json",
            "file_sha256": _require_sha(source_file_sha256, "$.source_review_bundle.file_sha256"),
            "bundle_sha256": bundle["bundle_sha256"],
            "campaign_id": bundle["campaign_id"],
            "execution_id": bundle["execution_id"],
        },
        "evidence_binding": {
            "benchmark_lock_digest": bundle["benchmark_lock"]["lock_digest"],
            "capture_manifest_sha256": bundle["capture_manifest"]["manifest_sha256"],
            "judgment_sha256": judgment["judgment_sha256"],
            "response_blob_sha256": judgment["response_blob_sha256"],
            "integrity_report_sha256": integrity["integrity_report_sha256"],
            "ledger_root": bundle["lifecycle_ledger"]["root_sha256"],
        },
        "deterministic_result": {
            "verdict": result["verdict"],
            "score": result["score"],
            "detected_failure_modes": list(result["detected_failure_modes"]),
            "explanation": result["explanation"],
        },
        "human_action": {
            "action": action,
            "disposition": ACTION_DISPOSITION[action],
            "reviewer": reviewer,
            "rationale": rationale,
            "explicit": action in {"ratify", "reject", "halt"},
        },
        "authority_scope": {
            "accepts_deterministic_judgment": action == "ratify",
            "model_endorsement": False,
            "provider_identity_attestation": False,
            "promotion": False,
            "publication": False,
            "release": False,
            "regulatory_or_legal_approval": False,
        },
        "outcome": {
            "class": ACTION_OUTCOME[action],
            "lineage_recorded": True,
            "auto_promoted": False,
            "reason": {
                "prepare": "review packet prepared; no human disposition recorded",
                "ratify": "human accepted the sealed deterministic judgment for this execution",
                "reject": "human disputed the sealed deterministic judgment for this execution",
                "halt": "human deferred disposition and halted this evidence workflow",
            }[action],
        },
    }
    packet["ratification_packet_sha256"] = _record_digest(packet, "ratification_packet_sha256")

    lineage: dict[str, Any] = {
        "schema_version": RATIFICATION_LINEAGE_SCHEMA,
        "lineage_record_id": f"lineage-{ratification_id}",
        "created_at": created_at,
        "ratification_packet_sha256": packet["ratification_packet_sha256"],
        "source_review_bundle_sha256": bundle["bundle_sha256"],
        "campaign_id": bundle["campaign_id"],
        "execution_id": bundle["execution_id"],
        "human_action": dict(packet["human_action"]),
        "ratification_outcome": packet["outcome"]["class"],
        "outcome": {
            "class": "LINEAGE_RECORDED",
            "promotion_effect": "none",
            "publication_effect": "none",
            "release_effect": "none",
            "reason": "human decision lineage recorded without mutating the capture run",
        },
    }
    lineage["lineage_record_sha256"] = _record_digest(lineage, "lineage_record_sha256")
    assert_secret_free(packet)
    assert_secret_free(lineage)
    return packet, lineage


def verify_ratification_packet(packet: dict[str, Any]) -> dict[str, Any]:
    require_exact_fields(packet, PACKET_FIELDS)
    if packet.get("schema_version") != RATIFICATION_PACKET_SCHEMA:
        raise CaptureError("UNSUPPORTED_RATIFICATION_PACKET", "unsupported ratification packet schema")
    if packet.get("ratification_packet_sha256") != _record_digest(packet, "ratification_packet_sha256"):
        raise CaptureError("RATIFICATION_PACKET_DIGEST_MISMATCH", "ratification packet was modified")
    action = packet.get("human_action", {}).get("action")
    if action not in ACTIONS or packet.get("outcome", {}).get("class") != ACTION_OUTCOME[action]:
        raise CaptureError("RATIFICATION_OUTCOME_MISMATCH", "ratification action and outcome differ")
    scope = packet.get("authority_scope")
    expected_acceptance = action == "ratify"
    if not isinstance(scope, dict) or scope.get("accepts_deterministic_judgment") is not expected_acceptance:
        raise CaptureError("RATIFICATION_SCOPE_MISMATCH", "judgment acceptance scope is inconsistent")
    for field in (
        "model_endorsement",
        "provider_identity_attestation",
        "promotion",
        "publication",
        "release",
        "regulatory_or_legal_approval",
    ):
        if scope.get(field) is not False:
            raise CaptureError("RATIFICATION_AUTHORITY_OVERREACH", "ratification claims forbidden authority", f"$.authority_scope.{field}")
    assert_secret_free(packet)
    return packet


def verify_lineage_record(lineage: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    require_exact_fields(lineage, LINEAGE_FIELDS)
    if lineage.get("schema_version") != RATIFICATION_LINEAGE_SCHEMA:
        raise CaptureError("UNSUPPORTED_RATIFICATION_LINEAGE", "unsupported lineage schema")
    if lineage.get("lineage_record_sha256") != _record_digest(lineage, "lineage_record_sha256"):
        raise CaptureError("RATIFICATION_LINEAGE_DIGEST_MISMATCH", "lineage record was modified")
    if (
        lineage.get("ratification_packet_sha256") != packet.get("ratification_packet_sha256")
        or lineage.get("source_review_bundle_sha256") != packet.get("source_review_bundle", {}).get("bundle_sha256")
        or lineage.get("campaign_id") != packet.get("source_review_bundle", {}).get("campaign_id")
        or lineage.get("execution_id") != packet.get("source_review_bundle", {}).get("execution_id")
        or lineage.get("human_action") != packet.get("human_action")
        or lineage.get("ratification_outcome") != packet.get("outcome", {}).get("class")
    ):
        raise CaptureError("RATIFICATION_LINEAGE_BINDING_MISMATCH", "lineage binds another packet")
    outcome = lineage.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("class") != "LINEAGE_RECORDED":
        raise CaptureError("RATIFICATION_LINEAGE_OUTCOME_MISMATCH", "lineage outcome is invalid")
    for field in ("promotion_effect", "publication_effect", "release_effect"):
        if outcome.get(field) != "none":
            raise CaptureError("RATIFICATION_AUTHORITY_OVERREACH", "lineage claims forbidden effect", f"$.outcome.{field}")
    assert_secret_free(lineage)
    return lineage


def packet_markdown(packet: dict[str, Any], lineage: dict[str, Any]) -> str:
    result = packet["deterministic_result"]
    failures = ", ".join(result["detected_failure_modes"]) or "none"
    return (
        "# Campaign Evidence Ratification\n\n"
        f"- Ratification ID: `{packet['ratification_id']}`\n"
        f"- Outcome: `{packet['outcome']['class']}`\n"
        f"- Campaign: `{packet['source_review_bundle']['campaign_id']}`\n"
        f"- Execution: `{packet['source_review_bundle']['execution_id']}`\n"
        f"- Review bundle: `{packet['source_review_bundle']['bundle_sha256']}`\n"
        f"- Judgment: `{packet['evidence_binding']['judgment_sha256']}`\n"
        f"- Verdict: `{result['verdict']}`\n"
        f"- Score: `{result['score']}`\n"
        f"- Failure modes: `{failures}`\n"
        f"- Reviewer: `{packet['human_action']['reviewer']}`\n"
        f"- Human action: `{packet['human_action']['action']}`\n"
        f"- Rationale: {packet['human_action']['rationale'] or '_none_'}\n\n"
        "## Authority Boundary\n\n"
        "This record accepts or disputes only the sealed deterministic judgment for the named execution. "
        "It does not endorse the model, attest provider identity, promote a candidate, publish evidence, "
        "create a release, or grant legal or regulatory approval.\n\n"
        "## Lineage\n\n"
        f"- Lineage record: `{lineage['lineage_record_id']}`\n"
        f"- Lineage digest: `{lineage['lineage_record_sha256']}`\n"
        "- Capture run mutated: `false`\n"
    )


def write_ratification_records(
    output_root: Path,
    packet: dict[str, Any],
    lineage: dict[str, Any],
) -> Path:
    """Publish one immutable ratification directory and verify its bytes."""
    verify_ratification_packet(packet)
    verify_lineage_record(lineage, packet)
    target = output_root / packet["ratification_id"]
    target.mkdir(parents=True, exist_ok=False)
    write_exclusive_json(target / "ratification-packet.json", packet)
    write_exclusive_json(target / "lineage-record.json", lineage)
    write_exclusive_bytes(target / "ratification-packet.md", packet_markdown(packet, lineage).encode("utf-8"))
    stored_packet = require_object(strict_json_loads((target / "ratification-packet.json").read_bytes()))
    stored_lineage = require_object(strict_json_loads((target / "lineage-record.json").read_bytes()))
    verify_ratification_packet(stored_packet)
    verify_lineage_record(stored_lineage, stored_packet)
    return target
