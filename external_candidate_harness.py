#!/usr/bin/env python3
"""Inspect and verify an external SFA-Bench candidate commit."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
BASE_REF = "origin/main"
PACKET_ROOT = ROOT / "out" / "candidate_packets"
FROZEN_MANIFEST = "autolab/frozen_manifest.json"
SCHEMA = "sfa.external_candidate_harness.packet.v0"
OUTCOMES = {
    "PROMOTION_READY",
    "REJECTED_BY_TESTS",
    "REJECTED_BY_RELEASE_GATE",
    "REJECTED_BY_FROZEN_ZONE",
    "HALTED_BY_PREFLIGHT",
}
PROTECTED_COMMANDS = (
    {
        "name": "verify_all",
        "argv": ["py", "-3", "verify_all.py"],
        "failure_outcome": "REJECTED_BY_TESTS",
    },
    {
        "name": "release_gate",
        "argv": ["py", "-3", "release_gate.py", "--ci"],
        "failure_outcome": "REJECTED_BY_RELEASE_GATE",
    },
    {
        "name": "frozen_zone_check",
        "argv": ["py", "-3", "frozen_zone_check.py", "--ci", "--base", BASE_REF],
        "failure_outcome": "REJECTED_BY_FROZEN_ZONE",
    },
)


class HarnessError(RuntimeError):
    """Raised when preflight cannot safely inspect the candidate."""


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise HarnessError(f"git {' '.join(args)} failed: {detail}")
    return result


def _resolve_ref(ref: str) -> str:
    result = _run_git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    detail = (result.stderr or result.stdout).strip()
    raise HarnessError(f"could not resolve ref {ref!r} to a commit: {detail}")


def _resolve_branch(branch: str) -> tuple[str, str]:
    candidates = [
        branch,
        f"refs/heads/{branch}",
        f"refs/remotes/{branch}",
        f"refs/remotes/origin/{branch}",
        f"origin/{branch}",
    ]
    tried: list[str] = []
    for candidate in candidates:
        if candidate in tried:
            continue
        tried.append(candidate)
        result = _run_git("rev-parse", "--verify", f"{candidate}^{{commit}}", check=False)
        if result.returncode == 0:
            return result.stdout.strip(), candidate
    raise HarnessError(
        f"could not resolve branch {branch!r}; tried: {', '.join(tried)}"
    )


def _changed_paths(base_ref: str, candidate_commit: str) -> list[str]:
    result = _run_git("diff", "--name-only", f"{base_ref}...{candidate_commit}")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _load_base_frozen_paths(base_ref: str) -> list[str]:
    result = _run_git("show", f"{base_ref}:{FROZEN_MANIFEST}")
    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{base_ref}:{FROZEN_MANIFEST} is not valid JSON: {exc}") from exc
    frozen_paths = manifest.get("frozen_paths")
    if not isinstance(frozen_paths, list) or not frozen_paths:
        raise HarnessError(f"{base_ref}:{FROZEN_MANIFEST} does not declare frozen_paths")
    return sorted(str(path).replace("\\", "/") for path in frozen_paths)


def _run_command(argv: list[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    duration = time.perf_counter() - started
    return {
        "argv": argv,
        "command": " ".join(argv),
        "duration_seconds": round(duration, 3),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "ok": result.returncode == 0,
    }


def _run_protected_commands(candidate_commit: str) -> list[dict[str, Any]]:
    command_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="sfa-candidate-") as parent:
        worktree = Path(parent) / "worktree"
        _run_git("worktree", "add", "--detach", str(worktree), candidate_commit)
        try:
            for command in PROTECTED_COMMANDS:
                result = _run_command(list(command["argv"]), worktree)
                result["name"] = command["name"]
                result["failure_outcome"] = command["failure_outcome"]
                command_results.append(result)
        finally:
            _run_git("worktree", "remove", "--force", str(worktree), check=False)
            _run_git("worktree", "prune", check=False)
    return command_results


def _classify(
    *,
    preflight_errors: list[str],
    frozen_paths_touched: list[str],
    commands: list[dict[str, Any]],
) -> tuple[str, str]:
    if preflight_errors:
        return "HALTED_BY_PREFLIGHT", "; ".join(preflight_errors)
    frozen_command = next((cmd for cmd in commands if cmd.get("name") == "frozen_zone_check"), None)
    if frozen_paths_touched:
        return (
            "REJECTED_BY_FROZEN_ZONE",
            "candidate changes files frozen as of origin/main: "
            + ", ".join(frozen_paths_touched),
        )
    if frozen_command is not None and not frozen_command.get("ok"):
        return "REJECTED_BY_FROZEN_ZONE", "frozen_zone_check.py failed"
    verify = next((cmd for cmd in commands if cmd.get("name") == "verify_all"), None)
    if verify is not None and not verify.get("ok"):
        return "REJECTED_BY_TESTS", "verify_all.py failed"
    release = next((cmd for cmd in commands if cmd.get("name") == "release_gate"), None)
    if release is not None and not release.get("ok"):
        return "REJECTED_BY_RELEASE_GATE", "release_gate.py --ci failed"
    return "PROMOTION_READY", "protected verification passed with no frozen-path changes"


def _packet_markdown(packet: dict[str, Any]) -> str:
    outcome = packet["outcome"]["class"]
    lines = [
        "# External Candidate Packet",
        "",
        f"- Run ID: `{packet['run_id']}`",
        f"- Outcome: `{outcome}`",
        f"- Reason: {packet['outcome']['reason']}",
        f"- Base: `{packet['base_ref']}` (`{packet['base_commit']}`)",
        f"- Candidate input: `{packet['candidate']['input']}`",
        f"- Candidate commit: `{packet['candidate']['resolved_commit']}`",
        f"- Diff range: `{packet['comparison']['diff_range']}`",
        "",
        "## Changed Paths",
        "",
    ]
    changed_paths = packet["comparison"]["changed_paths"]
    if changed_paths:
        lines.extend(f"- `{path}`" for path in changed_paths)
    else:
        lines.append("- None")

    lines.extend(["", "## Frozen Zone", ""])
    touched = packet["frozen_zone"]["touched_paths"]
    if touched:
        lines.append("Frozen paths touched:")
        lines.extend(f"- `{path}`" for path in touched)
    else:
        lines.append("No frozen paths were changed against `origin/main`.")

    lines.extend(["", "## Protected Verification", ""])
    for command in packet["commands"]:
        status = "PASS" if command.get("ok") else "FAIL"
        lines.append(
            f"- `{command['command']}`: {status} "
            f"(exit {command['returncode']}, {command['duration_seconds']}s)"
        )

    if packet["artifacts"].get("ratification_template_md"):
        lines.extend(
            [
                "",
                "## Ratification",
                "",
                "This candidate is promotion-ready by deterministic checks. A human",
                "ratification decision is still required before promotion.",
            ]
        )
    return "\n".join(lines) + "\n"


def _ratification_template(packet: dict[str, Any]) -> str:
    changed_paths = packet["comparison"]["changed_paths"]
    path_lines = "\n".join(f"- `{path}`" for path in changed_paths) if changed_paths else "- None"
    command_lines = "\n".join(
        f"- [x] `{command['command']}` returned {command['returncode']}"
        for command in packet["commands"]
    )
    return (
        "# External Candidate Ratification Template\n\n"
        f"- Run ID: `{packet['run_id']}`\n"
        f"- Candidate commit: `{packet['candidate']['resolved_commit']}`\n"
        f"- Base commit: `{packet['base_commit']}`\n"
        f"- Outcome: `{packet['outcome']['class']}`\n\n"
        "## Deterministic Evidence\n\n"
        f"{command_lines}\n\n"
        "## Changed Paths\n\n"
        f"{path_lines}\n\n"
        "## Human Decision\n\n"
        "- Decision: approve / reject\n"
        "- Reviewer:\n"
        "- Review timestamp UTC:\n"
        "- Ratification token or record ID:\n\n"
        "## Notes\n\n"
        "Document any manual review concerns before promotion.\n"
    )


def _write_packet(packet: dict[str, Any], run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "candidate_packet.json"
    md_path = run_dir / "candidate_packet.md"
    packet["artifacts"]["candidate_packet_json"] = str(json_path.relative_to(ROOT)).replace("\\", "/")
    packet["artifacts"]["candidate_packet_md"] = str(md_path.relative_to(ROOT)).replace("\\", "/")
    if packet["outcome"]["class"] == "PROMOTION_READY":
        ratification_path = run_dir / "ratification_template.md"
        packet["artifacts"]["ratification_template_md"] = (
            str(ratification_path.relative_to(ROOT)).replace("\\", "/")
        )
    json_path.write_text(_json_dump(packet), encoding="utf-8")
    md_path.write_text(_packet_markdown(packet), encoding="utf-8")
    if packet["outcome"]["class"] == "PROMOTION_READY":
        ratification_path.write_text(_ratification_template(packet), encoding="utf-8")


def _build_packet(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    created = _now_utc()
    preflight_errors: list[str] = []
    commands: list[dict[str, Any]] = []
    changed_paths: list[str] = []
    frozen_paths: list[str] = []
    frozen_paths_touched: list[str] = []
    candidate_commit = ""
    candidate_ref_used = args.target or args.branch or ""
    input_kind = "target" if args.target else "branch"
    base_commit = ""

    try:
        _run_git("rev-parse", "--is-inside-work-tree")
        base_commit = _resolve_ref(BASE_REF)
        if args.target:
            candidate_commit = _resolve_ref(args.target)
            candidate_ref_used = args.target
        else:
            candidate_commit, candidate_ref_used = _resolve_branch(args.branch)
        changed_paths = _changed_paths(BASE_REF, candidate_commit)
        frozen_paths = _load_base_frozen_paths(BASE_REF)
        frozen_paths_touched = sorted(set(changed_paths) & set(frozen_paths))
        commands = _run_protected_commands(candidate_commit)
    except HarnessError as exc:
        preflight_errors.append(str(exc))
    except FileNotFoundError as exc:
        preflight_errors.append(f"required executable not found: {exc.filename}")
    except OSError as exc:
        preflight_errors.append(str(exc))

    outcome, reason = _classify(
        preflight_errors=preflight_errors,
        frozen_paths_touched=frozen_paths_touched,
        commands=commands,
    )
    if outcome not in OUTCOMES:
        raise AssertionError(f"unknown outcome: {outcome}")

    short = candidate_commit[:12] if candidate_commit else "unresolved"
    run_id = f"{created.strftime('%Y%m%dT%H%M%SZ')}-{short}-{uuid.uuid4().hex[:8]}"
    run_dir = PACKET_ROOT / run_id
    packet = {
        "schema": SCHEMA,
        "run_id": run_id,
        "created_utc": created.isoformat().replace("+00:00", "Z"),
        "base_ref": BASE_REF,
        "base_commit": base_commit,
        "candidate": {
            "input_kind": input_kind,
            "input": args.target if args.target else args.branch,
            "resolved_ref": candidate_ref_used,
            "resolved_commit": candidate_commit,
        },
        "comparison": {
            "diff_range": f"{BASE_REF}...{candidate_commit or '<unresolved>'}",
            "changed_path_count": len(changed_paths),
            "changed_paths": changed_paths,
        },
        "frozen_zone": {
            "manifest_source": f"{BASE_REF}:{FROZEN_MANIFEST}",
            "frozen_path_count": len(frozen_paths),
            "touched": bool(frozen_paths_touched),
            "touched_paths": frozen_paths_touched,
        },
        "commands": commands,
        "outcome": {
            "class": outcome,
            "promotion_ready": outcome == "PROMOTION_READY",
            "reason": reason,
            "preflight_errors": preflight_errors,
        },
        "artifacts": {
            "candidate_packet_json": None,
            "candidate_packet_md": None,
            "ratification_template_md": None,
        },
    }
    return packet, run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", metavar="COMMIT_SHA", help="candidate commit SHA or ref")
    group.add_argument("--branch", metavar="BRANCH_NAME", help="candidate branch name")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    packet, run_dir = _build_packet(args)
    _write_packet(packet, run_dir)

    print("SFA-Bench external candidate harness")
    print("=" * 56)
    print(f"run_id: {packet['run_id']}")
    print(f"outcome: {packet['outcome']['class']}")
    print(f"reason: {packet['outcome']['reason']}")
    print(f"candidate_packet_json: {packet['artifacts']['candidate_packet_json']}")
    print(f"candidate_packet_md: {packet['artifacts']['candidate_packet_md']}")
    if packet["artifacts"].get("ratification_template_md"):
        print(f"ratification_template_md: {packet['artifacts']['ratification_template_md']}")
    print("=" * 56)
    print(f"final status: {packet['outcome']['class']}")
    return 0 if packet["outcome"]["class"] == "PROMOTION_READY" else 2


if __name__ == "__main__":
    sys.exit(main())

