#!/usr/bin/env python3
"""Run the v0.5 external-candidate provenance boundary demo."""
import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO

import invariant_suite
import replay
from sfa import tamper
from sfa.agent import SFAAgent
from sfa.external_adapter import ExternalCandidateAdapter
from sfa.provenance import verify_attempt_files


ROOT = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(ROOT, "cases", "external_candidate_001")
BAD_CANDIDATE = os.path.join(ROOT, "examples", "external_candidates", "bad_candidate.json")
GOOD_CANDIDATE = os.path.join(ROOT, "examples", "external_candidates", "good_candidate.json")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    task = _read_json(os.path.join(CASE_DIR, "input.json"))
    evidence_pack = {
        "evidence": _read_json(os.path.join(CASE_DIR, "evidence.json")),
        "verifier_rules": _read_json(os.path.join(CASE_DIR, "verifier_rules.json")),
    }

    agent = SFAAgent(ROOT)
    result = agent.run(
        task,
        evidence_pack,
        ExternalCandidateAdapter(BAD_CANDIDATE),
        retry_adapter=ExternalCandidateAdapter(GOOD_CANDIDATE),
    )

    print("SFA-Agent v0.7 external candidate demo")
    print("=" * 56)
    print(f"external candidate loaded: {os.path.relpath(BAD_CANDIDATE, ROOT)}")
    print(f"run_id: {result.run_id}")
    print(f"run_dir: {os.path.relpath(result.run_dir, ROOT)}")

    raw_preserved = True
    provenance_written = True
    for attempt in result.attempts:
        attempt_no = attempt["attempt"]
        raw_path = os.path.join(result.run_dir, f"attempt_{attempt_no:03d}_raw_source.json")
        provenance_path = os.path.join(result.run_dir, f"attempt_{attempt_no:03d}_provenance.json")
        raw_preserved = raw_preserved and os.path.exists(raw_path)
        provenance_written = provenance_written and os.path.exists(provenance_path)

        line = f"attempt {attempt_no}: {attempt['status']}"
        if attempt.get("family"):
            line += f" ({attempt['category']} / {attempt['family']})"
        print(line)
        if attempt.get("failure_artifact_path"):
            print("  failure sealed/logged")

    print(f"raw source preserved: {'yes' if raw_preserved else 'no'}")
    print(f"provenance written: {'yes' if provenance_written else 'no'}")

    warning_path = os.path.join(result.run_dir, "attempt_001_warning.json")
    warning_generated = os.path.exists(warning_path)
    print(f"warning generated: {'yes' if warning_generated else 'no'}")
    if warning_generated:
        warning = _read_json(warning_path)
        print(f"  {warning['message']}")

    checks = [verify_attempt_files(result.run_dir, attempt["attempt"]) for attempt in result.attempts]
    raw_hash_ok = all(check.get("source_hash") for check in checks)
    candidate_hash_ok = all(check.get("normalized_candidate_hash") for check in checks)
    print(f"raw source hash verified: {'yes' if raw_hash_ok else 'no'}")
    print(f"normalized candidate hash verified: {'yes' if candidate_hash_ok else 'no'}")

    print("both attempts and provenance preserved:")
    for name in (
        "attempt_001_raw_source.json",
        "attempt_001_candidate.json",
        "attempt_001_provenance.json",
        "attempt_001_verdict.json",
        "attempt_001_warning.json",
        "attempt_001_failure_artifact.json",
        "attempt_002_raw_source.json",
        "attempt_002_candidate.json",
        "attempt_002_provenance.json",
        "attempt_002_verdict.json",
        "summary.json",
    ):
        print(f"  {name}: {'yes' if os.path.exists(os.path.join(result.run_dir, name)) else 'no'}")

    replay_ok = _replay_ok()
    tamper_ok = _tamper_ok()
    invariant_ok = _invariant_ok()
    print("=" * 56)
    print(f"replay still passes: {'yes' if replay_ok else 'no'}")
    print(f"tamper suite still passes: {'yes' if tamper_ok else 'no'}")
    print(f"invariant suite still passes: {'yes' if invariant_ok else 'no'}")
    print(f"final status: {result.status}")
    return 0 if result.status == "PASS" and raw_hash_ok and candidate_hash_ok and replay_ok and tamper_ok and invariant_ok else 2


def _replay_ok():
    out = StringIO()
    with redirect_stdout(out):
        return replay.main() == 0


def _tamper_ok():
    return all(result.passed for result in tamper.run_tamper_checks(ROOT))


def _invariant_ok():
    out = StringIO()
    with redirect_stdout(out):
        return invariant_suite.main() == 0


if __name__ == "__main__":
    sys.exit(main())
