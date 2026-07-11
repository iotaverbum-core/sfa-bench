#!/usr/bin/env python3
"""Frontier Delta Suite runner (fixture-based, deterministic, offline).

Runs the frozen suite against a stored model-output fixture so CI can evaluate
without any live API call. Live model integration is intentionally out of scope
for v0; the fixture path is the contract.

Example:

  python -m sfa_bench.frontier_delta.runner \\
      --suite frontier_delta_v0 \\
      --model gpt-5.5 \\
      --input sfa_bench/frontier_delta/fixtures/gpt55_outputs.jsonl \\
      --out out/frontier_delta_gpt55_baseline
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from . import report as report_mod
from . import schemas
from .scorers import score_task
from .tasks import load_tasks


def load_output_fixture(path: str | Path) -> dict[str, dict[str, Any] | None]:
    """Load a JSONL model-output fixture into {task_id: output}."""
    outputs: dict[str, dict[str, Any] | None] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            record = json.loads(line)
            task_id = record.get("task_id")
            if not task_id:
                raise ValueError(f"{path}:{line_no}: record missing task_id")
            outputs[task_id] = record.get("output")
    return outputs


def run_suite(
    model: str,
    outputs: dict[str, dict[str, Any] | None],
    *,
    generated_at: str | None = None,
    suite_version: str = schemas.SUITE_VERSION,
) -> dict[str, Any]:
    """Score every suite task against the provided outputs; return a sealed report.

    Pure and deterministic given (model, outputs, generated_at). Missing outputs
    are scored as an explicit failure rather than skipped.
    """
    tasks = load_tasks()
    results = [score_task(task, outputs.get(task["task_id"])) for task in tasks]
    return report_mod.build_report(
        model, results, suite_version=suite_version, generated_at=generated_at, tasks=tasks
    )


def _write_artifacts(report: dict[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    report_path = out_dir / "baseline_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    written.append(report_path)

    results_path = out_dir / "per_task_results.jsonl"
    with results_path.open("w", encoding="utf-8") as fh:
        for row in report["per_task"]:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    written.append(results_path)

    summary_path = out_dir / "summary.txt"
    summary_path.write_text(report_mod.render_text(report) + "\n", encoding="utf-8")
    written.append(summary_path)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=schemas.SUITE_VERSION, help="suite version (frozen: frontier_delta_v0)")
    parser.add_argument("--model", required=True, help="model label, e.g. gpt-5.5")
    parser.add_argument("--input", required=True, help="JSONL model-output fixture")
    parser.add_argument("--out", help="output directory for report + artifacts")
    parser.add_argument("--now", help="ISO timestamp to stamp as generated_at (default: current UTC)")
    args = parser.parse_args(argv)

    print(f"Frontier Delta Suite v0 — {args.suite}")
    print("=" * 60)

    if args.suite != schemas.SUITE_VERSION:
        print(f"error: unknown suite {args.suite!r} (frozen suite is {schemas.SUITE_VERSION!r})")
        return 2

    outputs = load_output_fixture(args.input)
    generated_at = args.now or _dt.datetime.now(_dt.timezone.utc).isoformat()
    report = run_suite(args.model, outputs, generated_at=generated_at, suite_version=args.suite)

    print(report_mod.render_text(report))

    if args.out:
        written = _write_artifacts(report, Path(args.out))
        print("")
        print("artifacts written:")
        for path in written:
            print(f"  - {path}")

    print("=" * 60)
    # A run always "succeeds" as a measurement; the report carries pass/fail per lane.
    print(f"final status: MEASURED (total_score={report['total_score']:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
