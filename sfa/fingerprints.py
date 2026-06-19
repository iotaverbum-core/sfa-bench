"""Deterministic failure-family fingerprints over sealed occurrence inputs.

This module is a reporting layer. It derives model-labelled occurrences from
local transcript fixtures, but passes only normalized candidates and fixed case
inputs to the verifier.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from . import families as families_mod
from . import transcript as transcript_mod
from . import verifier as verifier_mod
from .hashing import sha256_hex


FIXTURE_SET_SCHEMA = "sfa.fingerprint_fixture_set.v0.1"
EXPECTED_SCHEMA = "sfa.fingerprint_expected.v0.1"
OCCURRENCE_SCHEMA = "sfa.fingerprint_occurrence.v0.1"
REPORT_SCHEMA = "sfa.failure_fingerprint.v0.1"
UNKNOWN_MODEL_ID = "unknown"

CONDITION_FIELDS = (
    "evidence_pack_id",
    "case_set_id",
    "prompt_condition_id",
    "adapter_id",
    "taxonomy_version",
)


class FingerprintError(ValueError):
    """Raised when fingerprint inputs are invalid or incomparable."""


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def model_id_of(occurrence: dict[str, Any]) -> str:
    """Return a stable reporting identity for new or legacy occurrences."""
    value = occurrence.get("model_id")
    return value if isinstance(value, str) and value.strip() else UNKNOWN_MODEL_ID


def condition_key(conditions: dict[str, Any]) -> dict[str, str]:
    missing = [field for field in CONDITION_FIELDS if not conditions.get(field)]
    if missing:
        raise FingerprintError("missing fingerprint condition(s): " + ", ".join(missing))
    return {field: str(conditions[field]) for field in CONDITION_FIELDS}


def assert_comparable(left: dict[str, Any], right: dict[str, Any]) -> None:
    """Refuse comparison across different fixed conditions."""
    left_conditions = condition_key(left.get("conditions", left))
    right_conditions = condition_key(right.get("conditions", right))
    mismatches = [
        field for field in CONDITION_FIELDS
        if left_conditions[field] != right_conditions[field]
    ]
    if mismatches:
        raise FingerprintError(
            "fingerprints are not comparable; fixed condition mismatch: "
            + ", ".join(mismatches)
        )


def compute_fingerprint(
    occurrences: list[dict[str, Any]],
    conditions: dict[str, Any],
    *,
    fixture_set_id: str,
) -> dict[str, Any]:
    """Aggregate deterministic per-model failure-family distributions."""
    fixed = condition_key(conditions)
    ordered = sorted((deepcopy(item) for item in occurrences), key=_occurrence_sort_key)
    for occurrence in ordered:
        for field, expected in fixed.items():
            if occurrence.get(field) != expected:
                raise FingerprintError(
                    f"occurrence {occurrence.get('sample_id')!r} has mismatched {field}"
                )
        stored_hash = occurrence.get("occurrence_hash")
        if stored_hash and stored_hash != _hash_without(occurrence, "occurrence_hash"):
            raise FingerprintError(
                f"occurrence {occurrence.get('sample_id')!r} failed its seal"
            )

    models: dict[str, list[dict[str, Any]]] = {}
    for occurrence in ordered:
        models.setdefault(model_id_of(occurrence), []).append(occurrence)

    model_fingerprints = []
    for model_id in sorted(models):
        samples = models[model_id]
        family_counts: dict[str, int] = {}
        pass_count = sum(item.get("status") == "PASS" for item in samples)
        fail_count = sum(item.get("status") == "FAIL" for item in samples)
        for item in samples:
            family = item.get("family")
            if item.get("status") == "FAIL" and family:
                family_counts[family] = family_counts.get(family, 0) + 1
        sorted_counts = dict(sorted(family_counts.items()))
        family_rates = {
            family: _rate(count, fail_count)
            for family, count in sorted_counts.items()
        }
        dominant = None
        if sorted_counts:
            dominant = sorted(sorted_counts, key=lambda family: (-sorted_counts[family], family))[0]
        model_fingerprints.append(
            {
                "model_id": model_id,
                "attempts": len(samples),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "pass_rate": _rate(pass_count, len(samples)),
                "family_counts": sorted_counts,
                "family_rates_among_failures": family_rates,
                "dominant_family": dominant,
                "recurrence_summary": {
                    "distinct_failure_families": len(sorted_counts),
                    "recurring_families": [
                        family for family, count in sorted_counts.items() if count > 1
                    ],
                },
                "sample_ids": sorted(str(item.get("sample_id")) for item in samples),
            }
        )

    report = {
        "schema": REPORT_SCHEMA,
        "fixture_set_id": fixture_set_id,
        "conditions": fixed,
        "attempts": len(ordered),
        "failures": sum(item.get("status") == "FAIL" for item in ordered),
        "passes": sum(item.get("status") == "PASS" for item in ordered),
        "input_hash": sha256_hex({"conditions": fixed, "occurrences": ordered}),
        "models": model_fingerprints,
    }
    report["fingerprint_hash"] = _hash_without(report, "fingerprint_hash")
    return report


def derive_fixture_set(
    fixture_set_path: str | Path,
    repo_root: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Re-derive sealed occurrences and their fingerprint entirely offline."""
    fixture_set = load_json(fixture_set_path)
    if fixture_set.get("schema") != FIXTURE_SET_SCHEMA:
        raise FingerprintError("unsupported fingerprint fixture-set schema")
    if fixture_set.get("illustrative_fixture_data") is not True:
        raise FingerprintError("fingerprint fixture set must be labelled illustrative")

    fixture_set_id = fixture_set.get("fixture_set_id")
    if not fixture_set_id:
        raise FingerprintError("fixture_set_id is required")
    conditions = condition_key(fixture_set.get("conditions", {}))
    root = Path(repo_root)
    taxonomy = load_json(root / "families.json")
    if taxonomy.get("taxonomy_version") != conditions["taxonomy_version"]:
        raise FingerprintError("fixture taxonomy version does not match families.json")

    cases = {
        item["case_id"]: root / item["case_dir"]
        for item in fixture_set.get("cases", [])
    }
    if not cases:
        raise FingerprintError("fixture set has no cases")

    sample_ids: set[str] = set()
    occurrences = []
    for sample in fixture_set.get("samples", []):
        sample_id = sample.get("sample_id")
        if not sample_id or sample_id in sample_ids:
            raise FingerprintError(f"invalid or duplicate sample_id: {sample_id!r}")
        sample_ids.add(sample_id)
        transcript = sample.get("transcript")
        if not isinstance(transcript, dict):
            raise FingerprintError(f"sample {sample_id!r} has no transcript object")
        case_id = transcript.get("case_id")
        if case_id not in cases:
            raise FingerprintError(f"sample {sample_id!r} uses unknown case {case_id!r}")
        metadata = transcript.get("metadata", {})
        if metadata.get("adapter_id") != conditions["adapter_id"]:
            raise FingerprintError(f"sample {sample_id!r} adapter condition mismatch")
        if metadata.get("prompt_template_id") != conditions["prompt_condition_id"]:
            raise FingerprintError(f"sample {sample_id!r} prompt condition mismatch")
        model_id = model_id_of(metadata)
        if model_id == UNKNOWN_MODEL_ID:
            raise FingerprintError(f"sample {sample_id!r} requires model_id")

        case_dir = cases[case_id]
        input_obj = load_json(case_dir / "input.json")
        evidence_obj = load_json(case_dir / "evidence.json")
        rules_obj = load_json(case_dir / "verifier_rules.json")
        normalized = transcript_mod.normalize_transcript(
            transcript,
            input_obj=input_obj,
            evidence_obj=evidence_obj,
            rules_obj=rules_obj,
        )
        verdict = verifier_mod.verify(input_obj, evidence_obj, normalized.candidate, rules_obj)
        family = None
        if verdict.status == "FAIL":
            family = families_mod.classify_family(
                verdict.category, normalized.candidate, evidence_obj
            )
        occurrence = {
            "schema": OCCURRENCE_SCHEMA,
            "fixture_set_id": fixture_set_id,
            "sample_id": sample_id,
            "run_id": sample.get("run_id", sample_id),
            "case_id": case_id,
            "model_id": model_id,
            "status": verdict.status,
            "category": verdict.category,
            "family": family,
            **conditions,
            "raw_source_hash": normalized.provenance["raw_source_hash"],
            "normalized_candidate_hash": normalized.provenance["normalized_candidate_hash"],
            "verifier_input_hash": normalized.provenance["verifier_input_hash"],
            "verdict_hash": sha256_hex(verdict.to_dict()),
        }
        occurrence["occurrence_hash"] = _hash_without(occurrence, "occurrence_hash")
        occurrences.append(occurrence)

    if not occurrences:
        raise FingerprintError("fixture set has no samples")
    report = compute_fingerprint(
        occurrences,
        conditions,
        fixture_set_id=str(fixture_set_id),
    )
    return report, occurrences


