#!/usr/bin/env python3
"""SFA-Bench v1.1.0 runner.

Pipeline per case, enforced structurally:
  1. Load verification inputs ONLY (no expected verdict).
  2. Produce a verdict from evidence + rules.
  3. Classify the failure into a family.
  4. Seal a failure artifact for every FAIL, append-only.
  5. Append an occurrence to the hash-chained ledger.
  6. ONLY THEN load expected_verdict.json to score the verifier.

Run:  python run_benchmark.py
"""
from datetime import datetime, timezone
import json
import os
import sys

from sfa import artifact as artifact_mod
from sfa import case as case_mod
from sfa import families as fam_mod
from sfa import history as history_mod
from sfa import ledger as ledger_mod
from sfa import verifier as verifier_mod

ROOT = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(ROOT, "cases")
ARTIFACTS_DIR = os.path.join(ROOT, "artifacts")
LEDGER_PATH = os.path.join(ROOT, "history", "occurrences.jsonl")
FAMILIES_PATH = os.path.join(ROOT, "families.json")
CONFIG_PATH = os.path.join(ROOT, "history_config.json")


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _lineage_depth_for_parent(parent_hash):
    if not parent_hash:
        return 0
    if not os.path.isdir(ARTIFACTS_DIR):
        return 1
    for name in os.listdir(ARTIFACTS_DIR):
        if not name.endswith(".sealed.json"):
            continue
        with open(os.path.join(ARTIFACTS_DIR, name), encoding="utf-8") as fh:
            art = json.load(fh)
        if art.get("artifact_hash") == parent_hash:
            return int(art.get("lineage_depth", 0)) + 1
    return 1


def seal_or_confirm(case_id, inp, ev, cand, verdict, family, parent_artifact_id=None):
    """Append-only sealing.

    If an artifact already exists, confirm it is intact and still matches the
    current case instead of overwriting it. This is what no rewritten history
    means operationally.
    """
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    path = os.path.join(ARTIFACTS_DIR, case_id + ".sealed.json")
    fresh = artifact_mod.seal_failure(
        case_id, inp, ev, cand,
        verifier_mod.VERIFIER_VERSION, verdict.category, family, verdict.explanation,
        parent_artifact_id=parent_artifact_id,
        lineage_depth=_lineage_depth_for_parent(parent_artifact_id),
    )
    if not os.path.exists(path):
        _write_json(path, fresh)
        return "sealed", path, fresh

    with open(path, encoding="utf-8") as fh:
        existing = json.load(fh)
    intact, _ = artifact_mod.verify_artifact_integrity(existing)
    existing_family = existing.get("failure_family") or fam_mod.CATEGORY_TO_FAMILY.get(existing.get("failure_category"), "uncategorized")
    consistent = (
        existing.get("input_hash") == fresh["input_hash"]
        and existing.get("evidence_hash") == fresh["evidence_hash"]
        and existing.get("candidate_hash") == fresh["candidate_hash"]
        and existing.get("failure_category") == fresh["failure_category"]
        and existing_family == fresh["failure_family"]
    )
    if intact and consistent:
        return "exists-consistent", path, existing
    return "DIVERGENCE", path, existing


def append_observation(artifact, verdict, family, observed_at, run_id, config):
    granularity = config.get("period_granularity", "year")
    return ledger_mod.append_occurrence(
        LEDGER_PATH,
        artifact_hash=artifact["artifact_hash"],
        case_id=artifact["case_id"],
        category=verdict.category,
        family=family,
        observed_at=observed_at,
        period=history_mod.period_of(observed_at, granularity),
        run_id=run_id,
        synthetic=False,
    )


def main():
    config = _load_config()
    taxonomy, taxonomy_version = fam_mod.load_taxonomy(FAMILIES_PATH)
    case_dirs = case_mod.discover_cases(CASES_DIR)
    if not case_dirs:
        print("No cases found under", CASES_DIR)
        return 1

    observed_at = datetime.now(timezone.utc).isoformat()
    run_id = "RUN-" + observed_at

    print("SFA-Bench v1.1.0   verifier:", verifier_mod.VERIFIER_VERSION)
    print("taxonomy:", taxonomy_version)
    print("run_id:", run_id)
    print("=" * 74)

    scored = matched = sealed_count = divergences = ledger_count = 0

    for case_dir in case_dirs:
        cid = case_mod.case_id_of(case_dir)

        # --- verification: evidence + rules only, no gold ---
        inp, ev, cand, rules = case_mod.load_verification_inputs(case_dir)
        verdict = verifier_mod.verify(inp, ev, cand, rules)

        line = f"{cid:<34} {verdict.status:<4}"
        if verdict.status == "FAIL":
            family = fam_mod.classify_family(verdict.category, cand, ev)
            line += f" {verdict.category} / {family}"
            state, path, artifact = seal_or_confirm(cid, inp, ev, cand, verdict, family)
            if state == "sealed":
                sealed_count += 1
            elif state == "DIVERGENCE":
                divergences += 1
            if state != "DIVERGENCE":
                append_observation(artifact, verdict, family, observed_at, run_id, config)
                ledger_count += 1
            line += f" [{state}]"
        print(line)

        # --- scoring: gold may be loaded only after verdict exists ---
        expected = case_mod.load_expected_verdict(case_dir)
        scored += 1
        if verdict.status == expected.get("status") and verdict.category == expected.get("category"):
            matched += 1
        else:
            print("  SCORE MISMATCH expected", expected, "got", verdict.to_dict())

    print("=" * 74)
    print(f"score: {matched}/{scored} matched expected verdicts")
    print(f"new sealed artifacts: {sealed_count}")
    print(f"ledger observations appended: {ledger_count}")
    if divergences:
        print(f"DIVERGENCES: {divergences} existing artifact(s) no longer match current cases")
        print("Run python replay.py for details. Do not overwrite sealed artifacts.")
        return 2
    print("Run python replay.py to re-attest artifacts and the ledger chain.")
    print("Run python report.py to inspect failure history.")
    return 0 if matched == scored else 1


if __name__ == "__main__":
    sys.exit(main())
