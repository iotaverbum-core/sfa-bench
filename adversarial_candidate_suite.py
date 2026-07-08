#!/usr/bin/env python3
"""Run controlled adversarial cases for external-candidate intake."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
BASE_REF = "origin/main"
FROZEN_MANIFEST = "autolab/frozen_manifest.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "adversarial_candidate_cases.json"
EXPECTED_CASE_ORDER = (
    "safe_docs_candidate",
    "frozen_path_tamper",
    "release_gate_failure",
    "non_promotion_ratification_attempt",
    "malformed_packet",
)


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    expected_outcome: str
    expected_reason: str | None


@dataclass
class CaseResult:
    case_id: str
    expected_outcome: str
    actual_outcome: str
    expected_reason: str | None
    actual_reason: str
    passed: bool
    details: dict[str, Any]


class SuiteError(RuntimeError):
    """Raised when the adversarial suite cannot construct a controlled case."""


class TempRepo:
    """Disposable repo cloned from an archive of origin/main."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "repo"
        self.env = os.environ.copy()
        for key in ("TMP", "TEMP", "TMPDIR"):
            self.env[key] = str(root)

    @classmethod
    def create(cls, root: Path, archive: bytes) -> "TempRepo":
        repo = cls(root)
        repo.path.mkdir(parents=True, exist_ok=True)
        _extract_archive(archive, repo.path)
        repo.git("init")
        repo.git("config", "user.name", "SFA Adversarial Suite")
        repo.git("config", "user.email", "adversarial-suite@example.invalid")
        repo.git("add", "-A")
        repo.git("commit", "-m", "Adversarial suite base")
        repo.git("update-ref", f"refs/remotes/{BASE_REF}", "HEAD")
        return repo

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return _run(["git", *args], cwd=self.path, env=self.env, check=check)

    def checkout_base(self, branch: str) -> None:
        self.git("checkout", "-B", branch, BASE_REF)

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()


@dataclass
class SuiteContext:
    temp_root: Path
    archive: bytes

    def repo_for(self, case_id: str) -> TempRepo:
        return TempRepo.create(self.temp_root / case_id, self.archive)


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode:
        raise SuiteError(f"{' '.join(argv)} failed in {cwd}: {result.stdout.strip()}")
    return result


def _run_bytes(argv: list[str], *, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise SuiteError(f"{' '.join(argv)} failed in {cwd}: {detail}")
    return result


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=cwd, check=check)


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, data: Any) -> None:
    _write_text(path, _json_dump(data))


