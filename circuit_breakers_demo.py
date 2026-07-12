#!/usr/bin/env python3
"""SFA-Bench v2.0.0-alpha.1 AutoLab circuit breakers demo (Item 6).

Offline, deterministic. Evaluates a clean AutoLab breaker context, then trips a
breaker with a proposed frozen-path change. The halt is appended to the
controller meta-ledger; restart is rejected without a human token and accepted
only with a sealed restart clearance plus matching token.

Run: python circuit_breakers_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from autolab import circuit_breakers as cb
from autolab import controller as ctrl
from autolab import frozen_zone as fz

TOKEN = "restart-demo-0001"


def _mini_root(path: Path) -> Path:
    (path / "autolab").mkdir(parents=True)
    (path / "guard.py").write_text("GUARD = 1\n", encoding="utf-8")
    manifest = {
        "schema": fz.SCHEMA,
        "manifest_version": "fz-demo-breakers",
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": [fz.MANIFEST_RELPATH, "guard.py"],
    }
    (path / fz.MANIFEST_RELPATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fz.seal(path)
    return path


def _clearance(halt_entry: dict) -> dict:
    return cb.seal_restart_clearance(cb.build_restart_clearance(
        clearance_id=TOKEN,
        halt_entry_hash=halt_entry[ctrl.ENTRY_HASH_KEY],
        human_reviewer="human-reviewer",
        rationale="Demo restart after reviewing the halt report.",
    ))


def main() -> int:
    print("# SFA-Bench v2.0.0-alpha.1 AutoLab circuit breakers demo")
    print("=" * 56)
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        root = _mini_root(Path(tmp) / "repo")
        ledger = Path(tmp) / "meta_ledger.jsonl"

        clean = cb.evaluate_breakers(repo_root=root, ledger_path=ledger)
        print(f"clean context          -> halted={clean.halted}")
        if clean.halted:
            failures.append(f"clean context halted unexpectedly: {clean.reasons}")

        tripped = cb.evaluate_breakers(
            repo_root=root,
            ledger_path=ledger,
            proposed_changed_paths=["guard.py"],
        )
        print(f"frozen-path proposal   -> halted={tripped.halted} reasons={tripped.reasons}")
        if cb.REASON_FROZEN_PATH_CHANGE_PROPOSED not in tripped.reasons:
            failures.append("frozen-path proposal did not trip breaker")

        halt = cb.append_halt(ledger, run_id="breaker-demo-halt", report=tripped)
        active = cb.current_halt(ledger)
        print(f"halt append            -> event={halt['event_type']} active={active is not None}")
        if active is None:
            failures.append("halt was not active after append")

        try:
            cb.append_restart_clearance(
                ledger,
                run_id="breaker-demo-restart-missing-token",
                clearance=_clearance(halt),
                restart_token=None,
            )
        except cb.CircuitBreakerError as exc:
            print(f"restart without token  -> rejected ({exc})")
        else:
            failures.append("restart without token was accepted")

        restart = cb.append_restart_clearance(
            ledger,
            run_id="breaker-demo-restart",
            clearance=_clearance(halt),
            restart_token=TOKEN,
        )
        ok, errors, count = ctrl.verify_meta_ledger(ledger)
        print(f"restart with token     -> event={restart['event_type']} active={cb.current_halt(ledger) is not None}")
        print(f"meta-ledger            -> count={count} ok={ok}")
        if not ok:
            failures.append(f"meta-ledger failed verification: {errors}")
        if cb.current_halt(ledger) is not None:
            failures.append("halt remained active after restart clearance")

    print("=" * 56)
    if failures:
        for failure in failures:
            print(f"failure: {failure}")
        print("final status: FAIL")
        return 1
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
