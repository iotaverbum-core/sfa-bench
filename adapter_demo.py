#!/usr/bin/env python3
"""Run the v1.0.0 optional adapter boundary demo."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from sfa import adapters
from sfa import families as fam_mod
from sfa import invariants as invariants_mod
from sfa import rederive as rederive_mod
from sfa import transcript as transcript_mod
from sfa import verifier as verifier_mod


ROOT = Path(__file__).resolve().parent
CASE_DIR = ROOT / "cases" / "external_candidate_001"
REPLAY_RECORD = ROOT / "examples" / "external_transcripts" / "bad_transcript.replay.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    demo_env = {"CI": os.environ.get("CI", "")}
    adapter = adapters.select_adapter(env=demo_env)
    request = adapters.AdapterRequest(
        case_id="external_candidate_001",
        prompt={
            "text": "Answer the contract approval question using the supplied facts.",
            "prompt_hash": "fixture-prompt-hash-contract-status-v0",
        },
    )

    input_obj = _read_json(CASE_DIR / "input.json")
    evidence_obj = _read_json(CASE_DIR / "evidence.json")
    rules_obj = _read_json(CASE_DIR / "verifier_rules.json")

    raw = adapter.produce_transcript(request)
    adapters.assert_transcript_raw_source(raw)
    normalized = transcript_mod.normalize_transcript(
        raw,
        input_obj=input_obj,
        evidence_obj=evidence_obj,
        rules_obj=rules_obj,
    )
    verdict = verifier_mod.verify(input_obj, evidence_obj, normalized.candidate, rules_obj)
    family = fam_mod.classify_family(verdict.category, normalized.candidate, evidence_obj) if verdict.status == "FAIL" else None

    rederived = rederive_mod.rederive_record(str(REPLAY_RECORD), str(ROOT))
    rederived_ok = rederived.passed and rederived.verdict == verdict.to_dict()

    metadata_blind = invariants_mod.run_adapter_metadata_blindness_case(
        input_obj=input_obj,
        evidence_obj=evidence_obj,
        rules_obj=rules_obj,
    ).matched
    invariants_mod.assert_verifier_callsite_guard(ROOT)

    transcript_produced = raw.get("schema") == transcript_mod.TRANSCRIPT_SCHEMA
    candidate_normalized = isinstance(normalized.candidate, dict)
    verifier_received_metadata = not metadata_blind

    print("SFA-Bench v1.0.0 adapter boundary demo")
    print("=" * 56)
    print(f"adapter selected: {adapter.spec.adapter_id}")
    print(f"adapter mode: {adapter.spec.mode}")
    print(f"live adapters enabled: {'yes' if adapters.live_adapters_enabled(demo_env) else 'no'}")
    print(f"ci safe: {'yes' if adapter.spec.ci_allowed else 'no'}")
    print(f"transcript produced: {'yes' if transcript_produced else 'no'}")
    print(f"candidate normalized: {'yes' if candidate_normalized else 'no'}")
    verdict_line = f"verdict: {verdict.status}"
    if verdict.status == "FAIL":
        verdict_line += f" {verdict.category} / {family}"
    print(verdict_line)
    print(f"re-derived verdict matches sealed normalized inputs: {'yes' if rederived_ok else 'no'}")
    print(f"verifier received adapter metadata: {'yes' if verifier_received_metadata else 'no'}")
    print("=" * 56)

    final_ok = (
        adapter.spec.adapter_id == adapters.DEFAULT_ADAPTER_ID
        and not adapter.spec.is_live
        and adapter.spec.ci_allowed
        and not adapters.live_adapters_enabled(demo_env)
        and transcript_produced
        and candidate_normalized
        and rederived_ok
        and metadata_blind
    )
    print(f"final status: {'PASS' if final_ok else 'FAIL'}")
    return 0 if final_ok else 2


if __name__ == "__main__":
    sys.exit(main())