def _temp_parent() -> Path:
    raw = os.environ.get("SFA_ADVERSARIAL_TMP")
    parent = Path(raw) if raw else Path("C:/tmp" if os.name == "nt" else tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _base_archive() -> bytes:
    _git(ROOT, "rev-parse", "--is-inside-work-tree")
    _git(ROOT, "rev-parse", "--verify", f"{BASE_REF}^{{commit}}")
    return _run_bytes(["git", "archive", "--format=tar", BASE_REF], cwd=ROOT, check=True).stdout


def _extract_archive(archive: bytes, target: Path) -> None:
    target_root = target.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            member_target = (target / member.name).resolve()
            if member_target != target_root and target_root not in member_target.parents:
                raise SuiteError(f"refusing to extract archive member outside temp repo: {member.name}")
        tar.extractall(target)


def _load_case_specs() -> dict[str, CaseSpec]:
    try:
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteError(f"fixture not found: {FIXTURE_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise SuiteError(f"fixture is not valid JSON: {exc}") from exc

    cases = data.get("cases")
    if not isinstance(cases, list):
        raise SuiteError("fixture field 'cases' must be a list")

    specs: dict[str, CaseSpec] = {}
    for raw in cases:
        if not isinstance(raw, dict):
            raise SuiteError("each fixture case must be an object")
        case_id = raw.get("case_id")
        expected_outcome = raw.get("expected_outcome")
        expected_reason = raw.get("expected_reason")
        if not isinstance(case_id, str) or not case_id:
            raise SuiteError("each fixture case needs a non-empty case_id")
        if not isinstance(expected_outcome, str) or not expected_outcome:
            raise SuiteError(f"{case_id}: expected_outcome must be a non-empty string")
        if expected_reason is not None and not isinstance(expected_reason, str):
            raise SuiteError(f"{case_id}: expected_reason must be a string when present")
        specs[case_id] = CaseSpec(case_id, expected_outcome, expected_reason)

    missing = [case_id for case_id in EXPECTED_CASE_ORDER if case_id not in specs]
    if missing:
        raise SuiteError(f"fixture missing required case(s): {', '.join(missing)}")
    return specs


def _changed_paths(repo: TempRepo, candidate_commit: str) -> list[str]:
    result = repo.git("diff", "--name-only", f"{BASE_REF}...{candidate_commit}")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _base_frozen_paths(repo: TempRepo) -> set[str]:
    result = repo.git("show", f"{BASE_REF}:{FROZEN_MANIFEST}")
    manifest = json.loads(result.stdout)
    frozen_paths = manifest.get("frozen_paths")
    if not isinstance(frozen_paths, list):
        raise SuiteError(f"{BASE_REF}:{FROZEN_MANIFEST} does not declare frozen_paths")
    return {str(path).replace("\\", "/") for path in frozen_paths}


def _release_gate(repo: TempRepo) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "release_gate.py", "--ci"], cwd=repo.path, env=repo.env)


