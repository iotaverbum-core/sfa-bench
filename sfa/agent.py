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
from . import verifier as verifier_mod
from .model_adapter import ModelAdapter


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

    def run(self, task: dict, evidence_pack: dict, model_adapter: ModelAdapter, run_id: str | None = None) -> AgentResult:
        """Run one task with at most one warning-guided retry.

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
            candidate = model_adapter.produce_candidate(task, evidence, warning=warning)
            _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "candidate")), candidate)

            verdict = verifier_mod.verify(task, evidence, candidate, rules)
            attempt_record = {
                "attempt": attempt_no,
                "status": verdict.status,
                "category": verdict.category,
                "verdict": verdict.to_dict(),
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
            observed_at = datetime.now(timezone.utc).isoformat()
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
            ledger_entry = self._append_occurrence(failure_artifact, verdict, family, observed_at, run_id)
            prior_entries = _prior_family_entries(self.ledger_path, family, exclude_entry_hash=ledger_entry["entry_hash"])

            attempt_record.update(
                {
                    "family": family,
                    "failure_artifact_path": artifact_path,
                    "artifact_hash": failure_artifact["artifact_hash"],
                    "ledger_entry_hash": ledger_entry["entry_hash"],
                }
            )
            _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "verdict")), attempt_record)
            attempts.append(attempt_record)

            if attempt_no == 1:
                warning = _warning_from_history(family, prior_entries, verdict)
                _write_json_new(os.path.join(run_dir, _attempt_name(attempt_no, "warning")), warning)
                continue
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

    def _append_occurrence(self, failure_artifact: dict, verdict, family: str, observed_at: str, run_id: str) -> dict:
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
        )


def _prior_family_entries(ledger_path: str, family: str, exclude_entry_hash: str | None = None) -> list[dict]:
    return [
        entry
        for entry in ledger_mod.read_ledger(ledger_path)
        if entry.get("family") == family and entry.get("entry_hash") != exclude_entry_hash
    ]


def _warning_from_history(family: str, prior_entries: list[dict], verdict) -> dict:
    recent = prior_entries[-3:]
    count = len(prior_entries)
    if count:
        message = (
            f"{count} prior occurrence(s) in family '{family}'. "
            "Retry by checking every claim value directly against the cited evidence."
        )
    else:
        message = (
            f"No prior occurrences in family '{family}'. "
            "Retry by checking every claim value directly against the cited evidence."
        )
    return {
        "family": family,
        "prior_occurrence_count": count,
        "recent_prior_occurrences": [
            {
                "case_id": entry.get("case_id"),
                "category": entry.get("category"),
                "period": entry.get("period"),
                "artifact_hash": entry.get("artifact_hash"),
            }
            for entry in recent
        ],
        "failed_explanation": verdict.explanation,
        "message": message,
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
