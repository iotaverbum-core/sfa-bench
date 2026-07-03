"""Deterministic baseline report for the Frontier Delta Suite.

Aggregates per-task scorer results into a sealed report: total score, per-lane and
per-task scores, failure-mode tally, replay status, and a hash-chained
``results_root_hash`` that reuses the SFA-Bench occurrence-ledger pattern
(GENESIS -> prev_hash -> entry_hash). The report is a pure function of its inputs;
``generated_at`` is metadata and is deliberately excluded from ``report_hash`` so
the sealed content stays byte-stable across wall-clock time.
"""
from __future__ import annotations

from typing import Any

from sfa.hashing import sha256_hex

from . import schemas

GENESIS = "GENESIS"

NON_AGI_WARNING = (
    "This is a measured behavioural baseline under specific benchmark pressure across "
    "eight lanes (truth, state, objective, and accountability preservation on long, "
    "open-ended, tool-mediated tasks). It is NOT a claim of AGI, general intelligence, "
    "or overall model quality. Deltas against later candidate models must be read only "
    "as behavioural differences on this frozen suite."
)


def _chain_results(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Hash-chain result hashes (SFA-Bench ledger pattern). Returns (entries, root)."""
    prev = GENESIS
    entries = []
    for seq, result in enumerate(results):
        entry = {"seq": seq, "task_id": result["task_id"], "result_hash": result["result_hash"], "prev_hash": prev}
        entry["entry_hash"] = sha256_hex(entry)
        prev = entry["entry_hash"]
        entries.append(entry)
    return entries, prev


def build_report(
    model: str,
    results: list[dict[str, Any]],
    *,
    suite_version: str = schemas.SUITE_VERSION,
    generated_at: str | None = None,
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the sealed baseline report from ordered per-task results."""
    results = sorted(results, key=lambda r: r["task_id"])

    per_task = [
        {
            "task_id": r["task_id"],
            "lane": r["lane"],
            "score": r["score"],
            "verdict": r["verdict"],
            "scoring_mode": r["scoring_mode"],
            "detected_failure_modes": r["detected_failure_modes"],
            "replay_possible": r["replay_possible"],
            "result_hash": r["result_hash"],
        }
        for r in results
    ]

    # Per-lane rollup (each lane has exactly one task in v0, but keep it general).
    per_lane: dict[str, Any] = {}
    for lane in schemas.LANES:
        lane_results = [r for r in results if r["lane"] == lane]
        if not lane_results:
            per_lane[lane] = {"score": None, "verdict": "absent", "task_ids": []}
            continue
        mean = round(sum(r["score"] for r in lane_results) / len(lane_results), 6)
        verdicts = {r["verdict"] for r in lane_results}
        rollup = "pass" if verdicts == {"pass"} else ("fail" if "fail" in verdicts else "partial")
        per_lane[lane] = {
            "score": mean,
            "verdict": rollup,
            "task_ids": sorted(r["task_id"] for r in lane_results),
        }

    total_score = round(sum(r["score"] for r in results) / len(results), 6) if results else 0.0
    verdict_counts = {v: sum(1 for r in results if r["verdict"] == v) for v in ("pass", "partial", "fail")}

    failure_tally: dict[str, int] = {}
    for r in results:
        for mode in r["detected_failure_modes"]:
            failure_tally[mode] = failure_tally.get(mode, 0) + 1
    failure_modes = [
        {"failure_mode": mode, "count": count}
        for mode, count in sorted(failure_tally.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    replayable = sum(1 for r in results if r["replay_possible"])
    replay_status = {
        "all_replayable": replayable == len(results) and bool(results),
        "replayable": replayable,
        "total": len(results),
    }

    ledger_entries, results_root_hash = _chain_results(results)

    sealed = {
        "schema": schemas.REPORT_SCHEMA_VERSION,
        "suite_name": "Frontier Delta Suite",
        "suite_version": suite_version,
        "model": model,
        "total_score": total_score,
        "verdict_counts": verdict_counts,
        "per_lane": per_lane,
        "per_task": per_task,
        "failure_modes": failure_modes,
        "replay_status": replay_status,
        "ledger": {
            "pattern": "sfa.ledger hash-chain (GENESIS -> prev_hash -> entry_hash)",
            "entries": ledger_entries,
            "results_root_hash": results_root_hash,
        },
        "task_count": len(results),
        "non_agi_warning": NON_AGI_WARNING,
    }
    # report_hash seals only deterministic content (generated_at excluded on purpose).
    report_hash = sha256_hex(sealed)

    report = dict(sealed)
    report["report_hash"] = report_hash
    report["generated_at"] = generated_at  # metadata, not part of report_hash
    return report


def render_text(report: dict[str, Any]) -> str:
    """Human-readable one-screen summary of a report."""
    lines = []
    lines.append(f"{report['suite_name']} — {report['suite_version']}")
    lines.append(f"model: {report['model']}    generated_at: {report.get('generated_at')}")
    lines.append(f"total score: {report['total_score']:.3f}    verdicts: {report['verdict_counts']}")
    lines.append("")
    lines.append("per-lane:")
    for lane, row in report["per_lane"].items():
        score = "  n/a" if row["score"] is None else f"{row['score']:.3f}"
        lines.append(f"  {lane:<30} {score}  {row['verdict']}")
    lines.append("")
    lines.append("per-task:")
    for row in report["per_task"]:
        modes = ", ".join(row["detected_failure_modes"]) or "-"
        lines.append(
            f"  {row['task_id']:<28} {row['score']:.3f}  {row['verdict']:<7} "
            f"[{row['scoring_mode']}]  failures: {modes}"
        )
    lines.append("")
    rs = report["replay_status"]
    lines.append(f"replay: {rs['replayable']}/{rs['total']} replayable  (all={rs['all_replayable']})")
    lines.append(f"results_root_hash: {report['ledger']['results_root_hash']}")
    lines.append(f"report_hash: {report['report_hash']}")
    lines.append("")
    lines.append("WARNING: " + report["non_agi_warning"])
    return "\n".join(lines)
