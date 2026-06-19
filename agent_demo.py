#!/usr/bin/env python3
"""Run the deterministic v0.7 SFA-Agent proof of concept."""
import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO

from sfa.agent import SFAAgent
from sfa.model_adapter import DeterministicFakeAdapter
from sfa import tamper
import replay


ROOT = os.path.dirname(os.path.abspath(__file__))
CASE_DIR = os.path.join(ROOT, "cases", "agent_demo_001")


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
    result = agent.run(task, evidence_pack, DeterministicFakeAdapter())

    print("SFA-Agent v0.7 demo")
    print("=" * 48)
    print(f"run_id: {result.run_id}")
    print(f"run_dir: {os.path.relpath(result.run_dir, ROOT)}")
    for attempt in result.attempts:
        line = f"attempt {attempt['attempt']}: {attempt['status']}"
        if attempt.get("family"):
            line += f" ({attempt['category']} / {attempt['family']})"
        print(line)
        if attempt.get("failure_artifact_path"):
            print("  failure sealed/logged")
    warning_path = os.path.join(result.run_dir, "attempt_001_warning.json")
    if os.path.exists(warning_path):
        warning = _read_json(warning_path)
        print("warning generated from failure family:")
        print(f"  {warning['message']}")
    print("both attempts preserved:")
    for name in (
        "attempt_001_raw_source.json",
        "attempt_001_candidate.json",
        "attempt_001_provenance.json",
        "attempt_001_verdict.json",
        "attempt_001_warning.json",
        "attempt_002_raw_source.json",
        "attempt_002_candidate.json",
        "attempt_002_provenance.json",
        "attempt_002_verdict.json",
        "summary.json",
    ):
        print(f"  {name}: {'yes' if os.path.exists(os.path.join(result.run_dir, name)) else 'no'}")
    print("=" * 48)
    replay_ok = _replay_ok()
    tamper_ok = _tamper_ok()
    print(f"replay still passes: {'yes' if replay_ok else 'no'}")
    print(f"tamper suite still passes: {'yes' if tamper_ok else 'no'}")
    print(f"final status: {result.status}")
    return 0 if result.status == "PASS" and replay_ok and tamper_ok else 2


def _replay_ok():
    out = StringIO()
    with redirect_stdout(out):
        return replay.main() == 0


def _tamper_ok():
    return all(result.passed for result in tamper.run_tamper_checks(ROOT))


if __name__ == "__main__":
    sys.exit(main())
