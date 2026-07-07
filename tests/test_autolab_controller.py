"""Deterministic tests for the AutoLab controller (Item 3)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import controller as ctrl  # noqa: E402
from autolab import frozen_zone as fz  # noqa: E402
from autolab import preregistration as pre  # noqa: E402


def _eval_plan(*, holdout: bool = False) -> dict:
    plan = {
        "suite": "public+holdout" if holdout else "public",
        "arms": ["candidate", "incumbent", "ancestor_anchor"],
        "seeds": [11, 12, 13],
        "n": 12,
        "bootstrap": 200,
    }
    if holdout:
        plan["holdout"] = {
            "budget_id": "frontier-delta-holdout:hd-v0.1.0",
            "suite": "frontier-delta-holdout",
            "version": "hd-v0.1.0",
            "units": 1,
        }
    return plan


def _declaration(*, holdout: bool = False, eval_plan: dict | None = None) -> dict:
    return pre.build_declaration(
        declaration_id="controller-test",
        target_metric="continual_learning_score",
        direction="increase",
        min_delta=0.05,
        decision_rule="ci95_low_gt_0",
        comparator="incumbent",
        eval_plan=eval_plan if eval_plan is not None else _eval_plan(holdout=holdout),
        protected_metrics=[
            {"name": "public_suite_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "verifier_latency_ms", "direction": "no_increase", "tolerance": 5.0},
        ],
    )


def _budget(max_uses: int = 1) -> dict:
    return ctrl.build_holdout_budget(
        budget_id="frontier-delta-holdout:hd-v0.1.0",
        suite="frontier-delta-holdout",
        version="hd-v0.1.0",
        max_uses=max_uses,
    )


def _mini_controller_root(path: Path) -> Path:
    (path / "autolab").mkdir(parents=True)
    (path / "guard.txt").write_text("controller guard\n", encoding="utf-8")
    manifest = {
        "schema": fz.SCHEMA,
        "manifest_version": "fz-test-controller",
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": [fz.MANIFEST_RELPATH, "guard.txt"],
    }
    (path / fz.MANIFEST_RELPATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fz.seal(path)
    return path


def _event_types(path: Path) -> list[str]:
    return [entry["event_type"] for entry in ctrl.read_meta_ledger(path)]


class ControllerTemporalTests(unittest.TestCase):
    def test_declaration_is_in_meta_ledger_before_builder_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            seen_inside_builder: list[list[str]] = []

            def builder(sealed: dict) -> dict:
                self.assertIn("declaration_hash", sealed)
                seen_inside_builder.append(_event_types(ledger))
                return {"patch_id": "candidate-1", "status": "built"}

            result = ctrl.run_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="run-temporal",
                declaration=_declaration(),
                builder=builder,
            )

            self.assertEqual(seen_inside_builder, [[
                "zone_attested_pre",
                "declaration_sealed",
                "builder_invoked",
            ]])
            final_events = _event_types(ledger)
            self.assertEqual(final_events, [
                "zone_attested_pre",
                "declaration_sealed",
                "builder_invoked",
                "builder_completed",
                "zone_attested_post",
            ])
            self.assertLess(final_events.index("declaration_sealed"), final_events.index("builder_invoked"))
            self.assertEqual(result.pre_zone_hash, result.post_zone_hash)
            self.assertEqual(result.ledger_root, ctrl.meta_ledger_root(ledger))

    def test_builder_result_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            builder_result = {"patch_id": "candidate-2", "files_changed": ["docs/x.md"]}

            result = ctrl.run_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="run-hash",
                declaration=_declaration(),
                builder=lambda _sealed: builder_result,
            )

            completed = [
                e for e in ctrl.read_meta_ledger(ledger)
                if e["event_type"] == "builder_completed"
            ][0]
            self.assertEqual(result.builder_result_hash, ctrl.sha256_hex(builder_result))
            self.assertEqual(completed["payload"]["builder_result_hash"], result.builder_result_hash)


class HoldoutBudgetTests(unittest.TestCase):
    def test_holdout_budget_is_consumed_before_builder_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            seen_inside_builder: list[list[str]] = []

            def builder(_sealed: dict) -> dict:
                seen_inside_builder.append(_event_types(ledger))
                return {"patch_id": "candidate-holdout"}

            first = ctrl.run_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="run-holdout-1",
                declaration=_declaration(holdout=True),
                builder=builder,
                holdout_budget=_budget(max_uses=1),
            )

            self.assertIsNotNone(first.holdout_entry)
            self.assertEqual(seen_inside_builder, [[
                "zone_attested_pre",
                "declaration_sealed",
                "holdout_budget_consumed",
                "builder_invoked",
            ]])
            receipt = first.holdout_entry["payload"]
            self.assertEqual(receipt["used_before"], 0)
            self.assertEqual(receipt["used_after"], 1)
            self.assertEqual(receipt["remaining_after"], 0)

            called = False

            def should_not_run(_sealed: dict) -> dict:
                nonlocal called
                called = True
                return {}

            with self.assertRaises(ctrl.ControllerError):
                ctrl.run_iteration(
                    repo_root=root,
                    ledger_path=ledger,
                    run_id="run-holdout-2",
                    declaration=_declaration(holdout=True),
                    builder=should_not_run,
                    holdout_budget=_budget(max_uses=1),
                )
            self.assertFalse(called)
            self.assertEqual(_event_types(ledger).count("holdout_budget_consumed"), 1)

    def test_holdout_suite_requires_explicit_budget_binding(self):
        plan = _eval_plan(holdout=False)
        plan["suite"] = "public+holdout"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            called = False

            def builder(_sealed: dict) -> dict:
                nonlocal called
                called = True
                return {}

            with self.assertRaisesRegex(ctrl.ControllerError, "explicit eval_plan.holdout"):
                ctrl.run_iteration(
                    repo_root=root,
                    ledger_path=ledger,
                    run_id="run-missing-holdout",
                    declaration=_declaration(eval_plan=plan),
                    builder=builder,
                    holdout_budget=_budget(),
                )
            self.assertFalse(called)

    def test_holdout_budget_identity_must_match_declaration(self):
        budget = _budget(max_uses=1)
        budget["version"] = "wrong-version"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            with self.assertRaisesRegex(ctrl.ControllerError, "version mismatch"):
                ctrl.run_iteration(
                    repo_root=root,
                    ledger_path=ledger,
                    run_id="run-bad-budget",
                    declaration=_declaration(holdout=True),
                    builder=lambda _sealed: {},
                    holdout_budget=budget,
                )


class MetaLedgerTests(unittest.TestCase):
    def test_tampered_meta_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            root = _mini_controller_root(workspace / "repo")
            ledger = workspace / "meta.jsonl"
            ctrl.run_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="run-clean",
                declaration=_declaration(),
                builder=lambda _sealed: {"patch_id": "candidate"},
            )
            lines = ledger.read_text(encoding="utf-8").splitlines()
            edited = json.loads(lines[1])
            edited["payload"]["declaration"]["declaration_id"] = "edited-after-the-fact"
            lines[1] = json.dumps(edited, sort_keys=True)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

            ok, errors, count = ctrl.verify_meta_ledger(ledger)
            self.assertFalse(ok)
            self.assertEqual(count, 5)
            self.assertTrue(any("entry hash mismatch" in message for _, message in errors))

            with self.assertRaises(ctrl.ControllerError):
                ctrl.run_iteration(
                    repo_root=root,
                    ledger_path=ledger,
                    run_id="run-after-tamper",
                    declaration=_declaration(),
                    builder=lambda _sealed: {},
                )


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_controller_module_is_frozen(self):
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/controller.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.3.0-add-controller")
        self.assertIsNotNone(record, "fz-v0.3.0 amendment record missing")
        self.assertIn("autolab/controller.py", record["applies_to"])
        if record["new_zone_hash"] == manifest["zone_hash"]:
            return
        successor = amendments.get("fz-v0.4.0-add-ratification")
        self.assertIsNotNone(successor, "v0.3.0 amendment must be linked by a successor")
        self.assertEqual(successor["prev_zone_hash"], record["new_zone_hash"])
        self.assertEqual(successor["new_zone_hash"], manifest["zone_hash"])


if __name__ == "__main__":
    unittest.main()