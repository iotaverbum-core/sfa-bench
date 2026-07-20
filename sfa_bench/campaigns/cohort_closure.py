"""Hash-bound closure records for completed, ratified campaign cohorts.

A closure is a mechanical companion record. It validates already-sealed review
bundles and ratification lineage, records descriptive outcomes, and never mutates
source evidence or grants ranking, promotion, publication, release, or legal
authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
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
from sfa_bench.campaigns.ratification import (
    read_validated_review_bundle,
    verify_lineage_record,
    verify_ratification_packet,
)

CLOSURE_SPEC_SCHEMA = "sfa_bench.campaign_capture.cohort_closure_spec.v1"
CLOSURE_RECORD_SCHEMA = "sfa_bench.campaign_capture.cohort_closure.v1"
CLOSURE_LINEAGE_SCHEMA = "sfa_bench.campaign_capture.cohort_closure_lineage.v1"
SHARED_GROUPS = (
    "cases",
    "rules",
    "taxonomy",
    "normalizer",
    "system_prompt",
    "user_prompt_or_case_set",
)
AUTHORITY_FIELDS = frozenset(
    {
        "model_endorsement",
        "provider_identity_attestation",
        "ranking",
        "promotion",
        "publication",
        "release",
        "regulatory_or_legal_approval",
    }
)
SPEC_FIELDS = frozenset(
    {
        "schema_version",
        "closure_id",
        "cohort_id",
        "classification",
        "protocol_reference",
        "members",
        "interpretation_limits",
        "authority",
    }
)
MEMBER_FIELDS = frozenset(
    {
        "declared_model_label",
        "campaign_id",
        "execution_id",
        "ratification_id",
        "requires_protocol_binding",
        "source_bundle_sha256",
        "judgment_sha256",
        "ratification_packet_sha256",
        "lineage_record_sha256",
        "verdict",
        "score",
        "detected_failure_modes",
    }
)
RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "closure_id",
        "created_at",
        "closed_by",
        "cohort",
        "source_spec",
        "protocol_binding",
        "shared_frozen_inputs",
        "members",
        "descriptive_summary",
        "interpretation",
        "authority_scope",
        "outcome",
        "closure_record_sha256",
    }
)
LINEAGE_FIELDS = frozenset(
    {
        "schema_version",
        "closure_lineage_id",
        "created_at",
        "closure_record_sha256",
        "cohort_id",
        "member_ratification_packet_sha256",
        "member_lineage_record_sha256",
        "outcome",
        "closure_lineage_sha256",
    }
)


def _digest(value: dict[str, Any], field: str) -> str:
    content = dict(value)
    content.pop(field, None)
    return sha256_value(content)


def _string(value: Any, path: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise CaptureError("INVALID_COHORT_CLOSURE_FIELD", "expected a non-empty bounded string", path)
    return value.strip()


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise CaptureError("INVALID_DIGEST", "expected a lowercase SHA-256 digest", path)
    try:
        int(value, 16)
    except ValueError as exc:
        raise CaptureError("INVALID_DIGEST", "expected a lowercase SHA-256 digest", path) from exc
    return value


def _score(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CaptureError("INVALID_COHORT_SCORE", "score must be numeric", path)
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise CaptureError("INVALID_COHORT_SCORE", "score must be finite and between zero and one", path)
    return result


def validate_closure_spec(spec: dict[str, Any]) -> dict[str, Any]:
    require_exact_fields(spec, SPEC_FIELDS)
    if spec.get("schema_version") != CLOSURE_SPEC_SCHEMA:
        raise CaptureError("UNSUPPORTED_COHORT_CLOSURE_SPEC", "unsupported closure spec schema")
    validate_safe_id(spec.get("closure_id"), "$.closure_id")
    validate_safe_id(spec.get("cohort_id"), "$.cohort_id")
    _string(spec.get("classification"), "$.classification")
    _string(spec.get("protocol_reference"), "$.protocol_reference", 1000)
    members = spec.get("members")
    if not isinstance(members, list) or len(members) < 2:
        raise CaptureError("INVALID_COHORT_MEMBERS", "closure requires at least two members")
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(members):
        member = require_object(raw, f"$.members[{index}]")
        require_exact_fields(member, MEMBER_FIELDS, f"$.members[{index}]")
        identity = (
            _string(member.get("campaign_id"), f"$.members[{index}].campaign_id"),
            _string(member.get("execution_id"), f"$.members[{index}].execution_id"),
            _string(member.get("ratification_id"), f"$.members[{index}].ratification_id"),
        )
        _string(member.get("declared_model_label"), f"$.members[{index}].declared_model_label")
        if identity in seen:
            raise CaptureError("DUPLICATE_COHORT_MEMBER", "cohort member identities must be unique")
        seen.add(identity)
        if not isinstance(member.get("requires_protocol_binding"), bool):
            raise CaptureError("INVALID_COHORT_MEMBER", "requires_protocol_binding must be boolean")
        for field in (
            "source_bundle_sha256",
            "judgment_sha256",
            "ratification_packet_sha256",
            "lineage_record_sha256",
        ):
            _sha(member.get(field), f"$.members[{index}].{field}")
        _string(member.get("verdict"), f"$.members[{index}].verdict")
        _score(member.get("score"), f"$.members[{index}].score")
        failures = member.get("detected_failure_modes")
        if not isinstance(failures, list) or not all(isinstance(item, str) for item in failures):
            raise CaptureError("INVALID_COHORT_MEMBER", "failure modes must be a string list")
    limits = spec.get("interpretation_limits")
    if not isinstance(limits, list) or not limits or not all(isinstance(item, str) and item.strip() for item in limits):
        raise CaptureError("INVALID_INTERPRETATION_LIMITS", "interpretation limits must be non-empty strings")
    authority = require_object(spec.get("authority"), "$.authority")
    if set(authority) != AUTHORITY_FIELDS or any(authority[field] is not False for field in AUTHORITY_FIELDS):
        raise CaptureError("COHORT_CLOSURE_AUTHORITY_OVERREACH", "closure spec claims forbidden authority")
    return spec


def read_closure_spec(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    return validate_closure_spec(require_object(strict_json_loads(data))), sha256_bytes(data)


def _canonical_record(path: Path, label: str) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    value = require_object(strict_json_loads(data))
    if canonical_bytes(value) != data:
        raise CaptureError("NONCANONICAL_COHORT_SOURCE", f"{label} must retain canonical stored bytes")
    return value, sha256_bytes(data)


def _binding_group(lock: dict[str, Any], group: str) -> list[dict[str, str]]:
    bindings = require_object(lock.get("bindings"), "$.benchmark_lock.bindings")
    entries = bindings.get(group)
    if not isinstance(entries, list) or not entries:
        raise CaptureError("MISSING_SHARED_FROZEN_BINDING", f"missing binding group {group}")
    normalized: list[dict[str, str]] = []
    for index, raw in enumerate(entries):
        entry = require_object(raw, f"$.benchmark_lock.bindings.{group}[{index}]")
        if set(entry) != {"path", "sha256"}:
            raise CaptureError("INVALID_SHARED_FROZEN_BINDING", "invalid binding entry shape")
        normalized.append(
            {
                "path": _string(entry.get("path"), f"$.benchmark_lock.bindings.{group}[{index}].path", 1000),
                "sha256": _sha(entry.get("sha256"), f"$.benchmark_lock.bindings.{group}[{index}].sha256"),
            }
        )
    return normalized


def _protocol_bound(lock: dict[str, Any], reference: str, digest: str) -> bool:
    bindings = require_object(lock.get("bindings"), "$.benchmark_lock.bindings")
    entries = bindings.get("evidence")
    return isinstance(entries, list) and any(
        isinstance(item, dict) and item.get("path") == reference and item.get("sha256") == digest
        for item in entries
    )


def load_member(
    member_spec: dict[str, Any],
    *,
    capture_root: Path,
    ratification_root: Path,
    protocol_reference: str,
    protocol_sha256: str,
) -> dict[str, Any]:
    campaign_id = member_spec["campaign_id"]
    execution_id = member_spec["execution_id"]
    bundle, review_file_sha = read_validated_review_bundle(
        capture_root / campaign_id / execution_id / "review-bundle.json"
    )
    ratification_dir = ratification_root / member_spec["ratification_id"]
    packet, packet_file_sha = _canonical_record(ratification_dir / "ratification-packet.json", "ratification packet")
    lineage, lineage_file_sha = _canonical_record(ratification_dir / "lineage-record.json", "ratification lineage")
    verify_ratification_packet(packet)
    verify_lineage_record(lineage, packet)
    checks = (
        (bundle.get("campaign_id"), campaign_id),
        (bundle.get("execution_id"), execution_id),
        (bundle.get("bundle_sha256"), member_spec["source_bundle_sha256"]),
        (bundle.get("deterministic_judgment", {}).get("judgment_sha256"), member_spec["judgment_sha256"]),
        (packet.get("ratification_packet_sha256"), member_spec["ratification_packet_sha256"]),
        (lineage.get("lineage_record_sha256"), member_spec["lineage_record_sha256"]),
    )
    if any(actual != expected for actual, expected in checks):
        raise CaptureError("COHORT_MEMBER_BINDING_MISMATCH", "cohort member differs from the closure spec")
    source = packet.get("source_review_bundle", {})
    if (
        source.get("file_sha256") != review_file_sha
        or source.get("bundle_sha256") != bundle["bundle_sha256"]
        or source.get("campaign_id") != campaign_id
        or source.get("execution_id") != execution_id
    ):
        raise CaptureError("COHORT_MEMBER_BINDING_MISMATCH", "ratification packet binds another review bundle")
    if (
        packet.get("human_action", {}).get("action") != "ratify"
        or packet.get("outcome", {}).get("class") != "RATIFIED"
        or packet.get("authority_scope", {}).get("accepts_deterministic_judgment") is not True
    ):
        raise CaptureError("COHORT_MEMBER_NOT_RATIFIED", "closure requires an accepted deterministic judgment")
    result = bundle["deterministic_judgment"]["deterministic_result"]
    if (
        result.get("verdict") != member_spec["verdict"]
        or float(result.get("score")) != float(member_spec["score"])
        or result.get("detected_failure_modes") != member_spec["detected_failure_modes"]
    ):
        raise CaptureError("COHORT_MEMBER_RESULT_MISMATCH", "deterministic result differs from the closure spec")
    parse_notes = require_object(result.get("parse_notes"), "$.deterministic_result.parse_notes")
    lock = require_object(bundle.get("benchmark_lock"), "$.benchmark_lock")
    if member_spec["requires_protocol_binding"] and not _protocol_bound(lock, protocol_reference, protocol_sha256):
        raise CaptureError("COHORT_PROTOCOL_BINDING_MISMATCH", "successor lock does not bind the cohort protocol")
    return {
        "declared_model_label": member_spec["declared_model_label"],
        "campaign_id": campaign_id,
        "execution_id": execution_id,
        "review_bundle_file_sha256": review_file_sha,
        "source_bundle_sha256": bundle["bundle_sha256"],
        "benchmark_lock_digest": bundle["benchmark_lock"]["lock_digest"],
        "capture_manifest_sha256": bundle["capture_manifest"]["manifest_sha256"],
        "judgment_sha256": bundle["deterministic_judgment"]["judgment_sha256"],
        "integrity_report_sha256": bundle["integrity_verification_report"]["integrity_report_sha256"],
        "ratification_id": packet["ratification_id"],
        "ratification_packet_sha256": packet["ratification_packet_sha256"],
        "ratification_packet_file_sha256": packet_file_sha,
        "lineage_record_sha256": lineage["lineage_record_sha256"],
        "lineage_record_file_sha256": lineage_file_sha,
        "human_disposition": "RATIFIED",
        "verdict": result["verdict"],
        "score": result["score"],
        "detected_failure_modes": list(result["detected_failure_modes"]),
        "result_hash": _sha(result.get("result_hash"), "$.deterministic_result.result_hash"),
        "canonical_output_sha256": _sha(parse_notes.get("canonical_output_sha256"), "$.parse_notes.canonical_output_sha256"),
        "response_text_sha256": _sha(parse_notes.get("response_text_sha256"), "$.parse_notes.response_text_sha256"),
        "shared_bindings": {group: _binding_group(lock, group) for group in SHARED_GROUPS},
    }


def _validate_loaded(spec_members: list[dict[str, Any]], members: list[dict[str, Any]]) -> None:
    if len(spec_members) != len(members):
        raise CaptureError("COHORT_MEMBER_COUNT_MISMATCH", "loaded member count differs from closure spec")
    fields = (
        "declared_model_label",
        "campaign_id",
        "execution_id",
        "ratification_id",
        "source_bundle_sha256",
        "judgment_sha256",
        "ratification_packet_sha256",
        "lineage_record_sha256",
        "verdict",
        "detected_failure_modes",
    )
    for index, (expected, actual) in enumerate(zip(spec_members, members)):
        if any(actual.get(field) != expected.get(field) for field in fields):
            raise CaptureError("COHORT_MEMBER_BINDING_MISMATCH", f"loaded member {index} differs from closure spec")
        if float(actual.get("score")) != float(expected.get("score")):
            raise CaptureError("COHORT_MEMBER_RESULT_MISMATCH", "loaded member score differs from closure spec")
        if actual.get("human_disposition") != "RATIFIED":
            raise CaptureError("COHORT_MEMBER_NOT_RATIFIED", "closure requires RATIFIED members")


def _shared(members: list[dict[str, Any]]) -> dict[str, Any]:
    reference = members[0].get("shared_bindings")
    if not isinstance(reference, dict) or set(reference) != set(SHARED_GROUPS):
        raise CaptureError("INVALID_SHARED_FROZEN_BINDING", "shared binding groups are incomplete")
    for member in members[1:]:
        if member.get("shared_bindings") != reference:
            raise CaptureError("COHORT_SHARED_INPUT_MISMATCH", "cohort members bind different frozen inputs")
    return reference


def build_closure_records(
    *,
    spec: dict[str, Any],
    spec_reference: str,
    spec_file_sha256: str,
    protocol_sha256: str,
    members: list[dict[str, Any]],
    closed_by: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_closure_spec(spec)
    validate_timestamp(created_at, "$.created_at")
    _sha(spec_file_sha256, "$.source_spec.file_sha256")
    _sha(protocol_sha256, "$.protocol_binding.file_sha256")
    _validate_loaded(spec["members"], members)
    shared = _shared(members)
    verdict_counts = dict(sorted(Counter(item["verdict"] for item in members).items()))
    failure_counts = dict(sorted(Counter(mode for item in members for mode in item["detected_failure_modes"]).items()))
    groups: dict[str, list[str]] = defaultdict(list)
    for item in members:
        groups[item["result_hash"]].append(item["execution_id"])
    public_members = [{key: value for key, value in item.items() if key != "shared_bindings"} for item in members]
    record: dict[str, Any] = {
        "schema_version": CLOSURE_RECORD_SCHEMA,
        "closure_id": spec["closure_id"],
        "created_at": created_at,
        "closed_by": {
            "identity": _string(closed_by, "$.closed_by"),
            "authority_type": "declared_human_operator",
            "action": "mechanical_cohort_closure",
        },
        "cohort": {
            "cohort_id": spec["cohort_id"],
            "classification": spec["classification"],
            "member_count": len(members),
        },
        "source_spec": {"reference": spec_reference, "file_sha256": spec_file_sha256},
        "protocol_binding": {"reference": spec["protocol_reference"], "file_sha256": protocol_sha256},
        "shared_frozen_inputs": {"binding_groups": shared, "verified_identical_across_members": True},
        "members": public_members,
        "descriptive_summary": {
            "verdict_counts": verdict_counts,
            "failure_mode_counts": failure_counts,
            "result_hash_groups": [
                {"result_hash": digest, "execution_ids": executions}
                for digest, executions in sorted(groups.items())
            ],
        },
        "interpretation": {
            "class": "closed_exploratory_cohort",
            "limits": list(spec["interpretation_limits"]),
            "inferential_ranking_authorized": False,
            "general_model_performance_claim_authorized": False,
        },
        "authority_scope": dict(spec["authority"]),
        "outcome": {
            "class": "COHORT_CLOSED",
            "all_members_ratified": True,
            "source_capture_runs_mutated": False,
            "source_ratification_records_mutated": False,
            "replication_required_for_generalization": True,
        },
    }
    record["closure_record_sha256"] = _digest(record, "closure_record_sha256")
    lineage: dict[str, Any] = {
        "schema_version": CLOSURE_LINEAGE_SCHEMA,
        "closure_lineage_id": f"lineage-{spec['closure_id']}",
        "created_at": created_at,
        "closure_record_sha256": record["closure_record_sha256"],
        "cohort_id": spec["cohort_id"],
        "member_ratification_packet_sha256": [item["ratification_packet_sha256"] for item in members],
        "member_lineage_record_sha256": [item["lineage_record_sha256"] for item in members],
        "outcome": {
            "class": "COHORT_LINEAGE_RECORDED",
            "capture_mutation_effect": "none",
            "ratification_mutation_effect": "none",
            "ranking_effect": "none",
            "promotion_effect": "none",
            "publication_effect": "none",
            "release_effect": "none",
        },
    }
    lineage["closure_lineage_sha256"] = _digest(lineage, "closure_lineage_sha256")
    verify_closure_record(record)
    verify_closure_lineage(lineage, record)
    return record, lineage


def verify_closure_record(record: dict[str, Any]) -> dict[str, Any]:
    require_exact_fields(record, RECORD_FIELDS)
    if record.get("schema_version") != CLOSURE_RECORD_SCHEMA:
        raise CaptureError("UNSUPPORTED_COHORT_CLOSURE", "unsupported closure record schema")
    if record.get("closure_record_sha256") != _digest(record, "closure_record_sha256"):
        raise CaptureError("COHORT_CLOSURE_DIGEST_MISMATCH", "closure record was modified")
    outcome = record.get("outcome", {})
    if (
        outcome.get("class") != "COHORT_CLOSED"
        or outcome.get("all_members_ratified") is not True
        or outcome.get("source_capture_runs_mutated") is not False
        or outcome.get("source_ratification_records_mutated") is not False
    ):
        raise CaptureError("COHORT_CLOSURE_OUTCOME_MISMATCH", "closure outcome is invalid")
    authority = record.get("authority_scope")
    if not isinstance(authority, dict) or set(authority) != AUTHORITY_FIELDS or any(authority[field] is not False for field in AUTHORITY_FIELDS):
        raise CaptureError("COHORT_CLOSURE_AUTHORITY_OVERREACH", "closure claims forbidden authority")
    if any(item.get("human_disposition") != "RATIFIED" for item in record.get("members", [])):
        raise CaptureError("COHORT_MEMBER_NOT_RATIFIED", "closure includes a non-ratified member")
    assert_secret_free(record)
    return record


def verify_closure_lineage(lineage: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    require_exact_fields(lineage, LINEAGE_FIELDS)
    if lineage.get("schema_version") != CLOSURE_LINEAGE_SCHEMA:
        raise CaptureError("UNSUPPORTED_COHORT_CLOSURE_LINEAGE", "unsupported closure lineage schema")
    if lineage.get("closure_lineage_sha256") != _digest(lineage, "closure_lineage_sha256"):
        raise CaptureError("COHORT_CLOSURE_LINEAGE_DIGEST_MISMATCH", "closure lineage was modified")
    if (
        lineage.get("closure_record_sha256") != record.get("closure_record_sha256")
        or lineage.get("cohort_id") != record.get("cohort", {}).get("cohort_id")
        or lineage.get("member_ratification_packet_sha256") != [item["ratification_packet_sha256"] for item in record["members"]]
        or lineage.get("member_lineage_record_sha256") != [item["lineage_record_sha256"] for item in record["members"]]
    ):
        raise CaptureError("COHORT_CLOSURE_LINEAGE_BINDING_MISMATCH", "closure lineage binds another record")
    outcome = lineage.get("outcome", {})
    if outcome.get("class") != "COHORT_LINEAGE_RECORDED" or any(
        outcome.get(field) != "none"
        for field in (
            "capture_mutation_effect",
            "ratification_mutation_effect",
            "ranking_effect",
            "promotion_effect",
            "publication_effect",
            "release_effect",
        )
    ):
        raise CaptureError("COHORT_CLOSURE_AUTHORITY_OVERREACH", "closure lineage claims forbidden effects")
    assert_secret_free(lineage)
    return lineage


def closure_markdown(record: dict[str, Any], lineage: dict[str, Any]) -> str:
    rows = []
    for item in record["members"]:
        failures = ", ".join(item["detected_failure_modes"]) or "none"
        rows.append(
            f"| `{item['declared_model_label']}` | `{item['execution_id']}` | `{item['verdict']}` | `{item['score']}` | `{failures}` |"
        )
    return (
        "# Campaign Cohort Closure\n\n"
        f"- Closure ID: `{record['closure_id']}`\n"
        f"- Cohort: `{record['cohort']['cohort_id']}`\n"
        f"- Outcome: `{record['outcome']['class']}`\n"
        f"- Closure digest: `{record['closure_record_sha256']}`\n\n"
        "## Members\n\n"
        "| Declared model label | Execution | Verdict | Score | Failure modes |\n"
        "|---|---|---:|---:|---|\n"
        + "\n".join(rows)
        + "\n\n## Authority Boundary\n\n"
        "This mechanically closes an exploratory cohort. It does not establish a model ranking, endorsement, promotion, publication, release, or legal approval.\n\n"
        "## Lineage\n\n"
        f"- Lineage digest: `{lineage['closure_lineage_sha256']}`\n"
        "- Capture runs mutated: `false`\n"
        "- Ratification records mutated: `false`\n"
    )


def write_closure_records(output_root: Path, record: dict[str, Any], lineage: dict[str, Any]) -> Path:
    verify_closure_record(record)
    verify_closure_lineage(lineage, record)
    target = output_root / record["closure_id"]
    target.mkdir(parents=True, exist_ok=False)
    write_exclusive_json(target / "cohort-closure.json", record)
    write_exclusive_json(target / "cohort-closure-lineage.json", lineage)
    write_exclusive_bytes(target / "cohort-closure.md", closure_markdown(record, lineage).encode("utf-8"))
    stored = require_object(strict_json_loads((target / "cohort-closure.json").read_bytes()))
    stored_lineage = require_object(strict_json_loads((target / "cohort-closure-lineage.json").read_bytes()))
    verify_closure_record(stored)
    verify_closure_lineage(stored_lineage, stored)
    return target
