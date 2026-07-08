#!/usr/bin/env python3
"""Prepare human ratification packets and lineage records for external candidates."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "out" / "ratification_packets"
CANDIDATE_PACKET_SCHEMA = "sfa.external_candidate_harness.packet.v0"
RATIFICATION_PACKET_SCHEMA = "sfa.ratification_packet.v0"
LINEAGE_RECORD_SCHEMA = "sfa.ratification_packet.lineage_record.v0"
OUTCOMES = {
    "RATIFICATION_READY",
    "RATIFIED",
    "REJECTED_BY_HUMAN",
    "HALTED_BY_HUMAN",
    "LINEAGE_RECORDED",
}
ACTION_OUTCOME = {
    "prepare": "RATIFICATION_READY",
    "ratify": "RATIFIED",
    "reject": "REJECTED_BY_HUMAN",
    "halt": "HALTED_BY_HUMAN",
}
REQUIRED_TOP_LEVEL = (
    "schema",
    "run_id",
    "base_ref",
    "base_commit",
    "candidate",
    "comparison",
    "frozen_zone",
    "commands",
    "outcome",
)


class PacketError(RuntimeError):
    """Raised when a candidate packet is missing required fields."""


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PacketError(f"candidate packet not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PacketError(f"candidate packet is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PacketError("candidate packet must be a JSON object")
    return data


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _require_mapping(obj: dict[str, Any], key: str) -> dict[str, Any]:
    value = obj.get(key)
    if not isinstance(value, dict):
        raise PacketError(f"candidate packet field {key!r} must be an object")
    return value


def _require_string(obj: dict[str, Any], key: str, *, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise PacketError(f"{context} field {key!r} must be a non-empty string")
    return value


def _require_list(obj: dict[str, Any], key: str, *, context: str) -> list[Any]:
    value = obj.get(key)
    if not isinstance(value, list):
        raise PacketError(f"{context} field {key!r} must be a list")
    return value


def _validate_candidate_packet(packet: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_TOP_LEVEL if key not in packet]
    if missing:
        raise PacketError(f"candidate packet missing required field(s): {', '.join(missing)}")
    if packet.get("schema") != CANDIDATE_PACKET_SCHEMA:
        raise PacketError(
            f"candidate packet schema {packet.get('schema')!r} != "
            f"{CANDIDATE_PACKET_SCHEMA!r}"
        )
    _require_string(packet, "run_id", context="candidate packet")
    _require_string(packet, "base_ref", context="candidate packet")
    _require_string(packet, "base_commit", context="candidate packet")

    candidate = _require_mapping(packet, "candidate")
    _require_string(candidate, "resolved_ref", context="candidate")
    _require_string(candidate, "resolved_commit", context="candidate")

    comparison = _require_mapping(packet, "comparison")
    changed_paths = _require_list(comparison, "changed_paths", context="comparison")
    if not all(isinstance(path, str) for path in changed_paths):
        raise PacketError("comparison field 'changed_paths' must contain only strings")

    frozen_zone = _require_mapping(packet, "frozen_zone")
    touched_paths = _require_list(frozen_zone, "touched_paths", context="frozen_zone")
    if not all(isinstance(path, str) for path in touched_paths):
        raise PacketError("frozen_zone field 'touched_paths' must contain only strings")
    if not isinstance(frozen_zone.get("touched"), bool):
        raise PacketError("frozen_zone field 'touched' must be a boolean")

    commands = _require_list(packet, "commands", context="candidate packet")
    for index, command in enumerate(commands, start=1):
        if not isinstance(command, dict):
            raise PacketError(f"commands[{index}] must be an object")
        _require_string(command, "command", context=f"commands[{index}]")
        if not isinstance(command.get("returncode"), int):
            raise PacketError(f"commands[{index}] field 'returncode' must be an integer")
        if not isinstance(command.get("ok"), bool):
            raise PacketError(f"commands[{index}] field 'ok' must be a boolean")

    outcome = _require_mapping(packet, "outcome")
    _require_string(outcome, "class", context="outcome")


def _safe_run_id(raw: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in raw)
    return safe.strip("-") or "candidate"


def _command_summary(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for command in commands:
        entry = {
            "name": command.get("name"),
            "command": command.get("command"),
            "argv": command.get("argv"),
            "ok": command.get("ok"),
            "returncode": command.get("returncode"),
            "duration_seconds": command.get("duration_seconds"),
            "failure_outcome": command.get("failure_outcome"),
        }
        summary.append({key: value for key, value in entry.items() if value is not None})
    return summary


def _human_action(action: str, timestamp_utc: str, rationale: str) -> dict[str, Any]:
    return {
        "action": action,
        "timestamp_utc": timestamp_utc,
        "rationale": rationale,
        "explicit": action in {"ratify", "reject", "halt"},
    }


def _build_ratification_packet(
    *,
    candidate_packet: dict[str, Any],
    candidate_packet_path: Path,
    candidate_packet_hash: str,
    action: str,
    rationale: str,
    run_id: str,
    created_utc: str,
) -> dict[str, Any]:
    candidate = candidate_packet["candidate"]
    comparison = candidate_packet["comparison"]
    frozen_zone = candidate_packet["frozen_zone"]
    outcome_class = ACTION_OUTCOME[action]
    return {
        "schema": RATIFICATION_PACKET_SCHEMA,
        "run_id": run_id,
        "created_utc": created_utc,
        "source_candidate_packet": {
            "path": _relpath(candidate_packet_path),
            "sha256": candidate_packet_hash,
            "run_id": candidate_packet["run_id"],
            "outcome_class": candidate_packet["outcome"]["class"],
            "promotion_ready": candidate_packet["outcome"].get("promotion_ready") is True,
        },
        "target": {
            "target_ref": candidate["resolved_ref"],
            "target_commit": candidate["resolved_commit"],
            "candidate_input": candidate.get("input"),
            "candidate_input_kind": candidate.get("input_kind"),
        },
        "base": {
            "base_ref": candidate_packet["base_ref"],
            "base_commit": candidate_packet["base_commit"],
        },
        "changed_files": list(comparison["changed_paths"]),
        "verification_results": _command_summary(candidate_packet["commands"]),
        "frozen_path_status": {
            "touched": frozen_zone["touched"],
            "touched_paths": list(frozen_zone["touched_paths"]),
            "manifest_source": frozen_zone.get("manifest_source"),
            "frozen_path_count": frozen_zone.get("frozen_path_count"),
        },
        "human_action": _human_action(action, created_utc, rationale),
        "outcome": {
            "class": outcome_class,
            "lineage_recorded": True,
            "auto_promoted": False,
            "reason": _outcome_reason(action, candidate_packet),
        },
        "artifacts": {
            "ratification_packet_json": None,
            "ratification_packet_md": None,
            "lineage_record_json": None,
        },
    }


def _build_lineage_record(
    *,
    ratification_packet: dict[str, Any],
    created_utc: str,
) -> dict[str, Any]:
    return {
        "schema": LINEAGE_RECORD_SCHEMA,
        "lineage_record_id": f"lineage-{ratification_packet['run_id']}",
        "created_utc": created_utc,
        "source_ratification_run_id": ratification_packet["run_id"],
        "source_candidate_run_id": ratification_packet["source_candidate_packet"]["run_id"],
        "target_ref": ratification_packet["target"]["target_ref"],
        "target_commit": ratification_packet["target"]["target_commit"],
        "base_ref": ratification_packet["base"]["base_ref"],
        "base_commit": ratification_packet["base"]["base_commit"],
        "changed_files": list(ratification_packet["changed_files"]),
        "verification_results": list(ratification_packet["verification_results"]),
        "frozen_path_status": dict(ratification_packet["frozen_path_status"]),
        "human_action": dict(ratification_packet["human_action"]),
        "ratification_outcome": ratification_packet["outcome"]["class"],
        "outcome": {
            "class": "LINEAGE_RECORDED",
            "auto_promoted": False,
            "promotion_effect": "none",
            "reason": "decision lineage recorded; no promotion was performed",
        },
    }


def _outcome_reason(action: str, candidate_packet: dict[str, Any]) -> str:
    candidate_outcome = candidate_packet["outcome"]["class"]
    if action == "prepare":
        return f"ratification packet prepared for candidate outcome {candidate_outcome}"
    if action == "ratify":
        return "human explicitly ratified a promotion-ready candidate"
    if action == "reject":
        return "human explicitly rejected the candidate"
    if action == "halt":
        return "human explicitly halted the candidate workflow"
    raise AssertionError(f"unknown action: {action}")


def _packet_markdown(packet: dict[str, Any], lineage_record: dict[str, Any]) -> str:
    changed_files = packet["changed_files"]
    changed = "\n".join(f"- `{path}`" for path in changed_files) if changed_files else "- None"
    touched = packet["frozen_path_status"]["touched_paths"]
    touched_lines = "\n".join(f"- `{path}`" for path in touched) if touched else "- None"
    checks = "\n".join(
        f"- `{command['command']}`: {'PASS' if command['ok'] else 'FAIL'} "
        f"(exit {command['returncode']})"
        for command in packet["verification_results"]
    )
    return (
        "# Ratification Packet\n\n"
        f"- Run ID: `{packet['run_id']}`\n"
        f"- Outcome: `{packet['outcome']['class']}`\n"
        f"- Lineage outcome: `{lineage_record['outcome']['class']}`\n"
        f"- Auto-promoted: `false`\n"
        f"- Candidate packet: `{packet['source_candidate_packet']['path']}`\n"
        f"- Candidate outcome: `{packet['source_candidate_packet']['outcome_class']}`\n"
        f"- Target ref: `{packet['target']['target_ref']}`\n"
        f"- Target commit: `{packet['target']['target_commit']}`\n"
        f"- Base ref: `{packet['base']['base_ref']}`\n"
        f"- Base commit: `{packet['base']['base_commit']}`\n"
        f"- Human action: `{packet['human_action']['action']}`\n"
        f"- Human timestamp UTC: `{packet['human_action']['timestamp_utc']}`\n"
        f"- Rationale: {packet['human_action']['rationale'] or '_empty_'}\n\n"
        "## Changed Files\n\n"
        f"{changed}\n\n"
        "## Verification Results\n\n"
        f"{checks or '- None'}\n\n"
        "## Frozen-Path Status\n\n"
        f"- Touched frozen paths: `{str(packet['frozen_path_status']['touched']).lower()}`\n"
        f"{touched_lines}\n\n"
        "## Lineage Record\n\n"
        f"- Lineage record ID: `{lineage_record['lineage_record_id']}`\n"
        "- Promotion effect: `none`\n"
    )


def _write_outputs(
    *,
    ratification_packet: dict[str, Any],
    lineage_record: dict[str, Any],
    run_dir: Path,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    packet_json = run_dir / "ratification_packet.json"
    packet_md = run_dir / "ratification_packet.md"
    lineage_json = run_dir / "lineage_record.json"

    ratification_packet["artifacts"]["ratification_packet_json"] = _relpath(packet_json)
    ratification_packet["artifacts"]["ratification_packet_md"] = _relpath(packet_md)
    ratification_packet["artifacts"]["lineage_record_json"] = _relpath(lineage_json)

    packet_json.write_text(_json_dump(ratification_packet), encoding="utf-8")
    lineage_json.write_text(_json_dump(lineage_record), encoding="utf-8")
    packet_md.write_text(_packet_markdown(ratification_packet, lineage_record), encoding="utf-8")


def _action_from_args(args: argparse.Namespace) -> str:
    for action in ("prepare", "ratify", "reject", "halt"):
        if getattr(args, action):
            return action
    raise AssertionError("argparse should require one action")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, help="path to candidate_packet.json")
    parser.add_argument(
        "--rationale",
        default="",
        help="optional human rationale to record in the packet",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true", help="prepare packet for review")
    group.add_argument("--ratify", action="store_true", help="record explicit human ratification")
    group.add_argument("--reject", action="store_true", help="record explicit human rejection")
    group.add_argument("--halt", action="store_true", help="record explicit human halt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    action = _action_from_args(args)
    packet_path = Path(args.packet)
    if not packet_path.is_absolute():
        packet_path = ROOT / packet_path

    try:
        candidate_packet = _read_json(packet_path)
        _validate_candidate_packet(candidate_packet)
        candidate_outcome = candidate_packet["outcome"]["class"]
        if action == "ratify" and candidate_outcome != "PROMOTION_READY":
            raise PacketError(
                f"refusing --ratify: candidate outcome is {candidate_outcome}, "
                "expected PROMOTION_READY"
            )
        created = _now_utc()
        created_utc = created.isoformat().replace("+00:00", "Z")
        candidate_run_id = _safe_run_id(candidate_packet["run_id"])
        run_id = f"{candidate_run_id}-{action}-{created.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = OUTPUT_ROOT / run_id
        ratification_packet = _build_ratification_packet(
            candidate_packet=candidate_packet,
            candidate_packet_path=packet_path,
            candidate_packet_hash=_file_sha256(packet_path),
            action=action,
            rationale=args.rationale,
            run_id=run_id,
            created_utc=created_utc,
        )
        lineage_record = _build_lineage_record(
            ratification_packet=ratification_packet,
            created_utc=created_utc,
        )
        _write_outputs(
            ratification_packet=ratification_packet,
            lineage_record=lineage_record,
            run_dir=run_dir,
        )
    except PacketError as exc:
        print("SFA-Bench ratification packet CLI")
        print("=" * 56)
        print(f"failure: {exc}")
        print("=" * 56)
        print("final status: HALTED_BY_HUMAN")
        return 2

    print("SFA-Bench ratification packet CLI")
    print("=" * 56)
    print(f"run_id: {ratification_packet['run_id']}")
    print(f"ratification_outcome: {ratification_packet['outcome']['class']}")
    print(f"lineage_outcome: {lineage_record['outcome']['class']}")
    print(f"ratification_packet_json: {ratification_packet['artifacts']['ratification_packet_json']}")
    print(f"ratification_packet_md: {ratification_packet['artifacts']['ratification_packet_md']}")
    print(f"lineage_record_json: {ratification_packet['artifacts']['lineage_record_json']}")
    print("=" * 56)
    print(f"final status: {lineage_record['outcome']['class']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
