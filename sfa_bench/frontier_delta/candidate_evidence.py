"""Deterministic successor evidence for corrected candidate scoring.

This module only replays preserved response text through score_response.
It has no provider integration, does not mutate historical artifacts, and does
not ratify or promote a result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from sfa.hashing import sha256_hex

from . import candidate_adapter, schemas
from .tasks import TASKS_DIR, load_task, load_tasks


SUCCESSOR_SCHEMA_VERSION = (
    "sfa_bench.frontier_delta.candidate_evidence.successor.v1"
)
DEFAULT_OUTPUT_DIRECTORY = Path("out") / "candidate_evidence_successors"
REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{40}\Z")
_CANDIDATE_EVIDENCE_PATH = "sfa_bench/frontier_delta/candidate_evidence.py"
_BENCHMARK_SOURCE_PATHS = (
    "sfa/hashing.py",
    "sfa_bench/frontier_delta/candidate_adapter.py",
    _CANDIDATE_EVIDENCE_PATH,
    "sfa_bench/frontier_delta/schemas.py",
    "sfa_bench/frontier_delta/scorers/__init__.py",
    "sfa_bench/frontier_delta/scorers/checks.py",
)
_VERIFIER_SOURCE_PATHS = (
    "sfa/hashing.py",
    "sfa/verifier.py",
    "sfa_bench/frontier_delta/schemas.py",
    "sfa_bench/frontier_delta/scorers/__init__.py",
    "sfa_bench/frontier_delta/scorers/checks.py",
)


class CandidateEvidenceError(ValueError):
    """Expected validation failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _NonStandardJsonConstant(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise _NonStandardJsonConstant(
        f"non-standard JSON constant is forbidden: {value}"
    )


def _contains_nonfinite_number(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_nonfinite_number(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite_number(child) for child in value)
    return isinstance(value, float) and not math.isfinite(value)


def _contains_unpaired_surrogate(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_unpaired_surrogate(key)
            or _contains_unpaired_surrogate(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_unpaired_surrogate(child) for child in value)
    return isinstance(value, str) and any(
        0xD800 <= ord(character) <= 0xDFFF for character in value
    )


def _require_finite_numbers(value: Any, *, code: str, label: str) -> None:
    if _contains_nonfinite_number(value):
        raise CandidateEvidenceError(
            code, f"{label} contains a non-finite number"
        )


def _require_unicode_scalars(value: Any, *, code: str, label: str) -> None:
    if _contains_unpaired_surrogate(value):
        raise CandidateEvidenceError(
            code, f"{label} contains an unpaired surrogate code point"
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _captured_task_digest_relation(
    task_path: Path, captured_digest: Any
) -> str:
    if captured_digest is None:
        return "not_recorded"
    if (
        not isinstance(captured_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", captured_digest)
    ):
        raise CandidateEvidenceError(
            "captured_task_digest_invalid",
            f"captured task digest is invalid: {task_path.name}",
        )
    task_bytes = task_path.read_bytes()
    exact_digest = _bytes_sha256(task_bytes)
    if captured_digest == exact_digest:
        return "exact_bytes"
    lf_bytes = task_bytes.replace(b"\r\n", b"\n")
    if captured_digest == _bytes_sha256(lf_bytes):
        return "lf_normalized_equivalent"
    crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
    if captured_digest == _bytes_sha256(crlf_bytes):
        return "crlf_normalized_equivalent"
    raise CandidateEvidenceError(
        "captured_task_digest_mismatch",
        f"captured task digest is unrelated to current bytes: {task_path.name}",
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CandidateEvidenceError(
            f"{label}_invalid_utf8", f"{label} must be UTF-8: {path}"
        ) from exc
    try:
        value = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, _NonStandardJsonConstant) as exc:
        raise CandidateEvidenceError(
            f"{label}_invalid_json", f"{label} is not valid JSON: {path}"
        ) from exc
    _require_finite_numbers(
        value,
        code=f"{label}_invalid_json",
        label=label,
    )
    _require_unicode_scalars(
        value,
        code=f"{label}_invalid_json",
        label=label,
    )
    if not isinstance(value, dict):
        raise CandidateEvidenceError(
            f"{label}_not_object", f"{label} must be a JSON object: {path}"
        )
    return value


def _load_raw_rows(path: Path) -> dict[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CandidateEvidenceError(
            "raw_evidence_invalid_utf8", f"raw evidence must be UTF-8: {path}"
        ) from exc
    rows: dict[str, dict[str, Any]] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(
                raw_line, parse_constant=_reject_json_constant
            )
        except (json.JSONDecodeError, _NonStandardJsonConstant) as exc:
            raise CandidateEvidenceError(
                "raw_evidence_invalid_jsonl",
                f"raw evidence line {line_number} is not valid JSON",
            ) from exc
        _require_finite_numbers(
            row,
            code="raw_evidence_invalid_jsonl",
            label=f"raw evidence line {line_number}",
        )
        _require_unicode_scalars(
            row,
            code="raw_evidence_invalid_jsonl",
            label=f"raw evidence line {line_number}",
        )
        if not isinstance(row, dict):
            raise CandidateEvidenceError(
                "raw_evidence_record_not_object",
                f"raw evidence line {line_number} must be an object",
            )
        task_id = row.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise CandidateEvidenceError(
                "raw_evidence_task_id_missing",
                f"raw evidence line {line_number} has no task_id",
            )
        if task_id in rows:
            raise CandidateEvidenceError(
                "raw_evidence_duplicate_task_id",
                f"raw evidence repeats task_id {task_id!r}",
            )
        if "response_text" not in row or not isinstance(row["response_text"], str):
            raise CandidateEvidenceError(
                "raw_evidence_response_text_missing",
                f"raw evidence for {task_id!r} lacks preserved response_text",
            )
        rows[task_id] = row
    if not rows:
        raise CandidateEvidenceError(
            "raw_evidence_empty", "raw evidence contains no candidate records"
        )
    return rows


def _validate_artifact_id(artifact_id: Any) -> None:
    if (
        not isinstance(artifact_id, str)
        or not _ARTIFACT_ID_RE.fullmatch(artifact_id)
        or artifact_id in {".", ".."}
    ):
        raise CandidateEvidenceError(
            "artifact_id_invalid",
            "artifact_id must be a path-free ASCII identifier",
        )


def _validate_commit(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise CandidateEvidenceError(
            "commit_invalid", f"{field} must be a full 40-character Git SHA"
        )
    return value.lower()


def _resolve_git_commit(repo_root: Path, commit: str, field: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise CandidateEvidenceError(
            f"{field}_unresolved",
            f"{field} cannot be resolved in the repository",
        ) from exc
    if result.returncode or result.stdout.strip().lower() != commit:
        raise CandidateEvidenceError(
            f"{field}_unresolved",
            f"{field} is not an available full Git commit",
        )
    return commit


def _assert_paths_at_commit(
    repo_root: Path,
    commit: str,
    paths: list[str],
    *,
    code: str,
    label: str,
) -> None:
    for relative in sorted(set(paths)):
        current = repo_root.joinpath(*relative.split("/"))
        _require_file(current, label)
        try:
            result = subprocess.run(
                ["git", "show", f"{commit}:{relative}"],
                cwd=repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as exc:
            raise CandidateEvidenceError(
                code,
                f"{label} source cannot be read at {commit}: {relative}",
            ) from exc
        if result.returncode or result.stdout != current.read_bytes():
            raise CandidateEvidenceError(
                code,
                f"{label} source does not match {commit}: {relative}",
            )


def _verify_repository_bindings(
    benchmark_commit: str,
    verifier_commit: str,
    benchmark_bound_paths: list[str],
    verifier_bound_paths: list[str],
) -> None:
    benchmark_commit = _resolve_git_commit(
        REPO_ROOT, benchmark_commit, "benchmark_commit"
    )
    verifier_commit = _resolve_git_commit(
        REPO_ROOT, verifier_commit, "verifier_commit"
    )
    _assert_paths_at_commit(
        REPO_ROOT,
        benchmark_commit,
        benchmark_bound_paths,
        code="benchmark_commit_content_mismatch",
        label="benchmark",
    )
    _assert_paths_at_commit(
        REPO_ROOT,
        verifier_commit,
        verifier_bound_paths,
        code="verifier_commit_content_mismatch",
        label="verifier",
    )


def _verify_predecessor_seal(predecessor: dict[str, Any]) -> None:
    declared = predecessor.get("scored_results_sha256")
    if not isinstance(declared, str):
        raise CandidateEvidenceError(
            "predecessor_seal_missing",
            "predecessor has no scored_results_sha256",
        )
    payload = {
        key: value
        for key, value in predecessor.items()
        if key != "scored_results_sha256"
    }
    if sha256_hex(payload) != declared:
        raise CandidateEvidenceError(
            "predecessor_seal_mismatch",
            "predecessor scored_results_sha256 does not verify",
        )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise CandidateEvidenceError(
            f"{label}_not_found", f"{label} file does not exist: {path}"
        )


def _predecessor_results(
    predecessor: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    rows = predecessor.get("per_task")
    if not isinstance(rows, list):
        raise CandidateEvidenceError(
            "predecessor_results_missing", "predecessor per_task must be a list"
        )
    results: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("task_id"), str):
            raise CandidateEvidenceError(
                "predecessor_result_invalid",
                "each predecessor result must contain task_id",
            )
        task_id = row["task_id"]
        if task_id in results:
            raise CandidateEvidenceError(
                "predecessor_duplicate_task_id",
                f"predecessor repeats task_id {task_id!r}",
            )
        results[task_id] = row
    return results


def _build_successor(
    raw_evidence_path: str | Path,
    predecessor_path: str | Path,
    *,
    artifact_id: str,
    benchmark_commit: str,
    verifier_commit: str,
    reason: str,
    verify_repository: bool = True,
) -> dict[str, Any]:
    """Re-score preserved raw evidence and return a sealed successor object."""
    _validate_artifact_id(artifact_id)
    benchmark_commit = _validate_commit(benchmark_commit, "benchmark_commit")
    verifier_commit = _validate_commit(verifier_commit, "verifier_commit")
    if not isinstance(reason, str) or not reason.strip():
        raise CandidateEvidenceError(
            "regeneration_reason_missing", "reason for regeneration is required"
        )

    raw_path = Path(raw_evidence_path)
    old_path = Path(predecessor_path)
    current_adapter_path = Path(candidate_adapter.__file__).resolve()
    current_evidence_path = Path(__file__).resolve()
    _require_file(raw_path, "raw_evidence")
    _require_file(old_path, "predecessor")
    _require_file(current_adapter_path, "candidate_adapter")
    _require_file(current_evidence_path, "candidate_evidence")
    candidate_adapter_sha256 = _file_sha256(current_adapter_path)
    candidate_evidence_sha256 = _file_sha256(current_evidence_path)

    raw_rows = _load_raw_rows(raw_path)
    predecessor = _load_json_object(old_path, label="predecessor")
    _verify_predecessor_seal(predecessor)
    old_results = _predecessor_results(predecessor)
    if set(raw_rows) != set(old_results):
        raise CandidateEvidenceError(
            "evidence_task_set_mismatch",
            "raw evidence and predecessor task sets do not match",
        )

    known_tasks = {task["task_id"]: task for task in load_tasks()}
    unknown_task_ids = sorted(set(raw_rows) - set(known_tasks))
    if unknown_task_ids:
        raise CandidateEvidenceError(
            "raw_evidence_unknown_task_id",
            f"raw evidence references unknown task {unknown_task_ids[0]!r}",
        )

    task_source_paths = [
        f"sfa_bench/frontier_delta/tasks/{task_id}.json"
        for task_id in sorted(raw_rows)
    ]
    benchmark_bound_paths = sorted(
        set(_BENCHMARK_SOURCE_PATHS) | set(task_source_paths)
    )
    verifier_bound_paths = sorted(_VERIFIER_SOURCE_PATHS)
    if verify_repository:
        _verify_repository_bindings(
            benchmark_commit,
            verifier_commit,
            benchmark_bound_paths,
            verifier_bound_paths,
        )

    per_task: list[dict[str, Any]] = []
    task_files: dict[str, dict[str, str | None]] = {}
    corrected_results: list[dict[str, Any]] = []
    for task_id in sorted(raw_rows):
        raw_row = raw_rows[task_id]
        task = known_tasks[task_id]
        if raw_row.get("lane") not in (None, task["lane"]):
            raise CandidateEvidenceError(
                "raw_evidence_lane_mismatch",
                f"raw evidence lane does not match task {task_id!r}",
            )
        raw_body = raw_row.get("raw_response_body")
        captured_raw_hash = raw_row.get("raw_response_sha256")
        if isinstance(raw_body, str) and isinstance(captured_raw_hash, str):
            actual_raw_hash = hashlib.sha256(
                raw_body.encode("utf-8")
            ).hexdigest()
            if actual_raw_hash != captured_raw_hash:
                raise CandidateEvidenceError(
                    "captured_raw_response_digest_mismatch",
                    f"captured raw response digest does not match {task_id!r}",
                )

        task_path = TASKS_DIR / f"{task_id}.json"
        task_file_sha256 = _file_sha256(task_path)
        captured_task_digest = raw_row.get("task_file_sha256")
        task_files[task_id] = {
            "path": f"sfa_bench/frontier_delta/tasks/{task_id}.json",
            "sha256": task_file_sha256,
            "canonical_sha256": schemas.task_hash(task),
            "capture_sha256": (
                captured_task_digest
                if isinstance(captured_task_digest, str)
                else None
            ),
            "capture_digest_relation": _captured_task_digest_relation(
                task_path, captured_task_digest
            ),
        }

        result = candidate_adapter.score_response(task, raw_row["response_text"])
        corrected_results.append(result)
        evidence_references = {
            "raw_response_body_sha256": (
                captured_raw_hash
                if isinstance(captured_raw_hash, str)
                else None
            ),
            "response_text_sha256": result["parse_notes"]["response_text_sha256"],
            "blinded_prompt_sha256": (
                raw_row.get("blinded_prompt_sha256")
                if isinstance(raw_row.get("blinded_prompt_sha256"), str)
                else None
            ),
            "task_file_sha256": task_file_sha256,
        }
        old_result = old_results[task_id]
        per_task.append(
            {
                "task_id": task_id,
                "predecessor_result": {
                    "result_hash": old_result.get("result_hash"),
                    "score": old_result.get("score"),
                    "verdict": old_result.get("verdict"),
                },
                "corrected_result": result,
                "evidence_references": evidence_references,
            }
        )

    total_score = round(
        sum(float(result["score"]) for result in corrected_results)
        / len(corrected_results),
        6,
    )
    verdict_counts = {
        verdict: sum(
            1 for result in corrected_results if result["verdict"] == verdict
        )
        for verdict in ("pass", "partial", "fail")
    }
    invalid_counts: dict[str, int] = {}
    for result in corrected_results:
        for mode in result["detected_failure_modes"]:
            if mode in {
                "no_model_output",
                "unparseable_model_output",
                "invalid_model_output",
            }:
                invalid_counts[mode] = invalid_counts.get(mode, 0) + 1

    artifact: dict[str, Any] = {
        "schema": SUCCESSOR_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "artifact_kind": "candidate_integrity_scoring_successor",
        "lineage": {
            "relationship": "integrity_correction_successor",
            "predecessor_reference": (
                "sha256:" + _file_sha256(old_path)
            ),
            "predecessor_file_sha256": _file_sha256(old_path),
            "predecessor_canonical_sha256": sha256_hex(predecessor),
            "predecessor_declared_sha256": predecessor["scored_results_sha256"],
            "reason_for_regeneration": reason.strip(),
            "historical_artifact_mutated": False,
        },
        "source_evidence": {
            "raw_jsonl_file_sha256": _file_sha256(raw_path),
            "raw_record_count": len(raw_rows),
            "task_files": task_files,
        },
        "implementation": {
            "benchmark_commit": benchmark_commit,
            "verifier_commit": verifier_commit,
            "candidate_adapter_version": (
                candidate_adapter.CANDIDATE_ADAPTER_VERSION
            ),
            "candidate_adapter_path": (
                "sfa_bench/frontier_delta/candidate_adapter.py"
            ),
            "candidate_adapter_sha256": candidate_adapter_sha256,
            "candidate_evidence_path": _CANDIDATE_EVIDENCE_PATH,
            "candidate_evidence_sha256": candidate_evidence_sha256,
            "benchmark_bound_paths": benchmark_bound_paths,
            "verifier_bound_paths": verifier_bound_paths,
            "scoring_entrypoint": (
                "sfa_bench.frontier_delta.candidate_adapter.score_response"
            ),
            "provider_called": False,
        },
        "scoring_status": {
            "predecessor": {
                "status": (
                    "provisional_due_to_candidate_output_integrity_issue"
                ),
                "total_score": predecessor.get(
                    "total_score_on_selected_cases"
                ),
                "verdict_counts": predecessor.get(
                    "verdict_counts_on_selected_cases"
                ),
            },
            "successor": {
                "status": (
                    "corrected_offline_rederivation_not_ratified"
                ),
                "total_score": total_score,
                "verdict_counts": verdict_counts,
                "invalid_output_counts": {
                    key: invalid_counts[key]
                    for key in sorted(invalid_counts)
                },
            },
        },
        "per_task": per_task,
    }
    artifact["canonical_artifact_sha256"] = sha256_hex(artifact)
    return artifact


def build_successor(
    raw_evidence_path: str | Path,
    predecessor_path: str | Path,
    *,
    artifact_id: str,
    benchmark_commit: str,
    verifier_commit: str,
    reason: str,
) -> dict[str, Any]:
    """Build a successor only after resolving its Git provenance."""
    return _build_successor(
        raw_evidence_path,
        predecessor_path,
        artifact_id=artifact_id,
        benchmark_commit=benchmark_commit,
        verifier_commit=verifier_commit,
        reason=reason,
        verify_repository=True,
    )


def _verify_artifact_seal(artifact: dict[str, Any]) -> None:
    _require_finite_numbers(
        artifact,
        code="successor_nonfinite_number",
        label="successor",
    )
    _require_unicode_scalars(
        artifact,
        code="successor_invalid_unicode",
        label="successor",
    )
    if artifact.get("schema") != SUCCESSOR_SCHEMA_VERSION:
        raise CandidateEvidenceError(
            "successor_schema_unknown",
            f"unsupported successor schema: {artifact.get('schema')!r}",
        )
    declared = artifact.get("canonical_artifact_sha256")
    if not isinstance(declared, str):
        raise CandidateEvidenceError(
            "successor_seal_missing",
            "successor has no canonical_artifact_sha256",
        )
    payload = {
        key: value
        for key, value in artifact.items()
        if key != "canonical_artifact_sha256"
    }
    if sha256_hex(payload) != declared:
        raise CandidateEvidenceError(
            "successor_seal_mismatch",
            "successor canonical_artifact_sha256 does not verify",
        )


def _artifact_bytes(artifact: dict[str, Any]) -> bytes:
    _require_finite_numbers(
        artifact,
        code="successor_nonfinite_number",
        label="successor",
    )
    _require_unicode_scalars(
        artifact,
        code="successor_invalid_unicode",
        label="successor",
    )
    return (
        json.dumps(
            artifact,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_successor(
    artifact: dict[str, Any],
    output_root: str | Path,
) -> Path:
    """Atomically create a successor file and refuse every overwrite."""
    _verify_artifact_seal(artifact)
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str):
        raise CandidateEvidenceError(
            "artifact_id_missing", "successor artifact_id is required"
        )
    _validate_artifact_id(artifact_id)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{artifact_id}.json"
    if destination.exists():
        raise CandidateEvidenceError(
            "successor_already_exists",
            f"refusing to overwrite existing successor: {destination}",
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{artifact_id}.",
        suffix=".tmp",
        dir=root,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_artifact_bytes(artifact))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise CandidateEvidenceError(
                "successor_already_exists",
                f"refusing to overwrite existing successor: {destination}",
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _assert_digest(actual: str, expected: Any, code: str, label: str) -> None:
    if not isinstance(expected, str) or actual != expected:
        raise CandidateEvidenceError(code, f"{label} digest does not match")


def _verify_successor(
    artifact_path: str | Path,
    raw_evidence_path: str | Path,
    predecessor_path: str | Path,
    *,
    verify_repository: bool = True,
) -> dict[str, Any]:
    """Verify all bound inputs and rederive a successor without writing."""
    successor_path = Path(artifact_path)
    raw_path = Path(raw_evidence_path)
    old_path = Path(predecessor_path)
    current_adapter_path = Path(candidate_adapter.__file__).resolve()
    current_evidence_path = Path(__file__).resolve()
    _require_file(successor_path, "successor")
    _require_file(raw_path, "raw_evidence")
    _require_file(old_path, "predecessor")
    _require_file(current_adapter_path, "candidate_adapter")
    _require_file(current_evidence_path, "candidate_evidence")

    artifact = _load_json_object(successor_path, label="successor")
    _verify_artifact_seal(artifact)
    if successor_path.read_bytes() != _artifact_bytes(artifact):
        raise CandidateEvidenceError(
            "successor_serialization_mismatch",
            "successor file is not in deterministic UTF-8 JSON form",
        )
    source = artifact.get("source_evidence")
    lineage = artifact.get("lineage")
    implementation = artifact.get("implementation")
    if not all(isinstance(value, dict) for value in (source, lineage, implementation)):
        raise CandidateEvidenceError(
            "successor_structure_invalid",
            "successor lineage, source_evidence, and implementation are required",
        )

    _assert_digest(
        _file_sha256(raw_path),
        source.get("raw_jsonl_file_sha256"),
        "raw_evidence_digest_mismatch",
        "raw evidence",
    )
    _assert_digest(
        _file_sha256(old_path),
        lineage.get("predecessor_file_sha256"),
        "predecessor_digest_mismatch",
        "predecessor",
    )
    predecessor = _load_json_object(old_path, label="predecessor")
    _assert_digest(
        sha256_hex(predecessor),
        lineage.get("predecessor_canonical_sha256"),
        "predecessor_canonical_digest_mismatch",
        "predecessor canonical content",
    )
    if (
        implementation.get("candidate_adapter_version")
        != candidate_adapter.CANDIDATE_ADAPTER_VERSION
    ):
        raise CandidateEvidenceError(
            "candidate_adapter_version_mismatch",
            "candidate adapter version does not match successor",
        )
    _assert_digest(
        _file_sha256(current_adapter_path),
        implementation.get("candidate_adapter_sha256"),
        "candidate_adapter_digest_mismatch",
        "candidate adapter",
    )
    _assert_digest(
        _file_sha256(current_evidence_path),
        implementation.get("candidate_evidence_sha256"),
        "candidate_evidence_digest_mismatch",
        "candidate evidence tool",
    )

    task_files = source.get("task_files")
    if not isinstance(task_files, dict):
        raise CandidateEvidenceError(
            "task_digests_missing", "successor task file digests are required"
        )
    for task_id, task_reference in sorted(task_files.items()):
        if not isinstance(task_reference, dict):
            raise CandidateEvidenceError(
                "task_digest_invalid", f"task digest entry is invalid: {task_id}"
            )
        try:
            task = load_task(task_id)
        except KeyError as exc:
            raise CandidateEvidenceError(
                "task_not_found", f"successor task no longer exists: {task_id}"
            ) from exc
        task_path = TASKS_DIR / f"{task_id}.json"
        _assert_digest(
            _file_sha256(task_path),
            task_reference.get("sha256"),
            "task_digest_mismatch",
            f"task {task_id}",
        )
        _assert_digest(
            schemas.task_hash(task),
            task_reference.get("canonical_sha256"),
            "task_canonical_digest_mismatch",
            f"canonical task {task_id}",
        )

    rebuilt = _build_successor(
        raw_path,
        old_path,
        artifact_id=artifact.get("artifact_id"),
        benchmark_commit=implementation.get("benchmark_commit"),
        verifier_commit=implementation.get("verifier_commit"),
        reason=lineage.get("reason_for_regeneration"),
        verify_repository=verify_repository,
    )
    if rebuilt != artifact:
        raise CandidateEvidenceError(
            "successor_rederivation_mismatch",
            "successor content does not match deterministic rederivation",
        )
    return {
        "ok": True,
        "code": (
            "candidate_evidence_verified"
            if verify_repository
            else "candidate_evidence_content_verified"
        ),
        "artifact_id": artifact["artifact_id"],
        "canonical_artifact_sha256": artifact[
            "canonical_artifact_sha256"
        ],
    }


def verify_successor(
    artifact_path: str | Path,
    raw_evidence_path: str | Path,
    predecessor_path: str | Path,
) -> dict[str, Any]:
    """Verify bound Git provenance and deterministic evidence rederivation."""
    return _verify_successor(
        artifact_path,
        raw_evidence_path,
        predecessor_path,
        verify_repository=True,
    )


def _resolve_cli_output_root(
    repo_root: Path,
    requested: str | Path | None,
) -> Path:
    repository = repo_root.resolve()
    approved = (repository / "out").resolve()
    candidate = (
        repository / DEFAULT_OUTPUT_DIRECTORY
        if requested is None
        else Path(requested)
    )
    if not candidate.is_absolute():
        candidate = repository / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(approved)
    except ValueError as exc:
        raise CandidateEvidenceError(
            "output_path_outside_approved_root",
            "successor output must remain inside the repository out directory",
        ) from exc
    return resolved


def _resolve_cli_input(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser(
        "build", help="create a corrected lineage-linked successor"
    )
    build.add_argument("--raw", required=True, help="preserved raw JSONL")
    build.add_argument(
        "--predecessor", required=True, help="preserved scored JSON artifact"
    )
    build.add_argument("--artifact-id", required=True)
    build.add_argument("--benchmark-commit", required=True)
    build.add_argument("--verifier-commit", required=True)
    build.add_argument("--reason", required=True)
    build.add_argument(
        "--output-root",
        help="directory inside repository out/ (default: successor directory)",
    )

    verify = commands.add_parser(
        "verify", help="rederive and compare a successor without writing"
    )
    verify.add_argument("--artifact", required=True)
    verify.add_argument("--raw", required=True, help="preserved raw JSONL")
    verify.add_argument(
        "--predecessor", required=True, help="preserved scored JSON artifact"
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    repo_root: str | Path = REPO_ROOT,
) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(repo_root).resolve()
    try:
        raw_path = _resolve_cli_input(root, args.raw)
        predecessor_path = _resolve_cli_input(root, args.predecessor)
        if args.command == "build":
            artifact = build_successor(
                raw_path,
                predecessor_path,
                artifact_id=args.artifact_id,
                benchmark_commit=args.benchmark_commit,
                verifier_commit=args.verifier_commit,
                reason=args.reason,
            )
            output_root = _resolve_cli_output_root(root, args.output_root)
            output_path = write_successor(artifact, output_root)
            payload = {
                "ok": True,
                "code": "candidate_evidence_successor_written",
                "artifact_id": artifact["artifact_id"],
                "canonical_artifact_sha256": artifact[
                    "canonical_artifact_sha256"
                ],
                "output_path": output_path.relative_to(root).as_posix(),
            }
        else:
            artifact_path = _resolve_cli_input(root, args.artifact)
            payload = verify_successor(
                artifact_path,
                raw_path,
                predecessor_path,
            )
    except CandidateEvidenceError as exc:
        print(
            json.dumps(
                {"ok": False, "code": exc.code, "message": str(exc)},
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 2
    print(json.dumps(payload, sort_keys=True, allow_nan=False))
    return 0