def verify_fixture_set(
    fixture_set_path: str | Path,
    expected_path: str | Path,
    repo_root: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    """Re-derive a fixture fingerprint and compare it with its separate seal."""
    fixture_set = load_json(fixture_set_path)
    expected = load_json(expected_path)
    if expected.get("schema") != EXPECTED_SCHEMA:
        raise FingerprintError("unsupported expected-fingerprint schema")
    report, occurrences = derive_fixture_set(fixture_set_path, repo_root)
    actual = {
        "fixture_set_hash": sha256_hex(fixture_set),
        "conditions_hash": sha256_hex(report["conditions"]),
        "fingerprint_input_hash": report["input_hash"],
        "fingerprint_hash": report["fingerprint_hash"],
        "model_summaries_hash": sha256_hex(report["models"]),
    }
    issues = []
    for field, value in actual.items():
        if expected.get(field) != value:
            issues.append(
                {
                    "code": field + "_mismatch",
                    "detail": f"stored {expected.get(field)!r} != derived {value!r}",
                }
            )
    if expected.get("fixture_set_id") != report["fixture_set_id"]:
        issues.append({"code": "fixture_set_id_mismatch", "detail": "fixture set id changed"})
    return report, occurrences, issues


def _hash_without(obj: dict[str, Any], field: str) -> str:
    return sha256_hex({key: value for key, value in obj.items() if key != field})


def _occurrence_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (model_id_of(item), str(item.get("sample_id", "")), str(item.get("occurrence_hash", "")))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
