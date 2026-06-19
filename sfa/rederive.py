"""Replay re-derivation for supported transcript fixtures."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from . import families as fam_mod
from . import hashing
from . import transcript as transcript_mod
from . import verifier as verifier_mod


REPLAY_RECORD_SCHEMA = "sfa.transcript_replay.v0.1"


@dataclass(frozen=True)
class ReDerivationResult:
    name: str
    passed: bool
    issues: list[dict[str, str]]
    verdict: dict[str, Any]
    family: str | None


def discover_records(root_dir: str) -> list[str]:
    base = os.path.join(root_dir, "examples", "external_transcripts")
    if not os.path.isdir(base):
        return []
    return [
        os.path.join(base, name)
        for name in sorted(os.listdir(base))
        if name.endswith(".replay.json")
    ]


def rederive_record(record_path: str, root_dir: str) -> ReDerivationResult:
    record = _read_json(record_path)
    if record.get("schema") != REPLAY_RECORD_SCHEMA:
        return ReDerivationResult(os.path.basename(record_path), False, [_issue("replay_schema_invalid", "unsupported replay record schema")], {}, None)

    name = record.get("name", os.path.basename(record_path))
    transcript_path = os.path.join(root_dir, record["transcript_path"])
    candidate_path = os.path.join(root_dir, record["normalized_candidate_path"])
    case_dir = os.path.join(root_dir, record["case_dir"])
    input_obj = _read_json(os.path.join(case_dir, "input.json"))
    evidence_obj = _read_json(os.path.join(case_dir, "evidence.json"))
    rules_obj = _read_json(os.path.join(case_dir, "verifier_rules.json"))
    sealed_candidate = _read_json(candidate_path)
    raw_transcript = transcript_mod.load_transcript(transcript_path)
    normalized = transcript_mod.normalize_transcript(
        raw_transcript,
        input_obj=input_obj,
        evidence_obj=evidence_obj,
        rules_obj=rules_obj,
    )
    verdict = verifier_mod.verify(input_obj, evidence_obj, sealed_candidate, rules_obj)
    verdict_dict = verdict.to_dict()
    family = fam_mod.classify_family(verdict.category, sealed_candidate, evidence_obj) if verdict.status == "FAIL" else None

    expected = record.get("expected", {})
    issues = []
    _compare(issues, "raw_source_hash", expected.get("raw_source_hash"), hashing.sha256_hex(raw_transcript))
    sealed_candidate_hash = hashing.sha256_hex(sealed_candidate)
    _compare(issues, "normalized_candidate_hash", expected.get("normalized_candidate_hash"), sealed_candidate_hash)
    if sealed_candidate_hash != hashing.sha256_hex(normalized.candidate):
        issues.append(_issue("normalization_output_mismatch", "transcript normalization does not match sealed normalized candidate"))
    _compare(issues, "input_hash", expected.get("input_hash"), hashing.sha256_hex(input_obj))
    _compare(issues, "evidence_hash", expected.get("evidence_hash"), hashing.sha256_hex(evidence_obj))
    _compare(issues, "rules_hash", expected.get("rules_hash"), hashing.sha256_hex(rules_obj))
    _compare(issues, "verifier_input_hash", expected.get("verifier_input_hash"), normalized.provenance.get("verifier_input_hash"))
    if expected.get("verdict") != verdict_dict:
        issues.append(_issue("verdict_mismatch", "re-derived verifier verdict does not match replay record"))
    if expected.get("family") != family:
        issues.append(_issue("family_mismatch", "re-derived failure family does not match replay record"))

    return ReDerivationResult(name, not issues, issues, verdict_dict, family)


def _compare(issues: list[dict[str, str]], field: str, expected: str | None, actual: str | None) -> None:
    if expected != actual:
        issues.append(_issue(field + "_mismatch", f"{field} expected {expected} got {actual}"))


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
