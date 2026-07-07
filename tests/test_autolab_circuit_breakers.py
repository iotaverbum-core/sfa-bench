"""Deterministic tests for AutoLab circuit breakers (Item 6)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import circuit_breakers as cb  # noqa: E402
from autolab import controller as ctrl  # noqa: E402
from autolab import frozen_zone as fz  # noqa: E402

RESTART_TOKEN = "restart-item-6-0001"


def _mini_root(path: Path) -> Path:
    (path / "autolab").mkdir(parents=True)
    (path / "guard.py").write_text("GUARD = 1\n", encoding="utf-8")
    manifest = {
        "schema": fz.SCHEMA,
        "manifest_version": "fz-test-breakers",
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": [fz.MANIFEST_RELPATH, "guard.py"],
    }
    (path / fz.MANIFEST_RELPATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fz.seal(path)
    return path


def _rejection(ledger: Path, run_id: str, lineage_id: str = "patch-a") -> dict:
    return ctrl.append_meta_event(
        ledger,
        event_type="gate_rejected",
        run_id=run_id,
        payload={
            "lineage_id": lineage_id,
            "gate_green": False,
            "reasons": ["protected metric regressed"],
        },
    )


def _clearance(halt_entry: dict) -> dict:
    return cb.seal_restart_clearance(cb.build_restart_clearance(
        clearance_id=RESTART_TOKEN,
        halt_entry_hash=halt_entry[ctrl.ENTRY_HASH_KEY],
        human_reviewer="human-reviewer",
        rationale="Reviewed halt report and authorized a controlled restart.",
    ))


class BreakerEvaluationTests(unittest.TestCase):
    def test_clean_context_does_not_halt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(repo_root=root, ledger_path=ledger)
            self.assertFalse(report.halted, report.reasons)
            self.assertEqual(report.reasons, [])
            cb.require_sealed_report(report.to_dict())

    def test_zone_hash_mismatch_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                expected_zone_hash="0" * 64,
            )
            self.assertTrue(report.halted)
            self.assertIn(cb.REASON_ZONE_HASH_MISMATCH, report.reasons)

    def test_chain_break_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            ctrl.append_meta_event(ledger, event_type="builder_completed", run_id="r1", payload={"ok": True})
            lines = ledger.read_text(encoding="utf-8").splitlines()
            edited = json.loads(lines[0])
            edited["payload"]["ok"] = False
            lines[0] = json.dumps(edited, sort_keys=True)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

            report = cb.evaluate_breakers(repo_root=root, ledger_path=ledger)
            self.assertTrue(report.halted)
            self.assertIn(cb.REASON_CHAIN_BREAK, report.reasons)
            self.assertFalse(report.checks["meta_ledger_ok"])

    def test_holdout_budget_exhausted_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            ctrl.append_meta_event(
                ledger,
                event_type="holdout_budget_consumed",
                run_id="holdout-run",
                payload={
                    "budget_id": "holdout:demo",
                    "units": 1,
                    "used_before": 0,
                    "used_after": 1,
                    "remaining_after": 0,
                },
            )
            report = cb.evaluate_breakers(repo_root=root, ledger_path=ledger)
            self.assertIn(cb.REASON_HOLDOUT_BUDGET_EXHAUSTED, report.reasons)

    def test_consecutive_rejections_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            for index in range(3):
                _rejection(ledger, f"reject-{index}")
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                max_consecutive_rejections=3,
            )
            self.assertIn(cb.REASON_CONSECUTIVE_REJECTIONS, report.reasons)
            self.assertEqual(report.checks["trailing_rejections"], 3)

    def test_success_resets_consecutive_rejection_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            _rejection(ledger, "reject-1")
            _rejection(ledger, "reject-2")
            ctrl.append_meta_event(
                ledger,
                event_type="promotion_inscribed",
                run_id="success",
                payload={"schema": "test", "target": "ok"},
            )
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                max_consecutive_rejections=2,
            )
            self.assertNotIn(cb.REASON_CONSECUTIVE_REJECTIONS, report.reasons)
            self.assertEqual(report.checks["trailing_rejections"], 0)

    def test_frozen_path_change_proposed_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_changed_paths=["guard.py"],
            )
            self.assertIn(cb.REASON_FROZEN_PATH_CHANGE_PROPOSED, report.reasons)
            self.assertEqual(report.checks["frozen_paths_touched"], ["guard.py"])

    def test_cost_or_time_budget_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                cost_spent=12.5,
                max_cost=10.0,
                seconds_spent=90,
                max_seconds=60,
            )
            self.assertIn(cb.REASON_COST_TIME_BUDGET_EXCEEDED, report.reasons)
            self.assertTrue(report.checks["cost_budget_exceeded"])
            self.assertTrue(report.checks["time_budget_exceeded"])

    def test_withered_lineage_trips_only_when_reproposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            for index in range(3):
                _rejection(ledger, f"reject-{index}", lineage_id="patch-a")
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_lineage_id="patch-a",
                wither_threshold=3,
            )
            self.assertIn(cb.REASON_LINEAGE_WITHERED, report.reasons)
            directives = report.checks["caution_directives"]
            self.assertEqual(directives[0]["lineage_id"], "patch-a")
            self.assertTrue(directives[0]["withered"])
            self.assertTrue(directives[0]["excluded_from_gate"])


class HaltRestartTests(unittest.TestCase):
    def test_halt_appends_and_duplicate_halt_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_changed_paths=["guard.py"],
            )
            entry = cb.append_halt(ledger, run_id="halt-run", report=report)
            self.assertEqual(entry["event_type"], cb.EVENT_HALTED)
            self.assertEqual(cb.current_halt(ledger)[ctrl.ENTRY_HASH_KEY], entry[ctrl.ENTRY_HASH_KEY])
            with self.assertRaisesRegex(cb.CircuitBreakerError, "active halt"):
                cb.append_halt(ledger, run_id="halt-run-2", report=report)

    def test_non_halted_report_cannot_append_halt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(repo_root=root, ledger_path=ledger)
            with self.assertRaisesRegex(cb.CircuitBreakerError, "non-halted"):
                cb.append_halt(ledger, run_id="halt-run", report=report)
            self.assertEqual(ctrl.read_meta_ledger(ledger), [])

    def test_restart_requires_token_and_clears_active_halt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_changed_paths=["guard.py"],
            )
            halt = cb.append_halt(ledger, run_id="halt-run", report=report)
            clearance = _clearance(halt)

            with self.assertRaisesRegex(cb.CircuitBreakerError, "token missing"):
                cb.append_restart_clearance(
                    ledger,
                    run_id="restart-run",
                    clearance=clearance,
                    restart_token=None,
                )
            self.assertIsNotNone(cb.current_halt(ledger))

            entry = cb.append_restart_clearance(
                ledger,
                run_id="restart-run",
                clearance=clearance,
                restart_token=RESTART_TOKEN,
            )
            self.assertEqual(entry["event_type"], cb.EVENT_RESTART_AUTHORIZED)
            self.assertIsNone(cb.current_halt(ledger))

    def test_restart_clearance_must_bind_active_halt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_changed_paths=["guard.py"],
            )
            cb.append_halt(ledger, run_id="halt-run", report=report)
            clearance = cb.seal_restart_clearance(cb.build_restart_clearance(
                clearance_id=RESTART_TOKEN,
                halt_entry_hash="0" * 64,
                human_reviewer="human-reviewer",
                rationale="Wrong halt hash.",
            ))
            with self.assertRaisesRegex(cb.CircuitBreakerError, "active halt"):
                cb.append_restart_clearance(
                    ledger,
                    run_id="restart-run",
                    clearance=clearance,
                    restart_token=RESTART_TOKEN,
                )

    def test_tampered_restart_clearance_raises(self):
        clearance = cb.seal_restart_clearance(cb.build_restart_clearance(
            clearance_id=RESTART_TOKEN,
            halt_entry_hash="1" * 64,
            human_reviewer="human-reviewer",
            rationale="Reviewed.",
        ))
        clearance["rationale"] = "Edited after sealing."
        with self.assertRaisesRegex(cb.CircuitBreakerError, "clearance_hash"):
            cb.require_sealed_restart_clearance(clearance)


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_circuit_breaker_module_is_frozen(self):
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/circuit_breakers.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.6.0-add-circuit-breakers")
        self.assertIsNotNone(record, "fz-v0.6.0 amendment record missing")
        self.assertEqual(record["new_zone_hash"], manifest["zone_hash"])
        self.assertIn("autolab/circuit_breakers.py", record["applies_to"])


if __name__ == "__main__":
    unittest.main()
