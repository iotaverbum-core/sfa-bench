"""Minimal SFA-Agent loop.

This is intentionally not a framework. It wraps a model adapter with the
existing deterministic SFA verifier, sealed failure artifacts, and the
append-only occurrence ledger.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import uuid

from . import artifact as artifact_mod
from . import families as fam_mod
from . import history as history_mod
from . import ledger as ledger_mod
from . import policy as policy_mod
from . import provenance as provenance_mod
from . import verifier as verifier_mod
from .model_adapter import CandidateOutput, ModelAdapter


@dataclass(frozen=True)
class AgentResult:
    run_id: str
    run_dir: str
    status: str
    attempts: list[dict]
    answer: dict | None


class SFAAgent:
    """Smallest useful SFA runtime loop."""

    def __init__(self, root_dir: str | None = None, run_root: str = "agent_runs"):
        self.root_dir = os.path.abspath(root_dir or os.getcwd())
        self.run_root = os.path.join(self.root_dir, run_root)
        self.ledger_path = os.path.join(self.root_dir, "history", "occurrences.jsonl")
        self.families_path = os.path.join(self.root_dir, "families.json")
        self.config_path = os.path.join(self.root_dir, "history_config.json")

    def run(
        self,
        task: dict,
        evidence_pack: dict,
        model_adapter: ModelAdapter,
        run_id: str | None = None,
        retry_adapter: ModelAdapter | None = None,
    ) -> AgentResult:
        """Run one task with at most one deterministic policy-guided retry.

        `evidence_pack` must contain `evidence` and `verifier_rules`. No gold
        verdict is accepted or loaded by this method.
        """
        evidence = evidence_pack["evidence"]
        rules = evidence_pack["verifier_rules"]
        case_id = task.get("case_id", "agent_task")
        run_id = run_id or _new_run_id()
        run_dir = os.path.join(self.run_root, run_id)
        os.makedirs(self.run_root, exist_ok=True)
        os.makedirs(run_dir, exist_ok=False)

        attempts = []
        warning = None
        for attempt_no in (1, 2):
            adapter = retry_adapter if attempt_no == 2 and retry_adapter is not None else model_adapter
            adapter_output = _coerce_adapter_output(adapter.produce_candidate(task, evidence, warning=warning), adapter)
            candidate = adapter_output.candidate
            raw_source_path = None
            if adapter_output.raw_source is not None:
                raw_source_path = os.path.join(run_dir, _attempt_name(attempt_no, "raw_source"))
                _write_json_new(raw_source_path, adapter_output.raw_source)
            _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "candidate")), candidate)

            created_at = datetime.now(timezone.utc).isoformat()
            provenance = provenance_mod.build_provenance(
                adapter_output,
                task,
                evidence,
                warning_used=warning is not None,
                created_at=created_at,
            )
            provenance_path = os.path.join(run_dir, _attempt_name(attempt_no, "provenance"))
            _write_json_new(provenance_path, provenance)

            verdict = verifier_mod.verify(task, evidence, candidate, rules)
            attempt_record = {
                "attempt": attempt_no,
                "status": verdict.status,
                "category": verdict.category,
                "verdict": verdict.to_dict(),
                "provenance_path": provenance_path,
                "raw_source_path": raw_source_path,
                "source_hash": provenance["source_hash"],
                "normalized_candidate_hash": provenance["normalized_candidate_hash"],
                "model_id": provenance["model_id"],
            }

            if verdict.status == "PASS":
                _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "verdict")), attempt_record)
                attempts.append(attempt_record)
                summary = {
                    "run_id": run_id,
                    "case_id": case_id,
                    "status": "PASS",
                    "returned_attempt": attempt_no,
                    "attempts": attempts,
                }
                _write_json_new(os.path.join(run_dir, "summary.json"), summary)
                return AgentResult(run_id, run_dir, "PASS", attempts, candidate)

            family = fam_mod.classify_family(verdict.category, candidate, evidence)
            observed_at = created_at
            failure_artifact = artifact_mod.seal_failure(
                case_id,
                task,
                evidence,
                candidate,
                verifier_mod.VERIFIER_VERSION,
                verdict.category,
                family,
                verdict.explanation,
                sealed_at=observed_at,
            )
            artifact_path = os.path.join(run_dir, f"attempt_{attempt_no:03d}_failure_artifact.json")
            _write_json_new(artifact_path, failure_artifact)
            ledger_entry = self._append_occurrence(
                failure_artifact,
                verdict,
                family,
                observed_at,
                run_id,
                provenance["model_id"],
            )
            attempt_record.update(
                {
                    "family": family,
                    "failure_artifact_path": artifact_path,
                    "artifact_hash": failure_artifact["artifact_hash"],
                    "ledger_entry_hash": ledger_entry["entry_hash"],
                }
            )
            if attempt_no == 1:
                policy_input = _policy_input_from_ledger(
                    self.ledger_path,
                    model_id=provenance["model_id"],
                    current_failure_family=family,
                )
                decision = policy_mod.decide_policy(policy_input)
                policy_input_path = os.path.join(run_dir, _attempt_name(attempt_no, "policy_input"))
                policy_decision_path = os.path.join(run_dir, _attempt_name(attempt_no, "policy_decision"))
                _write_json_new(policy_input_path, policy_input)
                _write_json_new(policy_decision_path, decision)
                warning = _warning_from_policy(decision, verdict)
                _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "warning")), warning)
                attempt_record.update(
                    {
                        "policy_input_path": policy_input_path,
                        "policy_decision_path": policy_decision_path,
                        "policy_decision_hash": decision["decision_hash"],
                        "policy_escalation_level": decision["escalation_level"],
                        "policy_generator_side_only": True,
                    }
                )
                _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "verdict")), attempt_record)
                attempts.append(attempt_record)
                if decision["directives"] and not decision["termination_recommended"]:
                    continue
                break
            _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "verdict")), attempt_record)
            attempts.append(attempt_record)
            break

        summary = {
            "run_id": run_id,
            "case_id": case_id,
            "status": attempts[-1]["status"] if attempts else "FAIL",
            "returned_attempt": None,
            "attempts": attempts,
        }
        _write_json_new(os.path.join(run_dir, "summary.json"), summary)
        return AgentResult(run_id, run_dir, summary["status"], attempts, None)

    def _append_occurrence(self, failure_artifact: dict, verdict, family: str, observed_at: str, run_id: str, model_id: str) -> dict:
        with open(self.config_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        granularity = config.get("period_granularity", "year")
        return ledger_mod.append_occurrence(
            self.ledger_path,
            artifact_hash=failure_artifact["artifact_hash"],
            case_id=failure_artifact["case_id"],
            category=verdict.category,
            family=family,
            observed_at=observed_at,
            period=history_mod.period_of(observed_at, granularity),
            run_id=run_id,
            synthetic=False,
            model_id=model_id,
        )


def _coerce_adapter_output(output, adapter) -> CandidateOutput:
    if isinstance(output, CandidateOutput):
        return output
    return CandidateOutput(
        candidate=output,
        raw_source=output,
        adapter_name=getattr(adapter, "adapter_name", adapter.__class__.__name__),
        adapter_kind=getattr(adapter, "adapter_kind", "legacy_adapter"),
        adapter_version=getattr(adapter, "adapter_version", "unknown"),
        source_type=getattr(adapter, "source_type", "legacy_dict"),
        source_path=getattr(adapter, "source_path", None),
    )


def _policy_input_from_ledger(
    ledger_path: str, *, model_id: str, current_failure_family: str
) -> dict:
    entries = [
        entry
        for entry in ledger_mod.read_ledger(ledger_path)
        if entry.get("model_id", "unknown") == model_id
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        family = entry.get("family")
        if family:
            counts[family] = counts.get(family, 0) + 1
    total = len(entries)
    profile = {
        "scope": f"model_id:{model_id}",
        "total_failures": total,
        "families": {
            family: {
                "count": count,
                "rate": round(count / total, 6) if total else 0.0,
            }
            for family, count in sorted(counts.items())
        },
    }
    return policy_mod.make_policy_input(
        model_id=model_id,
        recurrence_profile=profile,
        current_failure_family=current_failure_family,
        retry_attempt_number=1,
        prior_remediation_history=[],
    )


def _warning_from_policy(decision: dict, verdict) -> dict:
    return {
        "policy_version": decision["policy_version"],
        "policy_decision_hash": decision["decision_hash"],
        "triggered_families": decision["triggered_families"],
        "directives": decision["directives"],
        "escalation_level": decision["escalation_level"],
        "termination_recommended": decision["termination_recommended"],
        "directive_target": decision["directive_target"],
        "failed_explanation": verdict.explanation,
        "message": decision["generated_caution"],
        "verifier_received_policy_metadata": False,
    }


def _attempt_name(attempt_no: int, kind: str) -> str:
    return f"attempt_{attempt_no:03d}_{kind}.json"


def _write_json_new(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "x", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"agent-{stamp}-{uuid.uuid4().hex[:8]}"
