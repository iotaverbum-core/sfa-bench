#!/usr/bin/env python3
"""Run the complete SFA-Bench v2.0.0-alpha.2 offline verification suite."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parent
COMMANDS = (
    "run_benchmark.py",
    "replay.py",
    "report.py",
    "tamper_suite.py",
    "invariant_suite.py",
    "frozen_zone_check.py",
    "candidate_integrity_check.py",
    "campaign_protocol_check.py",
    "campaign_capture_check.py",
    "preregistration_demo.py",
    "autolab_controller_demo.py",
    "ratification_demo.py",
    "lineage_demo.py",
    "circuit_breakers_demo.py",
    "autolab_runner_demo.py",
    "agent_demo.py",
    "external_candidate_demo.py",
    "transcript_demo.py",
    "rederive.py",
    "adapter_demo.py",
    "fingerprint_report.py",
    "policy_demo.py",
    "prior_state_trial.py",
    "deferred_consequence.py",
    "recurrence_metric.py",
    "property_contract.py",
    "causal_report.py",
)
PROVENANCE_COMMANDS = frozenset(
    {"candidate_integrity_check.py", "campaign_protocol_check.py", "campaign_capture_check.py"}
)
EXCLUDED_DIRECTORIES = {
    ".git",
    ".tamper-tmp",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "agent_runs",
    "transcript_runs",
    "adapter_runs",
    "fingerprint_runs",
    "policy_runs",
}


def ignore_runtime(path: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in EXCLUDED_DIRECTORIES}
    ignored.update(name for name in names if name.startswith(".verify-all-"))
    if Path(path).name == "artifacts":
        ignored.update(name for name in names if fnmatch.fnmatch(name, "*.sealed.json"))
    ignored.update(name for name in names if name.endswith(".pyc"))
    return ignored


def remove_readonly(function, path: str, _error) -> None:
    """Retry temporary-worktree cleanup after clearing Windows read-only mode."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def main() -> int:
    print("SFA-Bench v2.0.0-alpha.2 full offline verification")
    print("=" * 56)
    print("workspace: isolated temporary copy (checked-out history is not mutated)")
    print("provenance checks: read-only execution in the checked-out Git repository")

    env = os.environ.copy()
    env["CI"] = "true"
    env.pop("SFA_ADAPTER", None)
    env.pop("SFA_ENABLE_LIVE_ADAPTERS", None)
    # verify_all.py runs in a copied, offline workspace; the dedicated CI step
    # owns PR base-ref amendment-gate enforcement.
    env.pop("GITHUB_BASE_REF", None)
    env.pop("GITHUB_HEAD_REF", None)
    env["SFA_VERIFY_ISOLATED_COPY"] = "true"

    workspace = ROOT / f".verify-all-{uuid.uuid4().hex[:8]}"
    failed_exit = 0

    try:
        shutil.copytree(
            ROOT,
            workspace,
            ignore=ignore_runtime,
            copy_function=shutil.copyfile,
        )
        total = len(COMMANDS)
        for index, script in enumerate(COMMANDS, start=1):
            command_env = env.copy()
            command_root = workspace
            if script in PROVENANCE_COMMANDS:
                command_env.pop("SFA_VERIFY_ISOLATED_COPY", None)
                command_root = ROOT
            result = subprocess.run(
                [sys.executable, script],
                cwd=command_root,
                env=command_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode:
                print(f"[{index}/{total}] {script} ... FAIL (exit {result.returncode})")
                if result.stdout:
                    print(result.stdout.rstrip())
                failed_exit = result.returncode or 1
                break
            print(f"[{index}/{total}] {script} ... PASS")
    finally:
        if workspace.exists():
            try:
                shutil.rmtree(workspace, onerror=remove_readonly)
            except OSError as exc:
                print(f"cleanup retained runtime workspace: {workspace}")
                print(f"cleanup warning: {exc}")

    print("=" * 56)
    print(f"final status: {'FAIL' if failed_exit else 'PASS'}")
    return failed_exit


if __name__ == "__main__":
    sys.exit(main())
