"""End-to-end AutoLab runner (Item 7).

FROZEN ZONE - this module is loop orchestration policy and is listed in
``autolab/frozen_manifest.json``. The AutoLab loop may not patch it; changes
flow only through the human-only amendment channel.

Items 1-6 define the primitives: frozen-zone attestation, pre-registration,
controller ordering, human ratification, promotion lineage, and circuit
breakers. Item 7 wires those primitives into one deterministic sequence so a
caller cannot accidentally skip the halt check, gate rejection record, human
approval layer, or lineage inscription.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from autolab import circuit_breakers
from autolab import controller
from autolab import lineage
from autolab import preregistration
from autolab import ratification

RUNNER_SCHEMA = "sfa.autolab.runner_result.v0"
REJECTION_SCHEMA = "sfa.autolab.runner_rejection.v0"

STATUS_HALTED = "halted"
STATUS_REJECTED = "rejected"
STATUS_PROMOTED = "promoted"

STAGE_PREFLIGHT = "preflight_breakers"
STAGE_CONTROLLER = "controller"
STAGE_GATE = "gate"
STAGE_HUMAN_RATIFICATION = "human_ratification"
STAGE_PROMOTION = "promotion"
STAGE_LINEAGE = "lineage"
STAGE_POSTFLIGHT = "postflight_breakers"


class RunnerError(RuntimeError):
    """Raised when the end-to-end runner cannot safely start or continue."""


@dataclass
class RunnerResult:
    run_id: str
    status: str
    stage: str
    reasons: list[str]
    ledger_root: str
    controller_run: Optional[controller.ControllerRun] = None
    builder_result_hash: Optional[str] = None
    report: Optional[dict[str, Any]] = None
    gate_decision: Optional[dict[str, Any]] = None
    promotion_decision: Optional[dict[str, Any]] = None
    rejection_entry_hash: Optional[str] = None
    promotion_entry_hash: Optional[str] = None
    inscription_entry_hash: Optional[str] = None
    halt_entry_hash: Optional[str] = None
    breaker_report: Optional[dict[str, Any]] = None
    lineage_state: Optional[dict[str, Any]] = None
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNNER_SCHEMA,
            "run_id": self.run_id,
            "status": self.status,
            "stage": self.stage,
            "reasons": list(self.reasons),
            "ledger_root": self.ledger_root,
            "controller_run": (
                self.controller_run.to_dict() if self.controller_run is not None else None
            ),
            "builder_result_hash": self.builder_result_hash,
            "report_hash": self.report.get(preregistration.REPORT_HASH_KEY)
            if self.report is not None else None,
            "gate_decision": dict(self.gate_decision) if self.gate_decision is not None else None,
            "promotion_decision": (
                dict(self.promotion_decision) if self.promotion_decision is not None else None
            ),
            "rejection_entry_hash": self.rejection_entry_hash,
            "promotion_entry_hash": self.promotion_entry_hash,
            "inscription_entry_hash": self.inscription_entry_hash,
            "halt_entry_hash": self.halt_entry_hash,
            "breaker_report": (
                dict(self.breaker_report) if self.breaker_report is not None else None
            ),
            "lineage_state": (
                dict(self.lineage_state) if self.lineage_state is not None else None
            ),
            "checks": dict(self.checks),
        }


Builder = Callable[[dict[str, Any]], Any]
Evaluator = Callable[[dict[str, Any], Any], dict[str, Any]]


def _entry_hash(entry: dict[str, Any]) -> str:
    return str(entry[controller.ENTRY_HASH_KEY])


def _ledger_root(path: str | Path) -> str:
    return controller.meta_ledger_root(path)


def _candidate_lineage_id(
    proposed_lineage_id: Optional[str],
    builder_result: Any = None,
) -> Optional[str]:
    if proposed_lineage_id:
        return str(proposed_lineage_id)
    if isinstance(builder_result, dict):
        for key in ("lineage_id", "patch_fingerprint", "patch_id", "candidate_id"):
            value = builder_result.get(key)
            if value:
                return str(value)
    return None


def _changed_paths_from_builder_result(builder_result: Any) -> list[str]:
    if not isinstance(builder_result, dict):
        return []
    raw = builder_result.get("files_changed") or builder_result.get("changed_paths") or []
    if not isinstance(raw, list):
        return []
    return [str(path).replace("\\", "/") for path in raw]


def append_rejection(
    ledger_path: str | Path,
    *,
    run_id: str,
    event_type: str,
    stage: str,
    reasons: list[str],
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if event_type not in circuit_breakers.REJECTION_EVENTS:
        raise RunnerError(f"event_type must be one of {circuit_breakers.REJECTION_EVENTS}")
    record = {
        "schema": REJECTION_SCHEMA,
        "stage": str(stage),
        "reasons": list(reasons),
    }
    if payload:
        record.update(dict(payload))
    return controller.append_meta_event(
        ledger_path,
        event_type=event_type,
        run_id=run_id,
        payload=record,
    )


def _halt_result(
    *,
    ledger_path: str | Path,
    run_id: str,
    stage: str,
    report: circuit_breakers.BreakerReport,
    controller_run: Optional[controller.ControllerRun] = None,
    report_record: Optional[dict[str, Any]] = None,
    gate_decision: Optional[dict[str, Any]] = None,
    promotion_decision: Optional[dict[str, Any]] = None,
    promotion_entry_hash: Optional[str] = None,
    inscription_entry_hash: Optional[str] = None,
) -> RunnerResult:
    halt = circuit_breakers.append_halt(ledger_path, run_id=run_id, report=report)
    state = lineage.derive_lineage_state(ledger_path).to_dict()
    return RunnerResult(
        run_id=run_id,
        status=STATUS_HALTED,
        stage=stage,
        reasons=list(report.reasons),
        ledger_root=_ledger_root(ledger_path),
        controller_run=controller_run,
        builder_result_hash=(
            controller_run.builder_result_hash if controller_run is not None else None
        ),
        report=report_record,
        gate_decision=gate_decision,
        promotion_decision=promotion_decision,
        promotion_entry_hash=promotion_entry_hash,
        inscription_entry_hash=inscription_entry_hash,
        halt_entry_hash=_entry_hash(halt),
        breaker_report=report.to_dict(),
        lineage_state=state,
    )


def run_autolab_iteration(
    *,
    repo_root: str | Path,
    ledger_path: str | Path,
    run_id: str,
    declaration: dict[str, Any],
    builder: Builder,
    evaluator: Evaluator,
    ratification_record: Optional[dict[str, Any]] = None,
    ratification_token: Optional[str] = None,
    holdout_budget: Optional[dict[str, Any]] = None,
    previous_ref: Optional[dict[str, Any]] = None,
    inscription_rationale: str = "",
    proposed_changed_paths: Optional[list[str]] = None,
    proposed_lineage_id: Optional[str] = None,
    max_consecutive_rejections: int = circuit_breakers.DEFAULT_MAX_CONSECUTIVE_REJECTIONS,
    wither_threshold: int = circuit_breakers.DEFAULT_WITHER_THRESHOLD,
    cost_spent: float = 0.0,
    max_cost: Optional[float] = None,
    seconds_spent: float = 0.0,
    max_seconds: Optional[float] = None,
) -> RunnerResult:
    """Run one complete AutoLab proposal, gate, ratification, and lineage pass.

    The builder cannot run while a halt is active. Breakers are evaluated before
    the builder and again after lineage inscription. Gate and human-promotion
    failures are appended as rejection events so Item 6 can count them.
    """
    if circuit_breakers.current_halt(ledger_path) is not None:
        raise RunnerError("active halt requires restart clearance before a new AutoLab iteration")

    lineage_id = _candidate_lineage_id(proposed_lineage_id)
    preflight = circuit_breakers.evaluate_breakers(
        repo_root=repo_root,
        ledger_path=ledger_path,
        proposed_changed_paths=proposed_changed_paths,
        proposed_lineage_id=lineage_id,
        max_consecutive_rejections=max_consecutive_rejections,
        wither_threshold=wither_threshold,
        cost_spent=cost_spent,
        max_cost=max_cost,
        seconds_spent=seconds_spent,
        max_seconds=max_seconds,
    )
    if preflight.halted:
        return _halt_result(
            ledger_path=ledger_path,
            run_id=run_id,
            stage=STAGE_PREFLIGHT,
            report=preflight,
        )

    captured: dict[str, Any] = {}

    def controlled_builder(sealed_declaration: dict[str, Any]) -> Any:
        result = builder(sealed_declaration)
        captured["builder_result"] = result
        return result

    try:
        run = controller.run_iteration(
            repo_root=repo_root,
            ledger_path=ledger_path,
            run_id=run_id,
            declaration=declaration,
            builder=controlled_builder,
            holdout_budget=holdout_budget,
        )
    except controller.ControllerError as exc:
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="autolab_rejected",
            stage=STAGE_CONTROLLER,
            reasons=[str(exc)],
            payload={"controller_error": str(exc), "lineage_id": lineage_id},
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_CONTROLLER,
            reasons=[str(exc)],
            ledger_root=_ledger_root(ledger_path),
            rejection_entry_hash=_entry_hash(entry),
        )

    builder_result = captured.get("builder_result")
    if lineage_id is None:
        lineage_id = _candidate_lineage_id(None, builder_result)

    report = preregistration.seal_report(evaluator(run.declaration, builder_result))
    gate = preregistration.evaluate_gate(run.declaration, report)
    gate_record = gate.to_dict()
    if not gate.gate_green:
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="gate_rejected",
            stage=STAGE_GATE,
            reasons=list(gate.reasons),
            payload={
                "lineage_id": lineage_id,
                "gate_green": False,
                "gate_decision": gate_record,
                "declaration_hash": gate.declaration_hash,
                "report_hash": gate.report_hash,
            },
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_GATE,
            reasons=list(gate.reasons),
            ledger_root=_ledger_root(ledger_path),
            controller_run=run,
            builder_result_hash=run.builder_result_hash,
            report=report,
            gate_decision=gate_record,
            rejection_entry_hash=_entry_hash(entry),
        )

    if ratification_record is None:
        reasons = ["human ratification record missing"]
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="human_ratification_rejected",
            stage=STAGE_HUMAN_RATIFICATION,
            reasons=reasons,
            payload={
                "lineage_id": lineage_id,
                "gate_green": True,
                "gate_decision": gate_record,
                "declaration_hash": gate.declaration_hash,
                "report_hash": gate.report_hash,
            },
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_HUMAN_RATIFICATION,
            reasons=reasons,
            ledger_root=_ledger_root(ledger_path),
            controller_run=run,
            builder_result_hash=run.builder_result_hash,
            report=report,
            gate_decision=gate_record,
            rejection_entry_hash=_entry_hash(entry),
        )

    try:
        promotion = ratification.evaluate_promotion(
            run.declaration,
            report,
            ratification_record,
            ratification_token=ratification_token,
        )
    except ratification.RatificationError as exc:
        reasons = [str(exc)]
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="promotion_rejected",
            stage=STAGE_PROMOTION,
            reasons=reasons,
            payload={
                "lineage_id": lineage_id,
                "gate_green": True,
                "gate_decision": gate_record,
                "declaration_hash": gate.declaration_hash,
                "report_hash": gate.report_hash,
            },
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_PROMOTION,
            reasons=reasons,
            ledger_root=_ledger_root(ledger_path),
            controller_run=run,
            builder_result_hash=run.builder_result_hash,
            report=report,
            gate_decision=gate_record,
            rejection_entry_hash=_entry_hash(entry),
        )

    promotion_record = promotion.to_dict()
    if not promotion.promoted:
        token_or_decision_failed = (
            not promotion.checks.get("human_token")
            or not promotion.checks.get("human_decision_approve")
        )
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="human_ratification_rejected" if token_or_decision_failed else "promotion_rejected",
            stage=STAGE_HUMAN_RATIFICATION if token_or_decision_failed else STAGE_PROMOTION,
            reasons=list(promotion.reasons),
            payload={
                "lineage_id": lineage_id,
                "gate_green": True,
                "gate_decision": gate_record,
                "promotion_decision": promotion_record,
                "declaration_hash": gate.declaration_hash,
                "report_hash": gate.report_hash,
            },
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_HUMAN_RATIFICATION if token_or_decision_failed else STAGE_PROMOTION,
            reasons=list(promotion.reasons),
            ledger_root=_ledger_root(ledger_path),
            controller_run=run,
            builder_result_hash=run.builder_result_hash,
            report=report,
            gate_decision=gate_record,
            promotion_decision=promotion_record,
            rejection_entry_hash=_entry_hash(entry),
        )

    promotion_entry = ratification.append_promotion(
        ledger_path,
        run_id=run_id,
        declaration=run.declaration,
        report=report,
        ratification=ratification_record,
        ratification_token=ratification_token,
    )
    try:
        inscription = lineage.append_promotion_inscription(
            ledger_path,
            run_id=run_id,
            promotion_entry_hash=_entry_hash(promotion_entry),
            previous_ref=previous_ref,
            rationale=inscription_rationale,
        )
    except lineage.LineageError as exc:
        entry = append_rejection(
            ledger_path,
            run_id=run_id,
            event_type="autolab_rejected",
            stage=STAGE_LINEAGE,
            reasons=[str(exc)],
            payload={
                "lineage_id": lineage_id,
                "promotion_decision": promotion_record,
                "promotion_entry_hash": _entry_hash(promotion_entry),
            },
        )
        return RunnerResult(
            run_id=run_id,
            status=STATUS_REJECTED,
            stage=STAGE_LINEAGE,
            reasons=[str(exc)],
            ledger_root=_ledger_root(ledger_path),
            controller_run=run,
            builder_result_hash=run.builder_result_hash,
            report=report,
            gate_decision=gate_record,
            promotion_decision=promotion_record,
            promotion_entry_hash=_entry_hash(promotion_entry),
            rejection_entry_hash=_entry_hash(entry),
        )

    changed_paths = _changed_paths_from_builder_result(builder_result)
    postflight = circuit_breakers.evaluate_breakers(
        repo_root=repo_root,
        ledger_path=ledger_path,
        proposed_changed_paths=changed_paths,
        proposed_lineage_id=lineage_id,
        max_consecutive_rejections=max_consecutive_rejections,
        wither_threshold=wither_threshold,
        cost_spent=cost_spent,
        max_cost=max_cost,
        seconds_spent=seconds_spent,
        max_seconds=max_seconds,
    )
    if postflight.halted:
        return _halt_result(
            ledger_path=ledger_path,
            run_id=run_id,
            stage=STAGE_POSTFLIGHT,
            report=postflight,
            controller_run=run,
            report_record=report,
            gate_decision=gate_record,
            promotion_decision=promotion_record,
            promotion_entry_hash=_entry_hash(promotion_entry),
            inscription_entry_hash=_entry_hash(inscription),
        )

    state = lineage.derive_lineage_state(ledger_path).to_dict()
    return RunnerResult(
        run_id=run_id,
        status=STATUS_PROMOTED,
        stage=STAGE_LINEAGE,
        reasons=[],
        ledger_root=_ledger_root(ledger_path),
        controller_run=run,
        builder_result_hash=run.builder_result_hash,
        report=report,
        gate_decision=gate_record,
        promotion_decision=promotion_record,
        promotion_entry_hash=_entry_hash(promotion_entry),
        inscription_entry_hash=_entry_hash(inscription),
        breaker_report=postflight.to_dict(),
        lineage_state=state,
    )
