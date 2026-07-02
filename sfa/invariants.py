"""Invariant checks for the verifier trust boundary.

These helpers are test code, not verifier behavior. They deliberately keep the
verifier under test behind subprocess calls so ambient files in the working
directory can vary while the fixed verification payload stays identical.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import ast
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tokenize
from typing import Any
import uuid


FORBIDDEN_VERIFIER_REFERENCES = (
    "history",
    "ledger",
    "artifacts",
    "agent_runs",
    "adapter_runs",
    "provenance",
    "warnings",
    "warning",
    "agent",
    "model_adapter",
    "raw_source",
    "raw_response",
    "transcript",
    "prompt",
    "model_id",
    "provider",
    "temperature",
    "top_p",
    "adapter",
    "fingerprint",
    "recurrence",
    "prior_failures",
    "sampling_params",
    "policy_decisions",
    "policy",
    "policy_input",
    "policy_decision",
    "directive",
    "directives",
    "retry_count",
    "remediation",
    "caution",
)

FORBIDDEN_VERIFIER_CALL_ARGUMENTS = (
    "raw_source",
    "raw_response",
    "transcript",
    "prompt",
    "model_id",
    "provider",
    "temperature",
    "top_p",
    "adapter",
    "warning",
    "history",
    "provenance",
    "adapter_runs",
    "fingerprint",
    "recurrence",
    "prior_failures",
    "sampling_params",
    "policy_decisions",
    "policy",
    "policy_input",
    "policy_decision",
    "directive",
    "directives",
    "retry_count",
    "remediation",
    "caution",
)


class InvariantFailure(AssertionError):
    """Raised when a verifier invariant is violated."""


@dataclass(frozen=True)
class ForbiddenReference:
    term: str
    kind: str
    line: int
    text: str


@dataclass(frozen=True)
class HistoryBlindnessResult:
    name: str
    empty_output: dict[str, Any]
    populated_output: dict[str, Any]

    @property
    def matched(self) -> bool:
        return self.empty_output == self.populated_output


def find_forbidden_verifier_references(verifier_path: str | Path) -> list[ForbiddenReference]:
    """Return forbidden import/reference hits in sfa/verifier.py.

    The scan is intentionally strict: import statements, identifiers, attribute
    names, string literals, and comments are checked for exact forbidden terms.
    """
    path = Path(verifier_path)
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    forbidden = {term.lower() for term in FORBIDDEN_VERIFIER_REFERENCES}
    hits: list[ForbiddenReference] = []

    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for part in alias.name.split("."):
                    if part.lower() in forbidden:
                        hits.append(_hit(part, "import", node.lineno, lines))
                if alias.asname and alias.asname.lower() in forbidden:
                    hits.append(_hit(alias.asname, "import-alias", node.lineno, lines))
        elif isinstance(node, ast.ImportFrom):
            module_parts = (node.module or "").split(".")
            for part in module_parts:
                if part.lower() in forbidden:
                    hits.append(_hit(part, "import-from", node.lineno, lines))
            for alias in node.names:
                if alias.name.lower() in forbidden:
                    hits.append(_hit(alias.name, "import-from", node.lineno, lines))
                if alias.asname and alias.asname.lower() in forbidden:
                    hits.append(_hit(alias.asname, "import-alias", node.lineno, lines))

    stream = io.StringIO(source)
    for token in tokenize.generate_tokens(stream.readline):
        if token.type == tokenize.NAME and token.string.lower() in forbidden:
            hits.append(_hit(token.string, "identifier", token.start[0], lines))
        elif token.type in (tokenize.STRING, tokenize.COMMENT):
            for term in FORBIDDEN_VERIFIER_REFERENCES:
                if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", token.string, re.IGNORECASE):
                    kind = "string" if token.type == tokenize.STRING else "comment"
                    hits.append(_hit(term, kind, token.start[0], lines))

    return _dedupe_hits(hits)


def assert_verifier_static_guard(verifier_path: str | Path) -> None:
    hits = find_forbidden_verifier_references(verifier_path)
    if hits:
        detail = "\n".join(
            f"{hit.line}: {hit.kind} reference to '{hit.term}': {hit.text}"
            for hit in hits
        )
        raise InvariantFailure(
            "sfa/verifier.py references forbidden history-adjacent symbols:\n" + detail
        )


def assert_verifier_callsite_guard(repo_root: str | Path) -> None:
    hits = find_forbidden_verifier_call_arguments(repo_root)
    if hits:
        detail = "\n".join(
            f"{hit.line}: {hit.kind} reference to '{hit.term}': {hit.text}"
            for hit in hits
        )
        raise InvariantFailure(
            "verifier call sites pass forbidden transcript-adjacent symbols:\n" + detail
        )


def find_forbidden_verifier_call_arguments(repo_root: str | Path) -> list[ForbiddenReference]:
    root = Path(repo_root)
    hits: list[ForbiddenReference] = []
    forbidden = {term.lower() for term in FORBIDDEN_VERIFIER_CALL_ARGUMENTS}
    for path in _python_files(root):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_verifier_call(node):
                continue
            segments = []
            for arg in node.args:
                segments.append(ast.get_source_segment(source, arg) or "")
            for keyword in node.keywords:
                segments.append(ast.get_source_segment(source, keyword.value) or "")
            for segment in segments:
                for term in forbidden:
                    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", segment, re.IGNORECASE):
                        hits.append(_hit(term, "verify-call-argument", node.lineno, lines))
    return _dedupe_hits(hits)


def run_normalization_isolation_case(
    *,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    rules_obj: dict[str, Any],
) -> HistoryBlindnessResult:
    from sfa import transcript as transcript_mod
    from sfa import verifier

    candidate_block = (
        "```json\n"
        "{\n"
        "  \"conclusion\": \"The contract approval status is pending.\",\n"
        "  \"cited_evidence\": [\"f2\"],\n"
        "  \"claims\": [{\"subject\": \"approval_status\", \"value\": \"pending\"}]\n"
        "}\n"
        "```"
    )
    transcript_a = _isolation_transcript(
        provider="fixture-provider-a",
        model_id="fixture-model-a",
        temperature=0,
        raw_response="Candidate follows.\n" + candidate_block + "\nEnd.",
    )
    transcript_b = _isolation_transcript(
        provider="fixture-provider-b",
        model_id="fixture-model-b",
        temperature=0.9,
        raw_response="Different wrapper text.\n" + candidate_block + "\nDifferent ending.",
    )
    norm_a = transcript_mod.normalize_transcript(transcript_a, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)
    norm_b = transcript_mod.normalize_transcript(transcript_b, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)
    if norm_a.candidate_bytes != norm_b.candidate_bytes:
        raise InvariantFailure("normalization isolation fixtures did not produce byte-identical candidates")
    output_a = verifier.verify(input_obj, evidence_obj, norm_a.candidate, rules_obj).to_dict()
    output_b = verifier.verify(input_obj, evidence_obj, norm_b.candidate, rules_obj).to_dict()
    result = HistoryBlindnessResult("normalization isolation", output_a, output_b)
    if not result.matched:
        raise InvariantFailure("verifier output changed with transcript metadata")
    return result


def run_adapter_airlock_case(
    *,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    rules_obj: dict[str, Any],
    repo_root: str | Path,
) -> HistoryBlindnessResult:
    from sfa import adapters
    from sfa import transcript as transcript_mod
    from sfa import verifier

    adapter = adapters.select_adapter(env={})
    if adapter.spec.is_live:
        raise InvariantFailure("default adapter must not be live")

    raw = adapter.produce_transcript(adapters.AdapterRequest(case_id="external_candidate_001"))
    adapters.assert_transcript_raw_source(raw)
    norm_a = transcript_mod.normalize_transcript(raw, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)

    changed = deepcopy(raw)
    changed["metadata"]["adapter_id"] = "tampered-adapter-metadata"
    changed["metadata"]["provider"] = "tampered-provider"
    changed["metadata"]["model_id"] = "tampered-model"
    changed["metadata"]["parameters"] = {"temperature": 0.99, "top_p": 0.5, "seed": 999}
    norm_b = transcript_mod.normalize_transcript(changed, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)
    if norm_a.candidate_bytes != norm_b.candidate_bytes:
        raise InvariantFailure("adapter metadata changed normalized candidate bytes")

    output_a = verifier.verify(input_obj, evidence_obj, norm_a.candidate, rules_obj).to_dict()
    output_b = verifier.verify(input_obj, evidence_obj, norm_b.candidate, rules_obj).to_dict()
    result = HistoryBlindnessResult("adapter airlock", output_a, output_b)
    if not result.matched:
        raise InvariantFailure("verifier output changed with adapter metadata")
    assert_verifier_callsite_guard(repo_root)
    return result


def run_adapter_metadata_blindness_case(
    *,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    rules_obj: dict[str, Any],
) -> HistoryBlindnessResult:
    from sfa import transcript as transcript_mod
    from sfa import verifier

    candidate_block = (
        "```json\n"
        "{\n"
        "  \"conclusion\": \"The contract has been approved.\",\n"
        "  \"cited_evidence\": [\"f2\"],\n"
        "  \"claims\": [{\"subject\": \"approval_status\", \"value\": \"approved\"}]\n"
        "}\n"
        "```"
    )
    transcript_a = _isolation_transcript(
        provider="fixture-provider-a",
        model_id="fixture-model-a",
        temperature=0,
        raw_response="Candidate follows.\n" + candidate_block,
        adapter_id="fixture-transcript-adapter-v0",
    )
    transcript_b = _isolation_transcript(
        provider="fixture-provider-b",
        model_id="fixture-model-b",
        temperature=0.75,
        raw_response="Different wrapper.\n" + candidate_block,
        adapter_id="different-adapter-v0",
    )
    norm_a = transcript_mod.normalize_transcript(transcript_a, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)
    norm_b = transcript_mod.normalize_transcript(transcript_b, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj)
    if norm_a.candidate_bytes != norm_b.candidate_bytes:
        raise InvariantFailure("adapter metadata blindness fixtures did not produce byte-identical candidates")
    output_a = verifier.verify(input_obj, evidence_obj, norm_a.candidate, rules_obj).to_dict()
    output_b = verifier.verify(input_obj, evidence_obj, norm_b.candidate, rules_obj).to_dict()
    result = HistoryBlindnessResult("adapter metadata blindness", output_a, output_b)
    if not result.matched:
        raise InvariantFailure("verifier output changed with adapter/model metadata")
    return result


def run_fingerprint_metadata_blindness_case(
    *,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    rules_obj: dict[str, Any],
) -> HistoryBlindnessResult:
    """Prove reporting metadata changes cannot change verifier judgment."""
    from sfa import transcript as transcript_mod
    from sfa import verifier

    candidate_block = (
        "```json\n"
        "{\"conclusion\":\"The contract approval status is pending.\","
        "\"cited_evidence\":[\"f2\"],"
        "\"claims\":[{\"subject\":\"approval_status\",\"value\":\"pending\"}]}\n"
        "```"
    )
    transcript_a = _isolation_transcript(
        "fixture-provider", "fixture-model-a", 0, candidate_block
    )
    transcript_b = deepcopy(transcript_a)
    transcript_b["metadata"].update(
        {
            "model_id": "fixture-model-b",
            "fingerprint_summary": {"dominant_family": "fabricated_entity"},
            "recurrence_profile": {"fabricated_entity": 99},
            "prior_failures": ["sealed-failure-placeholder"],
            "sampling_params": {"temperature": 1},
            "policy_decisions": ["do-not-pass-to-verifier"],
            "caution": "reporting-only fixture metadata",
        }
    )
    norm_a = transcript_mod.normalize_transcript(
        transcript_a, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj
    )
    norm_b = transcript_mod.normalize_transcript(
        transcript_b, input_obj=input_obj, evidence_obj=evidence_obj, rules_obj=rules_obj
    )
    if norm_a.candidate_bytes != norm_b.candidate_bytes:
        raise InvariantFailure("fingerprint metadata changed normalized candidate bytes")
    output_a = verifier.verify(input_obj, evidence_obj, norm_a.candidate, rules_obj).to_dict()
    output_b = verifier.verify(input_obj, evidence_obj, norm_b.candidate, rules_obj).to_dict()
    result = HistoryBlindnessResult("fingerprint metadata blindness", output_a, output_b)
    if not result.matched:
        raise InvariantFailure("verifier output changed with fingerprint metadata")
    return result


def assert_fingerprint_determinism(repo_root: str | Path) -> None:
    from sfa import fingerprints

    fixture = Path(repo_root) / "examples" / "fingerprints" / "demo_pack" / "fixture_set.json"
    report_a, occurrences_a = fingerprints.derive_fixture_set(fixture, repo_root)
    report_b, occurrences_b = fingerprints.derive_fixture_set(fixture, repo_root)
    if report_a != report_b or occurrences_a != occurrences_b:
        raise InvariantFailure("same sealed fingerprint inputs produced different output")


def assert_fingerprint_fixed_condition_guard(repo_root: str | Path) -> None:
    from sfa import fingerprints

    fixture = Path(repo_root) / "examples" / "fingerprints" / "demo_pack" / "fixture_set.json"
    report, _occurrences = fingerprints.derive_fixture_set(fixture, repo_root)
    for field in ("taxonomy_version", "evidence_pack_id", "prompt_condition_id"):
        changed = deepcopy(report)
        changed["conditions"][field] = changed["conditions"][field] + "-changed"
        try:
            fingerprints.assert_comparable(report, changed)
        except fingerprints.FingerprintError:
            continue
        raise InvariantFailure(f"fingerprint comparison accepted mismatched {field}")


def run_policy_metadata_blindness_case(
    *,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    candidate_obj: dict[str, Any],
    rules_obj: dict[str, Any],
    repo_root: str | Path,
) -> HistoryBlindnessResult:
    """Prove generator guidance is removed before the verifier boundary."""
    from sfa import policy as policy_mod
    from sfa import verifier

    fixture = Path(repo_root) / "examples" / "policy" / "multiple_recurring_families.json"
    sealed_input = policy_mod.load_policy_fixture(fixture)
    decision_a = policy_mod.decide_policy(sealed_input)
    decision_b = deepcopy(decision_a)
    decision_b["generated_caution"] = "different generator-only caution"
    envelope_a = {"candidate": deepcopy(candidate_obj), "guidance": decision_a}
    envelope_b = {"candidate": deepcopy(candidate_obj), "guidance": decision_b}
    candidate_a = envelope_a["candidate"]
    candidate_b = envelope_b["candidate"]
    output_a = verifier.verify(input_obj, evidence_obj, candidate_a, rules_obj).to_dict()
    output_b = verifier.verify(input_obj, evidence_obj, candidate_b, rules_obj).to_dict()
    result = HistoryBlindnessResult("policy metadata blindness", output_a, output_b)
    if not result.matched:
        raise InvariantFailure("verifier output changed with generator-only policy metadata")
    return result


def assert_policy_determinism(repo_root: str | Path) -> None:
    from sfa import policy as policy_mod

    fixture = Path(repo_root) / "examples" / "policy" / "single_recurring_family.json"
    sealed_input = policy_mod.load_policy_fixture(fixture)
    decision_a = policy_mod.decide_policy(sealed_input)
    decision_b = policy_mod.decide_policy(sealed_input)
    if policy_mod.decision_bytes(decision_a) != policy_mod.decision_bytes(decision_b):
        raise InvariantFailure("same sealed policy input produced different decision bytes")


def assert_policy_composition_determinism(repo_root: str | Path) -> None:
    from sfa import policy as policy_mod

    fixture = Path(repo_root) / "examples" / "policy" / "multiple_recurring_families.json"
    sealed_input = policy_mod.load_policy_fixture(fixture)
    decision = policy_mod.decide_policy(sealed_input)
    selected = [item["directive_id"] for item in decision["directives"]]
    expected = ["closed_world_entity", "claim_by_claim_evidence_check"]
    if selected != expected:
        raise InvariantFailure(f"policy composition order changed: {selected!r}")


def assert_policy_escalation_determinism(repo_root: str | Path) -> None:
    from sfa import policy as policy_mod

    base = Path(repo_root) / "examples" / "policy"
    level_2_input = policy_mod.load_policy_fixture(base / "escalation_after_recurrence.json")
    level_2_a = policy_mod.decide_policy(level_2_input)
    level_2_b = policy_mod.decide_policy(level_2_input)
    stop_input = policy_mod.load_policy_fixture(base / "termination.json")
    stop_a = policy_mod.decide_policy(stop_input)
    stop_b = policy_mod.decide_policy(stop_input)
    if level_2_a != level_2_b or level_2_a["escalation_level"] != 2:
        raise InvariantFailure("level-2 escalation is not deterministic")
    if stop_a != stop_b or stop_a["escalation_level"] != 3:
        raise InvariantFailure("level-3 escalation is not deterministic")
    if stop_a["termination_recommended"] is not True:
        raise InvariantFailure("level-3 policy did not fail closed")


def assert_ci_live_adapter_unreachable() -> None:
    from sfa import adapters

    for spec in adapters.all_adapter_specs():
        if spec.is_live and spec.ci_allowed:
            raise InvariantFailure(f"live adapter {spec.adapter_id} is marked CI-safe")

    ci_specs = adapters.list_adapter_specs(env={"CI": "true"})
    live_specs = [spec.adapter_id for spec in ci_specs if spec.is_live]
    if live_specs:
        raise InvariantFailure("CI registry exposed live adapters: " + ", ".join(live_specs))

    default_adapter = adapters.select_adapter(env={"CI": "true"})
    if default_adapter.spec.is_live:
        raise InvariantFailure("CI default adapter is live")

    try:
        adapters.select_adapter(
            env={
                "CI": "true",
                "SFA_ADAPTER": adapters.LIVE_PLACEHOLDER_ADAPTER_ID,
            }
        )
    except adapters.AdapterUnavailableError:
        pass
    else:
        raise InvariantFailure("CI selected a live adapter")

    try:
        adapters.list_adapter_specs(env={"CI": "true", "SFA_ENABLE_LIVE_ADAPTERS": "1"})
    except adapters.AdapterUnavailableError:
        pass
    else:
        raise InvariantFailure("CI allowed live adapter enablement")

    try:
        adapters.LiveAdapterPlaceholder().produce_transcript(
            adapters.AdapterRequest(case_id="external_candidate_001")
        )
    except adapters.AdapterUnavailableError:
        pass
    else:
        raise InvariantFailure("live placeholder did not fail closed")


RELEASE_GATE_FILENAME = "release_gate.py"
PACKAGE_INIT_RELATIVE = ("sfa", "__init__.py")
_PACKAGE_VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
_HEADER_VERSION_RE = re.compile(
    r"print\(\s*(?:f)?[\"']#?\s*(?:SFA-Bench|SFA-Agent)\s+v(\d+\.\d+(?:\.\d+)?)",
    re.MULTILINE,
)


def _read_package_version(init_path: Path) -> str | None:
    if not init_path.is_file():
        return None
    match = _PACKAGE_VERSION_RE.search(init_path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _read_release_gate_constants(gate_path: Path) -> tuple[str, list[str]]:
    tree = ast.parse(gate_path.read_text(encoding="utf-8"), filename=str(gate_path))
    expected: Any = None
    command_files: list[str] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "EXPECTED_RELEASE" and isinstance(node.value, ast.Constant):
                expected = node.value.value
            elif target.id == "COMMAND_FILES" and isinstance(node.value, (ast.Tuple, ast.List)):
                command_files = [
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                ]
    if not isinstance(expected, str):
        raise InvariantFailure("release_gate.py does not define EXPECTED_RELEASE")
    if not command_files:
        raise InvariantFailure("release_gate.py does not define COMMAND_FILES")
    return expected, command_files


def assert_prior_state_trial_determinism(repo_root: str | Path) -> dict[str, Any]:
    """Prior State Trial: byte-identical replay, and the headline delta equals the
    difference of arm means (a pure verifier-scored function of the seed)."""
    from sfa import prior_state_trial as trial

    config = {"seed": 20260101, "n": 12, "bootstrap": 200}
    first = trial.run_trial(config)
    second = trial.run_trial(config)
    if first["report_sha"] != second["report_sha"]:
        raise InvariantFailure("prior state trial is not deterministic (report_sha differs)")

    replayed = trial.replay(first)
    if not replayed["attested"]:
        raise InvariantFailure("prior state trial replay failed: " + "; ".join(replayed["issues"]))

    head = first["headline"]
    arms = first["arms"]
    delta = arms["true_prior"]["mean_score"] - arms["placebo_prior"]["mean_score"]
    if abs(delta - head["delta_mean"]) > 1e-9:
        raise InvariantFailure("prior state trial headline delta is inconsistent with arm means")
    return {"report_sha": first["report_sha"], "delta_mean": head["delta_mean"]}


def assert_repository_version_consistency(repo_root: str | Path) -> dict[str, Any]:
    """Fail closed when the version of record drifts across the repository.

    The package ``sfa.__version__``, the release gate's ``EXPECTED_RELEASE``, and
    every user-facing command header must declare the same release. This encodes a
    known procedural failure: a stale package version that every green check misses
    because nothing compares it against the declared release.
    """
    root = Path(repo_root)
    expected_release, command_files = _read_release_gate_constants(root / RELEASE_GATE_FILENAME)
    package_version = _read_package_version(root.joinpath(*PACKAGE_INIT_RELATIVE))
    if package_version is None:
        raise InvariantFailure("sfa/__init__.py declares no __version__")
    package_label = f"v{package_version}"
    if package_label != expected_release:
        raise InvariantFailure(
            f"package __version__ {package_label!r} does not match release "
            f"gate EXPECTED_RELEASE {expected_release!r}"
        )

    issues: list[str] = []
    for relative in command_files:
        path = root / relative
        if not path.is_file():
            issues.append(f"{relative}: command file missing")
            continue
        labels = {
            f"v{version}"
            for version in _HEADER_VERSION_RE.findall(path.read_text(encoding="utf-8"))
        }
        if not labels:
            issues.append(f"{relative}: no versioned command header")
        elif labels != {expected_release}:
            wrong = ", ".join(sorted(labels - {expected_release}))
            issues.append(f"{relative}: header version {wrong} != {expected_release}")
    if issues:
        raise InvariantFailure(
            "command headers disagree with the release version:\n" + "\n".join(issues)
        )
    return {
        "expected_release": expected_release,
        "package_version": package_version,
        "command_files_checked": len(command_files),
    }


def run_history_blindness_case(
    *,
    name: str,
    input_obj: dict[str, Any],
    evidence_obj: dict[str, Any],
    candidate_obj: dict[str, Any],
    rules_obj: dict[str, Any],
    repo_root: str | Path,
) -> HistoryBlindnessResult:
    """Verify identical payloads with empty vs populated surrounding history."""
    payload = {
        "input": input_obj,
        "evidence": evidence_obj,
        "candidate": candidate_obj,
        "rules": rules_obj,
    }
    root = Path(repo_root)
    temp_parent = root / ".tamper-tmp" / "invariants"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = temp_parent / f"sfa-invariant-{uuid.uuid4().hex}"
    empty_dir = temp_root / "empty"
    populated_dir = temp_root / "populated"

    try:
        empty_dir.mkdir(parents=True)
        populated_dir.mkdir(parents=True)
        _populate_surrounding_history(populated_dir)
        empty_output = _run_verifier_subprocess(payload, root, empty_dir)
        populated_output = _run_verifier_subprocess(payload, root, populated_dir)
    finally:
        _remove_owned_temp_tree(temp_root, temp_parent)

    result = HistoryBlindnessResult(name, empty_output, populated_output)
    if not result.matched:
        raise InvariantFailure(
            f"{name} changed verifier output when surrounding history was populated"
        )
    return result


def _python_files(root: Path):
    skip_dirs = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".tamper-tmp", "agent_runs", "transcript_runs", "adapter_runs", "fingerprint_runs"}
    for path in root.rglob("*.py"):
        if any(part in skip_dirs for part in path.relative_to(root).parts):
            continue
        yield path


def _is_verifier_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "verify"
        or isinstance(func, ast.Name)
        and func.id == "verify"
    )


def _isolation_transcript(provider: str, model_id: str, temperature: float, raw_response: str, adapter_id: str = "isolation-adapter") -> dict[str, Any]:
    return {
        "schema": "sfa.transcript.v0.1",
        "case_id": "external_candidate_001",
        "metadata": {
            "adapter_id": adapter_id,
            "prompt_template_id": "isolation-template",
            "provider": provider,
            "model_id": model_id,
            "parameters": {
                "temperature": temperature,
                "top_p": 1,
                "seed": 7,
            },
        },
        "prompt": {
            "text": "Different prompt wrapper should not affect verifier judgment.",
            "prompt_hash": provider + "-prompt-hash",
        },
        "raw_response": raw_response,
        "captured_at": "2026-06-18T00:00:00+00:00",
    }


def _remove_owned_temp_tree(target: Path, temp_parent: Path) -> None:
    target_resolved = target.resolve()
    parent_resolved = temp_parent.resolve()
    if parent_resolved not in target_resolved.parents:
        raise InvariantFailure(f"refusing to remove temp tree outside {parent_resolved}: {target_resolved}")
    if target.name.startswith("sfa-invariant-") and target.exists():
        shutil.rmtree(target, ignore_errors=True)


def _hit(term: str, kind: str, line: int, lines: list[str]) -> ForbiddenReference:
    text = lines[line - 1].strip() if 0 < line <= len(lines) else ""
    return ForbiddenReference(term=term, kind=kind, line=line, text=text)


def _dedupe_hits(hits: list[ForbiddenReference]) -> list[ForbiddenReference]:
    seen: set[tuple[str, str, int, str]] = set()
    out: list[ForbiddenReference] = []
    for hit in hits:
        key = (hit.term.lower(), hit.kind, hit.line, hit.text)
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out


def _populate_surrounding_history(root: Path) -> None:
    (root / "history").mkdir()
    (root / "artifacts").mkdir()
    (root / "provenance").mkdir()
    (root / "ledger").mkdir()

    (root / "history" / "occurrences.jsonl").write_text(
        '{"seq":999,"case_id":"ambient-history","entry_hash":"ambient"}\n',
        encoding="utf-8",
    )
    (root / "artifacts" / "ambient.sealed.json").write_text(
        '{"case_id":"ambient-artifact","artifact_hash":"ambient"}\n',
        encoding="utf-8",
    )
    (root / "provenance" / "ambient.json").write_text(
        '{"source":"ambient-provenance"}\n',
        encoding="utf-8",
    )
    (root / "ledger" / "ambient.jsonl").write_text(
        '{"ledger":"ambient"}\n',
        encoding="utf-8",
    )


def _run_verifier_subprocess(payload: dict[str, Any], repo_root: Path, cwd: Path) -> dict[str, Any]:
    code = (
        "import json, sys\n"
        "from sfa import verifier\n"
        "payload = json.loads(sys.stdin.read())\n"
        "verdict = verifier.verify(payload['input'], payload['evidence'], payload['candidate'], payload['rules'])\n"
        "print(json.dumps(verdict.to_dict(), sort_keys=True, separators=(',', ':')))\n"
    )
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(repo_root) if not existing_path else str(repo_root) + os.pathsep + existing_path
    completed = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(payload, sort_keys=True),
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise InvariantFailure(
            "verifier subprocess failed"
            f"\nreturncode: {completed.returncode}"
            f"\nstdout: {completed.stdout.strip()}"
            f"\nstderr: {completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)
