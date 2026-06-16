"""Invariant checks for the verifier trust boundary.

These helpers are test code, not verifier behavior. They deliberately keep the
verifier under test behind subprocess calls so ambient files in the working
directory can vary while the fixed verification payload stays identical.
"""
from __future__ import annotations

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
    "provenance",
    "warnings",
    "agent",
    "model_adapter",
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
