#!/usr/bin/env python3
"""Repository release checks for SFA-Bench v1.0.0."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
EXPECTED_RELEASE = "v1.0.0"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
REQUIRED_CI_COMMANDS = (
    "python verify_all.py",
    "python release_gate.py --ci",
)
PROTECTED_PATHS = (
    "history/occurrences.jsonl",
    "sfa/verifier.py",
    "families.json",
    "sfa/categories.py",
)
RUNTIME_PREFIXES = (
    "agent_runs/",
    "transcript_runs/",
    "adapter_runs/",
    "fingerprint_runs/",
    "policy_runs/",
)
COMMAND_FILES = (
    "run_benchmark.py",
    "replay.py",
    "report.py",
    "tamper_suite.py",
    "invariant_suite.py",
    "agent_demo.py",
    "external_candidate_demo.py",
    "transcript_demo.py",
    "rederive.py",
    "adapter_demo.py",
    "fingerprint_report.py",
    "policy_demo.py",
)
STALE_HEADER = re.compile(
    r"print\(\s*(?:f)?[\"']#?\s*(?:SFA-Bench|SFA-Agent) v0\.", re.MULTILINE
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def tracked_changes(path: str) -> bool:
    return bool(git("diff", "--name-only", "HEAD", "--", path).strip())


def is_generated_sealed_artifact(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        (normalized.startswith("artifacts/") and normalized != "artifacts/.gitkeep")
        or normalized.endswith(".sealed.json")
        or normalized.endswith("/failure_artifact.json")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ci", action="store_true", help="identify the check as the offline CI gate"
    )
    parser.add_argument(
        "--release", metavar="VERSION", help="require the expected release label"
    )
    args = parser.parse_args()

    print("SFA-Bench release gate")
    print("=" * 56)

    failures: list[str] = []
    try:
        status = git("status", "--short", "--untracked-files=all")
        untracked = [
            line for line in git("ls-files", "--others", "--exclude-standard").splitlines()
            if line
        ]
        staged = [
            line.replace("\\", "/")
            for line in git("diff", "--cached", "--name-only").splitlines()
            if line
        ]
    except RuntimeError as exc:
        print("working tree inspected: no")
        print("untracked files inspected: no")
        print(f"failure: {exc}")
        print("final status: FAIL")
        return 2

    protected = {path: not tracked_changes(path) for path in PROTECTED_PATHS}
    runtime_staged = [
        path for path in staged if path.startswith(RUNTIME_PREFIXES)
    ]
    sealed_staged = [path for path in staged if is_generated_sealed_artifact(path)]

    workflow_text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""
    missing_ci = [cmd for cmd in REQUIRED_CI_COMMANDS if cmd not in workflow_text]

    stale_headers: list[str] = []
    for relative in COMMAND_FILES:
        path = ROOT / relative
        if not path.is_file() or STALE_HEADER.search(path.read_text(encoding="utf-8")):
            stale_headers.append(relative)

    if untracked:
        failures.append("untracked files remain")
    if not protected["history/occurrences.jsonl"]:
        failures.append("history/occurrences.jsonl is modified or staged")
    if not protected["sfa/verifier.py"]:
        failures.append("sfa/verifier.py is modified or staged")
    if not protected["families.json"] or not protected["sfa/categories.py"]:
        failures.append("taxonomy files are modified or staged")
    if runtime_staged:
        failures.append("runtime output is staged")
    if sealed_staged:
        failures.append("generated sealed artifacts are staged")
    if missing_ci:
        failures.append("required v1.0 CI commands are missing")
    if stale_headers:
        failures.append("stale version labels remain in command headers")
    if args.release and args.release != EXPECTED_RELEASE:
        failures.append(
            f"release label {args.release!r} does not match {EXPECTED_RELEASE!r}"
        )

    print("working tree inspected: yes")
    print("untracked files inspected: yes")
    print(f"untracked files remain: {'yes' if untracked else 'no'}")
    print(f"history unchanged: {'yes' if protected['history/occurrences.jsonl'] else 'no'}")
    print(f"verifier unchanged: {'yes' if protected['sfa/verifier.py'] else 'no'}")
    taxonomy_ok = protected["families.json"] and protected["sfa/categories.py"]
    print(f"taxonomy unchanged: {'yes' if taxonomy_ok else 'no'}")
    print(f"runtime output staged: {'yes' if runtime_staged else 'no'}")
    print(f"generated sealed artifacts staged: {'yes' if sealed_staged else 'no'}")
    print(f"CI command coverage: {'yes' if not missing_ci else 'no'}")
    print(f"current command headers: {'yes' if not stale_headers else 'no'}")
    print(f"mode: {'ci' if args.ci else 'local'}")
    if status.strip():
        print("working tree status:")
        print(status.rstrip())
    if untracked:
        print("untracked files:")
        for path in untracked:
            print(f"  - {path}")
    if runtime_staged:
        print("staged runtime output:")
        for path in runtime_staged:
            print(f"  - {path}")
    if sealed_staged:
        print("staged generated sealed artifacts:")
        for path in sealed_staged:
            print(f"  - {path}")
    if missing_ci:
        print("missing CI commands:")
        for command in missing_ci:
            print(f"  - {command}")
    if stale_headers:
        print("stale or missing command headers:")
        for path in stale_headers:
            print(f"  - {path}")
    for failure in failures:
        print(f"failure: {failure}")
    print("=" * 56)
    print(f"final status: {'FAIL' if failures else 'PASS'}")
    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
