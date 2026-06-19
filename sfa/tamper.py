"""Temporary corruption checks for SFA-Bench.

The helpers in this module copy repository state into a temporary workspace,
mutate only that copy, and run read-only validations against the copy. They are
guards against silent corruption, not repair tools.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import builtins
import json
import os
import shutil
import uuid

from . import artifact as artifact_mod
from . import case as case_mod
from . import families as fam_mod
from . import hashing
from . import invariants as invariants_mod
from . import ledger as ledger_mod
from . import rederive as rederive_mod
from . import validation
from . import verifier as verifier_mod


@dataclass(frozen=True)
class TamperResult:
    name: str
    passed: bool
    detail: str = ""


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _mutate_json(path, mutator):
    obj = _read_json(path)
    replacement = mutator(obj)
    if replacement is not None:
        obj = replacement
    _write_json(path, obj)


def _artifact_paths(root):
    artifacts_dir = os.path.join(root, "artifacts")
    if not os.path.isdir(artifacts_dir):
        return []
    return [
        os.path.join(artifacts_dir, name)
        for name in sorted(os.listdir(artifacts_dir))
        if name.endswith(".sealed.json")
    ]


def _artifacts_dir(root):
    return os.path.join(root, "artifacts")


def _cases_dir(root):
    return os.path.join(root, "cases")


def _families_path(root):
    return os.path.join(root, "families.json")


def _ledger_path(root):
    return os.path.join(root, "history", "occurrences.jsonl")


_COPY_DIRS = ("cases", "artifacts", "history", "sfa", "examples")
_COPY_FILES = (
    "families.json",
    "history_config.json",
    "run_benchmark.py",
    "replay.py",
    "report.py",
)
_IGNORE_NAMES = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "tmp",
    "temp",
    ".DS_Store",
    "*.pyc",
)


@contextmanager
def temp_workspace(source_root):
    """Copy repository state into a temporary workspace and clean it up."""
    temp_parent = os.path.join(source_root, ".tamper-tmp")
    os.makedirs(temp_parent, exist_ok=True)
    tmp = os.path.join(temp_parent, "sfa-tamper-" + uuid.uuid4().hex)
    os.makedirs(tmp, exist_ok=False)
    try:
        dest = os.path.join(tmp, "workspace")
        _copy_benchmark_state(source_root, dest)
        ensure_valid_state(dest)
        yield dest
    finally:
        _remove_owned_temp_tree(tmp, temp_parent)


def _remove_owned_temp_tree(target, temp_parent):
    target_resolved = os.path.abspath(target)
    parent_resolved = os.path.abspath(temp_parent)
    if not target_resolved.startswith(parent_resolved + os.sep):
        raise RuntimeError(f"refusing to remove temp tree outside {parent_resolved}: {target_resolved}")
    if os.path.basename(target_resolved).startswith("sfa-tamper-") and os.path.exists(target_resolved):
        shutil.rmtree(target_resolved, ignore_errors=True)


def _copy_benchmark_state(source_root, dest):
    """Copy only auditable benchmark state needed by tamper checks."""
    os.makedirs(dest, exist_ok=True)
    ignore = shutil.ignore_patterns(*_IGNORE_NAMES)

    for dirname in _COPY_DIRS:
        src = os.path.join(source_root, dirname)
        dst = os.path.join(dest, dirname)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=ignore)
        else:
            os.makedirs(dst, exist_ok=True)

    for filename in _COPY_FILES:
        src = os.path.join(source_root, filename)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, filename))


def ensure_valid_state(root):
    """Ensure the temp copy is already valid enough for tamper checks."""
    if not _artifact_paths(root):
        raise RuntimeError("temp benchmark state has no sealed artifacts")
    try:
        ledger_entries = ledger_mod.read_ledger(_ledger_path(root))
    except ValueError as exc:
        raise RuntimeError(f"temp benchmark ledger is invalid: {exc}") from exc
    if len(ledger_entries) < 2:
        raise RuntimeError("temp benchmark state has fewer than two ledger entries")


def _first_artifact_with_case(root):
    for path in _artifact_paths(root):
        art = _read_json(path)
        if os.path.isdir(os.path.join(_cases_dir(root), art.get("case_id", ""))):
            return path
    raise RuntimeError("no artifact with a matching case directory")


def _first_failing_case(root):
    for case_dir in case_mod.discover_cases(_cases_dir(root)):
        inp, ev, cand, rules = case_mod.load_verification_inputs(case_dir)
        verdict = verifier_mod.verify(inp, ev, cand, rules)
        if verdict.status == "FAIL":
            return case_dir, inp, ev, cand, rules, verdict
    raise RuntimeError("no failing case available for hidden repair guard")


def _issue_codes(issues):
    return {issue.code for issue in issues}


def _passes_on_issue(issues, *codes):
    present = _issue_codes(issues)
    if present.intersection(codes):
        return True, ""
    if not issues:
        return False, "no validation issue was reported"
    return False, "reported " + ", ".join(sorted(present))


def _result_from_issues(name, issues, *codes):
    passed, detail = _passes_on_issue(issues, *codes)
    return TamperResult(name, passed, detail)


def edited_artifact_detected(source_root):
    name = "edited artifact detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)

        def tamper(art):
            art["failure_explanation"] = art.get("failure_explanation", "") + " tampered"

        _mutate_json(artifact_path, tamper)
        issues = validation.validate_artifact_integrity(artifact_path)
        return _result_from_issues(name, issues, "seal_hash_mismatch")


def edited_evidence_detected(source_root):
    name = "edited evidence detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)
        art = _read_json(artifact_path)
        evidence_path = os.path.join(_cases_dir(root), art["case_id"], "evidence.json")

        def tamper(evidence):
            evidence["_tamper_marker"] = "edited evidence"

        _mutate_json(evidence_path, tamper)
        issues = validation.validate_case_hashes(artifact_path, _cases_dir(root))
        return _result_from_issues(name, issues, "evidence_hash_mismatch")


def edited_candidate_detected(source_root):
    name = "edited candidate detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)
        art = _read_json(artifact_path)
        candidate_path = os.path.join(_cases_dir(root), art["case_id"], "candidate_answer.json")

        def tamper(candidate):
            candidate["_tamper_marker"] = "edited candidate"

        _mutate_json(candidate_path, tamper)
        issues = validation.validate_case_hashes(artifact_path, _cases_dir(root))
        return _result_from_issues(name, issues, "candidate_hash_mismatch")


def edited_input_detected(source_root):
    name = "edited input detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)
        art = _read_json(artifact_path)
        input_path = os.path.join(_cases_dir(root), art["case_id"], "input.json")

        def tamper(input_obj):
            input_obj["_tamper_marker"] = "edited input"

        _mutate_json(input_path, tamper)
        issues = validation.validate_case_hashes(artifact_path, _cases_dir(root))
        return _result_from_issues(name, issues, "input_hash_mismatch")


def deleted_ledger_entry_detected(source_root):
    name = "deleted ledger entry detected"
    with temp_workspace(source_root) as root:
        path = _ledger_path(root)
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) < 2:
            return TamperResult(name, False, "need at least two ledger entries")
        del lines[0]
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        issues = validation.validate_ledger_chain(path)
        return _result_from_issues(
            name,
            issues,
            "ledger_chain_broken",
            "ledger_seq_mismatch",
            "ledger_entry_hash_mismatch",
        )


def reordered_ledger_entry_detected(source_root):
    name = "reordered ledger entry detected"
    with temp_workspace(source_root) as root:
        path = _ledger_path(root)
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) < 2:
            return TamperResult(name, False, "need at least two ledger entries")
        lines[0], lines[1] = lines[1], lines[0]
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        issues = validation.validate_ledger_chain(path)
        return _result_from_issues(
            name,
            issues,
            "ledger_chain_broken",
            "ledger_seq_mismatch",
            "ledger_entry_hash_mismatch",
        )


def edited_ledger_entry_detected(source_root):
    name = "edited ledger entry detected"
    with temp_workspace(source_root) as root:
        path = _ledger_path(root)
        entries = ledger_mod.read_ledger(path)
        if not entries:
            return TamperResult(name, False, "ledger is empty")
        entries[0]["run_id"] = entries[0].get("run_id", "") + "-tampered"
        with open(path, "w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
        issues = validation.validate_ledger_chain(path)
        return _result_from_issues(name, issues, "ledger_entry_hash_mismatch")


def fake_lineage_parent_detected(source_root):
    name = "fake lineage parent detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)

        def tamper(art):
            art["parent_artifact_id"] = "0" * 64

        _mutate_json(artifact_path, tamper)
        issues = validation.validate_lineage_parents(_artifacts_dir(root))
        return _result_from_issues(name, issues, "missing_lineage_parent")


def taxonomy_drift_detected(source_root):
    name = "taxonomy drift detected"
    with temp_workspace(source_root) as root:
        artifact_path = _first_artifact_with_case(root)
        used_family = _read_json(artifact_path)["failure_family"]
        families_path = _families_path(root)

        def tamper(taxonomy):
            taxonomy["families"] = [
                family for family in taxonomy.get("families", []) if family.get("id") != used_family
            ]

        _mutate_json(families_path, tamper)
        issues = []
        issues.extend(
            validation.validate_taxonomy_references(
                families_path,
                artifacts_dir=_artifacts_dir(root),
                ledger_path=_ledger_path(root),
            )
        )
        issues.extend(
            validation.validate_taxonomy_ancestry_consistency(
                families_path,
                baseline_taxonomy_path=_families_path(source_root),
            )
        )
        return _result_from_issues(
            name,
            issues,
            "taxonomy_invalid",
            "taxonomy_missing_required_family",
            "unknown_artifact_family",
            "unknown_ledger_family",
            "taxonomy_family_removed",
        )


def edited_transcript_raw_source_detected(source_root):
    name = "edited transcript raw source detected"
    with temp_workspace(source_root) as root:
        record_path = _first_transcript_replay_record(root)
        record = _read_json(record_path)
        transcript_path = os.path.join(root, record["transcript_path"])

        def tamper(transcript):
            transcript["raw_response"] = transcript["raw_response"] + "\nTampered wrapper text."

        _mutate_json(transcript_path, tamper)
        result = rederive_mod.rederive_record(record_path, root)
        return _result_from_rederive_issues(name, result.issues, "raw_source_hash_mismatch")


def edited_transcript_normalized_hash_detected(source_root):
    name = "edited transcript normalized hash detected"
    with temp_workspace(source_root) as root:
        record_path = _first_transcript_replay_record(root)

        def tamper(record):
            record["expected"]["normalized_candidate_hash"] = "0" * 64

        _mutate_json(record_path, tamper)
        result = rederive_mod.rederive_record(record_path, root)
        return _result_from_rederive_issues(name, result.issues, "normalized_candidate_hash_mismatch")


def live_adapter_ci_guard_passed(source_root):
    name = "live adapter CI guard passed"
    invariants_mod.assert_ci_live_adapter_unreachable()
    return TamperResult(name, True)


def adapter_metadata_blindness_guard_passed(source_root):
    name = "adapter metadata blindness guard passed"
    case_dir = os.path.join(_cases_dir(source_root), "external_candidate_001")
    result = invariants_mod.run_adapter_metadata_blindness_case(
        input_obj=_read_json(os.path.join(case_dir, "input.json")),
        evidence_obj=_read_json(os.path.join(case_dir, "evidence.json")),
        rules_obj=_read_json(os.path.join(case_dir, "verifier_rules.json")),
    )
    return TamperResult(name, result.matched)


def gold_leakage_guard_passed(source_root):
    name = "gold leakage guard passed"
    with temp_workspace(source_root) as root:
        case_dir = case_mod.discover_cases(_cases_dir(root))[0]
        inp, ev, cand, rules = case_mod.load_verification_inputs(case_dir)
        baseline = verifier_mod.verify(inp, ev, cand, rules).to_dict()

        expected_path = os.path.join(case_dir, "expected_verdict.json")
        _write_json(
            expected_path,
            {
                "status": "ABSURD_GOLD_SHOULD_NOT_BE_READ",
                "category": "ABSURD_GOLD_SHOULD_NOT_BE_READ",
            },
        )

        original_open = builtins.open

        def guarded_open(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and os.path.basename(os.fspath(file)) == "expected_verdict.json":
                raise AssertionError("verifier path attempted to read expected_verdict.json")
            return original_open(file, *args, **kwargs)

        try:
            builtins.open = guarded_open
            inp2, ev2, cand2, rules2 = case_mod.load_verification_inputs(case_dir)
            after = verifier_mod.verify(inp2, ev2, cand2, rules2).to_dict()
        except AssertionError as exc:
            return TamperResult(name, False, str(exc))
        finally:
            builtins.open = original_open

        if after != baseline:
            return TamperResult(name, False, f"verifier changed from {baseline} to {after}")
        return TamperResult(name, True)


def hidden_repair_guard_passed(source_root):
    name = "hidden repair guard passed"
    with temp_workspace(source_root) as root:
        case_dir, inp, ev, cand, _rules, verdict = _first_failing_case(root)
        case_id = case_mod.case_id_of(case_dir)
        candidate_path = os.path.join(case_dir, "candidate_answer.json")

        with open(candidate_path, "rb") as fh:
            before_bytes = fh.read()
        before_files = _relative_files(case_dir)

        family = fam_mod.classify_family(verdict.category, cand, ev)
        sealed = artifact_mod.seal_failure(
            case_id,
            inp,
            ev,
            cand,
            verifier_mod.VERIFIER_VERSION,
            verdict.category,
            family,
            verdict.explanation,
            sealed_at="2026-01-01T00:00:00+00:00",
        )
        artifact_path = os.path.join(_artifacts_dir(root), case_id + ".hidden-repair-check.sealed.json")
        _write_json(artifact_path, sealed)

        with open(candidate_path, "rb") as fh:
            after_bytes = fh.read()
        after_files = _relative_files(case_dir)

        issues = validation.validate_artifact_integrity(artifact_path)
        if issues:
            return TamperResult(name, False, "sealed artifact failed integrity")
        if verdict.status != "FAIL":
            return TamperResult(name, False, "selected candidate did not fail")
        if before_bytes != after_bytes:
            return TamperResult(name, False, "candidate file was modified")
        if before_files != after_files:
            return TamperResult(name, False, "case directory files changed")
        if sealed["candidate_hash"] != hashing.sha256_hex(_read_json(candidate_path)):
            return TamperResult(name, False, "artifact did not hash the original candidate")
        return TamperResult(name, True)


def _relative_files(root):
    out = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            out.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(out)


def _first_transcript_replay_record(root):
    base = os.path.join(root, "examples", "external_transcripts")
    for name in sorted(os.listdir(base)):
        if name.endswith(".replay.json"):
            return os.path.join(base, name)
    raise RuntimeError("no transcript replay record available for tamper check")


def _result_from_rederive_issues(name, issues, *codes):
    present = {issue["code"] for issue in issues}
    if present.intersection(codes):
        return TamperResult(name, True)
    if not issues:
        return TamperResult(name, False, "no re-derivation issue was reported")
    return TamperResult(name, False, "reported " + ", ".join(sorted(present)))


CHECKS = (
    edited_artifact_detected,
    edited_evidence_detected,
    edited_candidate_detected,
    edited_input_detected,
    deleted_ledger_entry_detected,
    reordered_ledger_entry_detected,
    edited_ledger_entry_detected,
    fake_lineage_parent_detected,
    taxonomy_drift_detected,
    edited_transcript_raw_source_detected,
    edited_transcript_normalized_hash_detected,
    live_adapter_ci_guard_passed,
    adapter_metadata_blindness_guard_passed,
    gold_leakage_guard_passed,
    hidden_repair_guard_passed,
)


def run_tamper_checks(source_root):
    results = []
    for check in CHECKS:
        try:
            results.append(check(source_root))
        except Exception as exc:  # noqa: BLE001 - suite reports failures instead of crashing mid-run.
            fallback_name = check.__name__.replace("_", " ")
            results.append(TamperResult(fallback_name, False, str(exc)))
    return results