def _final_status(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("final status:"):
            return line.split(":", 1)[1].strip()
    return "UNKNOWN"


def _failure_line(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.startswith("failure:"):
            return line.split(":", 1)[1].strip()
    return stdout.strip()


def _case_result(
    spec: CaseSpec,
    *,
    actual_outcome: str,
    actual_reason: str,
    details: dict[str, Any] | None = None,
) -> CaseResult:
    passed = actual_outcome == spec.expected_outcome
    if passed and spec.expected_reason:
        passed = spec.expected_reason in actual_reason
    return CaseResult(
        case_id=spec.case_id,
        expected_outcome=spec.expected_outcome,
        actual_outcome=actual_outcome,
        expected_reason=spec.expected_reason,
        actual_reason=actual_reason,
        passed=passed,
        details=details or {},
    )


def run_safe_docs_candidate(ctx: SuiteContext, spec: CaseSpec) -> CaseResult:
    repo = ctx.repo_for("safe_docs_candidate")
    repo.checkout_base("case-safe-docs")
    _write_text(
        repo.path / "docs" / "adversarial-safe-candidate.md",
        "# Adversarial Safe Candidate\n\n"
        "Temporary docs-only candidate used by adversarial_candidate_suite.py.\n",
    )
    commit = repo.commit_all("Adversarial suite safe docs candidate")
    changed = _changed_paths(repo, commit)
    touched = sorted(path for path in changed if path in _base_frozen_paths(repo))
    gate = _release_gate(repo)
    if touched:
        outcome = "HALTED_BY_PREFLIGHT"
        reason = "frozen_path_change_proposed"
    elif gate.returncode:
        outcome = "REJECTED_BY_RELEASE_GATE"
        reason = "release_gate.py --ci failed"
    else:
        outcome = "PROMOTION_READY"
        reason = "protected verification passed with no frozen-path changes"
    return _case_result(
        spec,
        actual_outcome=outcome,
        actual_reason=reason,
        details={
            "candidate_commit": commit,
            "changed_paths": changed,
            "release_gate_returncode": gate.returncode,
            "release_gate_final_status": _final_status(gate.stdout),
        },
    )


def run_frozen_path_tamper(ctx: SuiteContext, spec: CaseSpec) -> CaseResult:
    repo = ctx.repo_for("frozen_path_tamper")
    repo.checkout_base("case-frozen-path-tamper")
    path = repo.path / "sfa" / "verifier.py"
    text = path.read_text(encoding="utf-8")
    _write_text(path, text + "\n# adversarial suite frozen path tamper fixture\n")
    commit = repo.commit_all("Adversarial suite frozen path tamper")
    changed = _changed_paths(repo, commit)
    touched = sorted(path for path in changed if path in _base_frozen_paths(repo))
    if touched:
        outcome = "HALTED_BY_PREFLIGHT"
        reason = "frozen_path_change_proposed"
    else:
        outcome = "PREFLIGHT_MISSED_FROZEN_PATH"
        reason = "candidate did not intersect the base frozen manifest"
    return _case_result(
        spec,
        actual_outcome=outcome,
        actual_reason=reason,
        details={"candidate_commit": commit, "changed_paths": changed, "frozen_paths_touched": touched},
    )


def run_release_gate_failure(ctx: SuiteContext, spec: CaseSpec) -> CaseResult:
    repo = ctx.repo_for("release_gate_failure")
    repo.checkout_base("case-release-gate-failure")
    _write_text(
        repo.path / "adversarial_release_gate_output.tmp",
        "created by the adversarial release gate case\n",
    )
    gate = _release_gate(repo)
    outcome = "REJECTED_BY_RELEASE_GATE" if gate.returncode else "PROMOTION_READY"
    reason = "release_gate.py --ci failed" if gate.returncode else "release_gate.py --ci passed"
    return _case_result(
        spec,
        actual_outcome=outcome,
        actual_reason=reason,
        details={
            "release_gate_returncode": gate.returncode,
            "release_gate_final_status": _final_status(gate.stdout),
            "dirty_file": "adversarial_release_gate_output.tmp",
        },
    )


def _minimal_candidate_packet(outcome_class: str) -> dict[str, Any]:
    return {
        "schema": "sfa.external_candidate_harness.packet.v0",
        "run_id": f"adversarial-{outcome_class.lower()}",
        "created_utc": "2026-07-08T00:00:00Z",
        "base_ref": BASE_REF,
        "base_commit": "a" * 40,
        "candidate": {
            "input_kind": "target",
            "input": "b" * 40,
            "resolved_ref": "b" * 40,
            "resolved_commit": "b" * 40,
        },
        "comparison": {
            "diff_range": f"{BASE_REF}...{'b' * 40}",
            "changed_path_count": 1,
            "changed_paths": ["README.md"],
        },
        "frozen_zone": {
            "manifest_source": f"{BASE_REF}:{FROZEN_MANIFEST}",
            "frozen_path_count": 18,
            "touched": False,
            "touched_paths": [],
        },
        "commands": [
            {
                "name": "release_gate",
                "argv": ["py", "-3", "release_gate.py", "--ci"],
                "command": "py -3 release_gate.py --ci",
                "duration_seconds": 0.001,
                "failure_outcome": "REJECTED_BY_RELEASE_GATE",
                "ok": False,
                "returncode": 2,
                "stdout": "SFA-Bench release gate\nfinal status: FAIL\n",
            }
        ],
        "outcome": {
            "class": outcome_class,
            "promotion_ready": outcome_class == "PROMOTION_READY",
            "reason": "release_gate.py --ci failed",
            "preflight_errors": [],
        },
        "artifacts": {
            "candidate_packet_json": None,
            "candidate_packet_md": None,
            "ratification_template_md": None,
        },
    }


def _ratification_repo(ctx: SuiteContext, case_id: str) -> TempRepo:
    repo = ctx.repo_for(case_id)
    repo.checkout_base(f"case-{case_id}")
    return repo


def run_non_promotion_ratification_attempt(ctx: SuiteContext, spec: CaseSpec) -> CaseResult:
    repo = _ratification_repo(ctx, "non_promotion_ratification_attempt")
    packet_path = repo.path / "adversarial_packets" / "non_promotion_candidate_packet.json"
    _write_json(packet_path, _minimal_candidate_packet("REJECTED_BY_RELEASE_GATE"))
    result = _run(
        [sys.executable, "ratification_packet_cli.py", "--packet", str(packet_path), "--ratify"],
        cwd=repo.path,
        env=repo.env,
    )
    actual = "RATIFICATION_REFUSED" if result.returncode and "refusing --ratify" in result.stdout else "UNEXPECTED_RATIFICATION_RESULT"
    return _case_result(
        spec,
        actual_outcome=actual,
        actual_reason=_failure_line(result.stdout),
        details={"packet_path": str(packet_path), "returncode": result.returncode},
    )


def run_malformed_packet(ctx: SuiteContext, spec: CaseSpec) -> CaseResult:
    repo = _ratification_repo(ctx, "malformed_packet")
    packet_path = repo.path / "adversarial_packets" / "malformed_candidate_packet.json"
    _write_json(
        packet_path,
        {
            "schema": "sfa.external_candidate_harness.packet.v0",
            "run_id": "adversarial-malformed",
            "outcome": {"class": "PROMOTION_READY"},
        },
    )
    result = _run(
        [sys.executable, "ratification_packet_cli.py", "--packet", str(packet_path), "--prepare"],
        cwd=repo.path,
        env=repo.env,
    )
    actual = "MALFORMED_PACKET_REJECTED" if result.returncode and "missing required field" in result.stdout else "UNEXPECTED_RATIFICATION_RESULT"
    return _case_result(
        spec,
        actual_outcome=actual,
        actual_reason=_failure_line(result.stdout),
        details={"packet_path": str(packet_path), "returncode": result.returncode},
    )


CASE_HANDLERS: dict[str, Callable[[SuiteContext, CaseSpec], CaseResult]] = {
    "safe_docs_candidate": run_safe_docs_candidate,
    "frozen_path_tamper": run_frozen_path_tamper,
    "release_gate_failure": run_release_gate_failure,
    "non_promotion_ratification_attempt": run_non_promotion_ratification_attempt,
    "malformed_packet": run_malformed_packet,
}


def run_suite() -> list[CaseResult]:
    specs = _load_case_specs()
    archive = _base_archive()
    with tempfile.TemporaryDirectory(
        prefix="sfa-adversarial-",
        dir=_temp_parent(),
        ignore_cleanup_errors=True,
    ) as temp_name:
        ctx = SuiteContext(temp_root=Path(temp_name), archive=archive)
        results: list[CaseResult] = []
        for case_id in EXPECTED_CASE_ORDER:
            spec = specs[case_id]
            try:
                results.append(CASE_HANDLERS[case_id](ctx, spec))
            except Exception as exc:  # pragma: no cover - keep all cases reportable.
                results.append(
                    _case_result(
                        spec,
                        actual_outcome="ERROR",
                        actual_reason=str(exc),
                        details={"exception_type": type(exc).__name__},
                    )
                )
        return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="identify this as a CI adversarial run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("SFA-Bench adversarial candidate suite")
    print("=" * 56)
    print(f"mode: {'ci' if args.ci else 'local'}")
    print(f"base_ref: {BASE_REF}")

    try:
        results = run_suite()
    except SuiteError as exc:
        print(f"failure: {exc}")
        print("=" * 56)
        print("final status: FAIL")
        return 2

    for index, result in enumerate(results, start=1):
        status = "PASS" if result.passed else "FAIL"
        print(f"[{index}/{len(results)}] {result.case_id}: {status}")
        print(f"  expected: {result.expected_outcome}")
        print(f"  actual:   {result.actual_outcome}")
        if result.expected_reason:
            print(f"  expected reason contains: {result.expected_reason}")
        print(f"  actual reason: {result.actual_reason or '<empty>'}")
        if result.details.get("frozen_paths_touched"):
            touched = ", ".join(result.details["frozen_paths_touched"])
            print(f"  frozen paths touched: {touched}")

    all_passed = all(result.passed for result in results)
    print("=" * 56)
    print(f"final status: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 2


if __name__ == "__main__":
    sys.exit(main())