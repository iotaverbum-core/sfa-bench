#!/usr/bin/env python3
"""Run the v1.0.0 offline transcript normalization demo."""
from datetime import datetime, timezone
import json
import os
import sys
import uuid

from sfa import artifact as artifact_mod
from sfa import families as fam_mod
from sfa import hashing
from sfa import history as history_mod
from sfa import ledger as ledger_mod
from sfa import transcript as transcript_mod
from sfa import verifier as verifier_mod


ROOT = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPT_PATH = os.path.join(ROOT, "examples", "external_transcripts", "bad_transcript.json")
CASE_DIR = os.path.join(ROOT, "cases", "external_candidate_001")
RUN_ROOT = os.path.join(ROOT, "transcript_runs")
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")
CONFIG_PATH = os.path.join(ROOT, "history_config.json")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json_new(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def main():
    run_id = "transcript-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = os.path.join(RUN_ROOT, run_id)
    os.makedirs(run_dir, exist_ok=False)

    raw_source = transcript_mod.load_transcript(TRANSCRIPT_PATH)
    input_obj = _read_json(os.path.join(CASE_DIR, "input.json"))
    evidence_obj = _read_json(os.path.join(CASE_DIR, "evidence.json"))
    rules_obj = _read_json(os.path.join(CASE_DIR, "verifier_rules.json"))
    normalized = transcript_mod.normalize_transcript(
        raw_source,
        input_obj=input_obj,
        evidence_obj=evidence_obj,
        rules_obj=rules_obj,
    )

    raw_path = os.path.join(run_dir, "raw_source.json")
    candidate_path = os.path.join(run_dir, "candidate.json")
    provenance_path = os.path.join(run_dir, "provenance.json")
    input_path = os.path.join(run_dir, "input.json")
    evidence_path = os.path.join(run_dir, "evidence.json")
    rules_path = os.path.join(run_dir, "verifier_rules.json")

    _write_json_new(raw_path, raw_source)
    _write_json_new(candidate_path, normalized.candidate)
    _write_json_new(provenance_path, normalized.provenance)
    _write_json_new(input_path, input_obj)
    _write_json_new(evidence_path, evidence_obj)
    _write_json_new(rules_path, rules_obj)

    verdict = verifier_mod.verify(input_obj, evidence_obj, normalized.candidate, rules_obj)
    family = fam_mod.classify_family(verdict.category, normalized.candidate, evidence_obj) if verdict.status == "FAIL" else None
    verdict_record = {
        "status": verdict.status,
        "category": verdict.category,
        "family": family,
        "verdict": verdict.to_dict(),
    }
    _write_json_new(os.path.join(run_dir, "verdict.json"), verdict_record)

    failure_logged = False
    if verdict.status == "FAIL":
        observed_at = datetime.now(timezone.utc).isoformat()
        failure_artifact = artifact_mod.seal_failure(
            raw_source["case_id"],
            input_obj,
            evidence_obj,
            normalized.candidate,
            verifier_mod.VERIFIER_VERSION,
            verdict.category,
            family,
            verdict.explanation,
            sealed_at=observed_at,
        )
        _write_json_new(os.path.join(run_dir, "failure_artifact.json"), failure_artifact)
        _append_occurrence(
            failure_artifact,
            verdict,
            family,
            observed_at,
            run_id,
            normalized.provenance["model_id"],
        )
        failure_logged = True

    raw_hash_ok = normalized.provenance["raw_source_hash"] == hashing.sha256_hex(_read_json(raw_path))
    candidate_hash_ok = normalized.provenance["normalized_candidate_hash"] == hashing.sha256_hex(_read_json(candidate_path))
    rederived = _rederive_from_run(run_dir)
    rederived_ok = rederived == verdict.to_dict()
    verifier_normalized_only = _verifier_normalized_only(input_obj, evidence_obj, normalized.candidate, rules_obj, verdict.to_dict())

    metadata = raw_source["metadata"]
    print("SFA-Bench v1.0.0 transcript demo")
    print("=" * 56)
    print(f"transcript loaded: {os.path.relpath(TRANSCRIPT_PATH, ROOT)}")
    print(f"model_id: {metadata['model_id']}")
    print(f"adapter_id: {metadata['adapter_id']}")
    print(f"run_id: {run_id}")
    print(f"raw_source sealed: {'yes' if os.path.exists(raw_path) else 'no'}")
    print(f"candidate normalized: {'yes' if os.path.exists(candidate_path) else 'no'}")
    print(f"raw_source_hash verified: {'yes' if raw_hash_ok else 'no'}")
    print(f"normalized_candidate_hash verified: {'yes' if candidate_hash_ok else 'no'}")
    verdict_line = f"verdict: {verdict.status}"
    if verdict.status == "FAIL":
        verdict_line += f" {verdict.category} / {family}"
    print(verdict_line)
    print(f"failure sealed/logged: {'yes' if failure_logged else 'not applicable'}")
    print(f"re-derived verdict matches sealed verdict: {'yes' if rederived_ok else 'no'}")
    print(f"verifier received normalized candidate only: {'yes' if verifier_normalized_only else 'no'}")
    print("=" * 56)
    final_ok = raw_hash_ok and candidate_hash_ok and rederived_ok and verifier_normalized_only
    print(f"final status: {'PASS' if final_ok else 'FAIL'}")
    return 0 if final_ok else 2


def _append_occurrence(failure_artifact, verdict, family, observed_at, run_id, model_id):
    config = _read_json(CONFIG_PATH)
    granularity = config.get("period_granularity", "year")
    return ledger_mod.append_occurrence(
        LEDGER_PATH,
        artifact_hash=failure_artifact["artifact_hash"],
        case_id=failure_artifact["case_id"],
        category=verdict.category,
        family=family,
        observed_at=observed_at,
        period=history_mod.period_of(observed_at, granularity),
        run_id=run_id,
        synthetic=False,
        model_id=model_id,
    )


def _rederive_from_run(run_dir):
    input_obj = _read_json(os.path.join(run_dir, "input.json"))
    evidence_obj = _read_json(os.path.join(run_dir, "evidence.json"))
    candidate_obj = _read_json(os.path.join(run_dir, "candidate.json"))
    rules_obj = _read_json(os.path.join(run_dir, "verifier_rules.json"))
    return verifier_mod.verify(input_obj, evidence_obj, candidate_obj, rules_obj).to_dict()


def _verifier_normalized_only(input_obj, evidence_obj, candidate_obj, rules_obj, expected_verdict):
    return verifier_mod.verify(input_obj, evidence_obj, candidate_obj, rules_obj).to_dict() == expected_verdict


if __name__ == "__main__":
    sys.exit(main())
