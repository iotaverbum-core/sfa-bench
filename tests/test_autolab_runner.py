"""Deterministic tests for the end-to-end AutoLab runner (Item 7)."""
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
from autolab import lineage as lin  # noqa: E402
from autolab import preregistration as pre  # noqa: E402
from autolab import ratification as rat  # noqa: E402
from autolab import runner  # noqa: E402

RATIFY_TOKEN = "ratify-runner-0001"
TARGET_REF = {
    "type": "git_commit",
    "sha": "7777777777777777777777777777777777777777",
    "branch": "candidate/item-7",
}
PREVIOUS_REF = {
    "type": "git_commit",
    "sha": "0000000000000000000000000000000000000000",
    "branch": "main",
}


def _mini_root(path: Path) -> Path:
    (path / "autolab").mkdir(parents=True)
    (path / "guard.py").write_text("GUARD = 1\n", encoding="utf-8")
    manifest = {
        "schema": fz.SCHEMA,
        "manifest_version": "fz-test-runner",
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": [fz.MANIFEST_RELPATH, "guard.py"],
    }
    (path / fz.MANIFEST_RELPATH).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fz.seal(path)
    return path


def _eval_plan(*, holdout: bool = False) -> dict:
    plan = {
        "suite": "public+holdout" if holdout else "public",
        "arms": ["candidate", "incumbent", "ancestor_anchor"],
        "seeds": [41, 42, 43],
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


def _declaration(*, holdout: bool = False) -> dict:
    return pre.build_declaration(
        declaration_id="runner-test",
        target_metric="score",
        direction="increase",
        min_delta=0.05,
        decision_rule="ci95_low_gt_0",
        comparator="incumbent",
        eval_plan=_eval_plan(holdout=holdout),
        protected_metrics=[
            {"name": "public_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "latency_ms", "direction": "no_increase", "tolerance": 5.0},
        ],
    )


def _budget(max_uses: int = 1) -> dict:
    return ctrl.build_holdout_budget(
        budget_id="frontier-delta-holdout:hd-v0.1.0",
        suite="frontier-delta-holdout",
        version="hd-v0.1.0",
        max_uses=max_uses,
    )


def _builder(_sealed_declaration: dict) -> dict:
    return {
        "patch_id": "runner-candidate",
        "files_changed": ["docs/example.md"],
    }


def _report(declaration: dict, _builder_result: dict, *, regression: bool = False) -> dict:
    return pre.build_report(
        declaration_hash=declaration["declaration_hash"],
        eval_plan=declaration["eval_plan"],
        primary={"metric": "score", "delta": 0.12, "ci95_low": 0.04, "ci95_high": 0.2},
        protected=[
            {"name": "public_pass_rate", "delta": -0.2 if regression else 0.0},
            {"name": "latency_ms", "delta": 2.0},
        ],
        builder_rationale="advisory",
    )


def _ratification_for(declaration: dict, report: dict, *, decision: str = "approve") -> dict:
    gate = pre.evaluate_gate(declaration, pre.seal_report(report))
    return rat.seal_ratification(rat.build_ratification(
        ratification_id=RATIFY_TOKEN,
        decision=decision,
        declaration_hash=gate.declaration_hash,
        report_hash=gate.report_hash,
        gate_decision_hash=rat.gate_decision_hash(gate),
        target_ref=TARGET_REF,
        human_reviewer="human-reviewer",
        rationale="Gate is green and target ref is approved.",
    ))


def _event_types(path: Path) -> list[str]:
    return [entry["event_type"] for entry in ctrl.read_meta_ledger(path)]


class RunnerFlowTests(unittest.TestCase):
    def test_successful_end_to_end_run_promotes_and_inscribes_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            declaration = _declaration()
            sealed = pre.seal_declaration(declaration)
            record = _ratification_for(sealed, _report(sealed, {}))

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-success",
                declaration=declaration,
                builder=_builder,
                evaluator=lambda decl, built: _report(decl, built),
                ratification_record=record,
                ratification_token=RATIFY_TOKEN,
                previous_ref=PREVIOUS_REF,
                inscription_rationale="Inscribing reviewed Item 7 target.",
            )

            self.assertEqual(result.status, runner.STATUS_PROMOTED, result.reasons)
            self.assertEqual(result.stage, runner.STAGE_LINEAGE)
            self.assertEqual(_event_types(ledger), [
                "zone_attested_pre",
                "declaration_sealed",
                "builder_invoked",
                "builder_completed",
                "zone_attested_post",
                "human_ratification",
                "promotion_inscribed",
            ])
            state = lin.derive_lineage_state(ledger)
            self.assertEqual(state.current_ref, TARGET_REF)
            self.assertEqual(result.lineage_state["current_ref"], TARGET_REF)
            self.assertIsNotNone(result.promotion_entry_hash)
            self.assertIsNotNone(result.inscription_entry_hash)

    def test_gate_red_appends_rejection_and_skips_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            declaration = _declaration()
            sealed = pre.seal_declaration(declaration)
            record = _ratification_for(sealed, _report(sealed, {}))

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-gate-red",
                declaration=declaration,
                builder=_builder,
                evaluator=lambda decl, built: _report(decl, built, regression=True),
                ratification_record=record,
                ratification_token=RATIFY_TOKEN,
                previous_ref=PREVIOUS_REF,
            )

            self.assertEqual(result.status, runner.STATUS_REJECTED)
            self.assertEqual(result.stage, runner.STAGE_GATE)
            self.assertEqual(_event_types(ledger)[-1], "gate_rejected")
            self.assertIsNone(lin.derive_lineage_state(ledger).current_ref)

    def test_missing_ratification_appends_human_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-no-human",
                declaration=_declaration(),
                builder=_builder,
                evaluator=lambda decl, built: _report(decl, built),
                ratification_record=None,
            )

            self.assertEqual(result.status, runner.STATUS_REJECTED)
            self.assertEqual(result.stage, runner.STAGE_HUMAN_RATIFICATION)
            self.assertEqual(_event_types(ledger)[-1], "human_ratification_rejected")
            self.assertTrue(any("missing" in reason for reason in result.reasons))

    def test_wrong_token_appends_human_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            declaration = _declaration()
            sealed = pre.seal_declaration(declaration)
            record = _ratification_for(sealed, _report(sealed, {}))

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-wrong-token",
                declaration=declaration,
                builder=_builder,
                evaluator=lambda decl, built: _report(decl, built),
                ratification_record=record,
                ratification_token="wrong-token",
                previous_ref=PREVIOUS_REF,
            )

            self.assertEqual(result.status, runner.STATUS_REJECTED)
            self.assertEqual(result.stage, runner.STAGE_HUMAN_RATIFICATION)
            self.assertEqual(_event_types(ledger)[-1], "human_ratification_rejected")

    def test_preflight_halt_prevents_builder_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            builder_called = False

            def should_not_run(_sealed_declaration: dict) -> dict:
                nonlocal builder_called
                builder_called = True
                return {}

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-preflight-halt",
                declaration=_declaration(),
                builder=should_not_run,
                evaluator=lambda decl, built: _report(decl, built),
                proposed_changed_paths=["guard.py"],
            )

            self.assertEqual(result.status, runner.STATUS_HALTED)
            self.assertEqual(result.stage, runner.STAGE_PREFLIGHT)
            self.assertFalse(builder_called)
            self.assertIsNotNone(cb.current_halt(ledger))
            self.assertEqual(_event_types(ledger), [cb.EVENT_HALTED])

    def test_active_halt_blocks_new_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            report = cb.evaluate_breakers(
                repo_root=root,
                ledger_path=ledger,
                proposed_changed_paths=["guard.py"],
            )
            cb.append_halt(ledger, run_id="halt", report=report)

            with self.assertRaisesRegex(runner.RunnerError, "active halt"):
                runner.run_autolab_iteration(
                    repo_root=root,
                    ledger_path=ledger,
                    run_id="blocked",
                    declaration=_declaration(),
                    builder=_builder,
                    evaluator=lambda decl, built: _report(decl, built),
                )

    def test_postflight_budget_exhaustion_halts_after_successful_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _mini_root(Path(tmp) / "repo")
            ledger = Path(tmp) / "meta.jsonl"
            declaration = _declaration(holdout=True)
            sealed = pre.seal_declaration(declaration)
            record = _ratification_for(sealed, _report(sealed, {}))

            result = runner.run_autolab_iteration(
                repo_root=root,
                ledger_path=ledger,
                run_id="runner-postflight-halt",
                declaration=declaration,
                builder=_builder,
                evaluator=lambda decl, built: _report(decl, built),
                ratification_record=record,
                ratification_token=RATIFY_TOKEN,
                holdout_budget=_budget(max_uses=1),
                previous_ref=PREVIOUS_REF,
            )

            self.assertEqual(result.status, runner.STATUS_HALTED)
            self.assertEqual(result.stage, runner.STAGE_POSTFLIGHT)
            self.assertIn(cb.REASON_HOLDOUT_BUDGET_EXHAUSTED, result.reasons)
            self.assertIn("promotion_inscribed", _event_types(ledger))
            self.assertIsNotNone(cb.current_halt(ledger))


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_runner_module_is_frozen(self):
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/runner.py", manifest["frozen_paths"])

    def test_amendment_record_documents_the_transition(self):
        manifest = fz.load_manifest(REPO_ROOT)
        amendments = {a.get("amendment_id"): a for a in fz.load_amendments(REPO_ROOT)}
        record = amendments.get("fz-v0.7.0-add-runner")
        self.assertIsNotNone(record, "fz-v0.7.0 amendment record missing")
        self.assertEqual(record["new_zone_hash"], manifest["zone_hash"])
        self.assertIn("autolab/runner.py", record["applies_to"])


if __name__ == "__main__":
    unittest.main()
