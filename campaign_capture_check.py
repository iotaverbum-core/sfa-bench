#!/usr/bin/env python3
"""Deterministic offline smoke check for governed alpha.2 campaign capture."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from sfa_bench.campaigns.capture import (
    AUTHORIZATION_SCHEMA,
    SyntheticAdapter,
    build_review_bundle,
    capture_attempt,
    initialize_run,
    judge_run,
    seal_authorization,
    seal_run,
    sha256_bytes,
    verify_review_bundle,
    verify_run,
)
from sfa_bench.campaigns.locking import build_benchmark_lock


ROOT = Path(__file__).resolve().parent
NOW = "2026-07-12T20:00:00+02:00"
REQUEST = b'{"synthetic":"locked-request-v1"}'
TASK_REFERENCE = "sfa_bench/frontier_delta/tasks/memory_boundary_001.json"


def _head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("campaign capture check requires Git history")
    return result.stdout.strip()


def _campaign_and_lock() -> tuple[dict, dict]:
    campaign = json.loads(
        (ROOT / "campaigns/examples/gpt56-draft-preregistration.json").read_text(encoding="utf-8")
    )
    campaign = copy.deepcopy(campaign)
    campaign["benchmark_commit_sha"] = _head()
    campaign["release_identifier"] = "v2.0.0-alpha.2"
    campaign["benchmark_inputs"]["schema_paths"].extend(
        [
            "campaign_capture_cli.py",
            "campaign_capture_check.py",
            "sfa_bench/campaigns/capture",
            "campaigns/alpha2/schemas",
        ]
    )
    campaign["benchmark_inputs"]["schema_paths"] = sorted(
        set(campaign["benchmark_inputs"]["schema_paths"])
    )
    campaign["benchmark_inputs"]["declared_commands"].append(
        "py -3 campaign_capture_check.py"
    )
    campaign.pop("benchmark_lock", None)
    return campaign, build_benchmark_lock(campaign, ROOT)


def _authorization(campaign: dict, lock: dict, execution_id: str) -> dict:
    adapter = SyntheticAdapter("valid_json_object")
    return seal_authorization(
        {
            "schema_version": AUTHORIZATION_SCHEMA,
            "authorization_id": f"auth-{execution_id}",
            "campaign_id": campaign["campaign_id"],
            "benchmark_lock_digest": lock["lock_digest"],
            "benchmark_commit": lock["repository_commit"],
            "verifier_commit": lock["verifier_commit"],
            "release_identifier": lock["release_identifier"],
            "execution_id": execution_id,
            "adapter": {
                "adapter_id": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "implementation_path": adapter.implementation_path,
            },
            "request": {
                "sha256": sha256_bytes(REQUEST),
                "byte_length": len(REQUEST),
                "prompt_reference": campaign["system_prompt"]["reference"],
                "case_reference": TASK_REFERENCE,
            },
            "retry_policy": {
                "max_attempts": campaign["retry_policy"]["max_attempts"],
                "allowed_reasons": campaign["retry_policy"]["retry_conditions"],
            },
            "operator_declaration": {
                "identity": "synthetic-test-operator",
                "authority_type": "declared_human_operator",
                "authorization_scope": "execution_only",
            },
            "issued_at": NOW,
            "ratification_status": "unratified",
            "automatic_actions": {
                "ratify": False,
                "promote": False,
                "publish": False,
                "release": False,
            },
        }
    )


def main() -> int:
    campaign, lock = _campaign_and_lock()
    with tempfile.TemporaryDirectory(prefix="sfa-alpha2-capture-") as temporary:
        output_root = Path(temporary) / "runs"
        authorization = _authorization(campaign, lock, "synthetic-alpha2-valid")
        adapter = SyntheticAdapter("valid_json_object")
        run_dir = initialize_run(
            campaign=campaign,
            lock=lock,
            authorization=authorization,
            request_bytes=REQUEST,
            adapter=adapter,
            repo_root=ROOT,
            output_root=output_root,
            observed_at=NOW,
        )
        attempt = capture_attempt(
            run_dir,
            request_bytes=REQUEST,
            adapter=adapter,
            repo_root=ROOT,
            observed_at=NOW,
        )
        if not attempt["complete"] or adapter.calls != 1:
            raise AssertionError("synthetic capture did not complete exactly once")
        manifest = seal_run(run_dir, repo_root=ROOT, observed_at=NOW)
        judgment = judge_run(
            run_dir,
            repo_root=ROOT,
            task_reference=TASK_REFERENCE,
            observed_at=NOW,
        )
        bundle = build_review_bundle(run_dir, repo_root=ROOT, observed_at=NOW)
        report = verify_run(run_dir, repo_root=ROOT)
        verify_review_bundle(run_dir, repo_root=ROOT)
        if report["lifecycle_state"] != "review_required":
            raise AssertionError("final lifecycle state is not review_required")
        if bundle["ratification_status"] != "unratified" or bundle["raw_bodies_included"]:
            raise AssertionError("review bundle crossed the authority/privacy boundary")
        print("SFA-Bench alpha.2 campaign capture check")
        print("synthetic adapter: PASS")
        print("exact request bytes: PASS")
        print("sealed capture:", manifest["manifest_sha256"])
        print("sealed judgment:", judgment["judgment_sha256"])
        print("review bundle:", bundle["bundle_sha256"])
        print("ratification status: unratified")
        print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
