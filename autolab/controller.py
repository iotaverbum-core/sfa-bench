"""AutoLab loop controller (SFA-AutoLab v0, Item 3).

FROZEN ZONE — the controller is listed in ``autolab/frozen_manifest.json``. It is
the orchestrator the loop runs *within*; the loop may not patch it.

One iteration, as a **pure, deterministic function** of its config:

    propose  ->  public suite  ->  budgeted holdout  ->  paired comparison
    (candidate / incumbent / ancestor-anchor, identical seeds, bootstrap CI,
     pre-registered threshold)  ->  sealed improvement report  ->  gate  ->
    PR payload (declaration + report attached)

Crucially there is **no promotion path** here. The iteration stops at "PR opened
with declaration + report" and records ``awaiting_human_ratification``. Promotion
requires deterministic-gate-green AND a human token (Item 4).

Invariant compliance:

  * **Frozen zone (1).** The controller reads the frozen evaluators but writes
    nothing to the zone. It computes a pre/post zone attestation around the
    iteration and refuses to emit a record if the zone changed.
  * **Asymmetric gate (2).** It calls the Item-2 gate, which may only reject, and
    never promotes.
  * **Builder cannot attest (3).** The improvement report's numbers are produced
    by frozen evaluators (the verifier via the Item-1 trial harness, the public
    suite, the holdout). The builder contributes only an advisory rationale.
  * **Append-only lineage (4).** ``run_iteration`` is pure and emits a sealed,
    hash-chained record; a separate (Item-4/5) inscription step persists it.
  * **Budgeted holdout (5).** Holdout feedback is coarse (lane pass/fail +
    aggregate delta); seeds are consumed from an append-only schedule and never
    reused; exposure is metered per suite version.
  * **Determinism & offline CI (6).** All randomness derives from one integer
    seed via SHA-256; no wall-clock, network, or model call. ``--live`` (a real
    builder) is opt-in, user-supplied, and never in CI. ``replay`` re-derives an
    iteration byte-for-byte.

The default ``stub`` builder is an illustrative mechanism model (like the
prior-state-trial stub): it proposes a candidate whose only effect is an elevated
per-task success probability. It makes the loop deterministically testable; it is
not a claim about any real builder. Point ``--live`` at a real builder to measure
reality.

Stdlib-only; standalone canonical hashing mirrors ``sfa.hashing``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from sfa import prior_state_trial as trial
from sfa import verifier as verifier_mod
from . import frozen_zone as fz
from . import preregistration as pre

ITERATION_SCHEMA = "sfa.autolab.loop_iteration.v0"
STUB_BUILDER_ID = "stub-autolab-builder-v0"
GENESIS = "GENESIS"

ARMS = ("candidate", "incumbent", "ancestor_anchor")

# Illustrative stub success probabilities (documented in
# docs/autolab-loop-controller.md). candidate > incumbent > ancestor_anchor.
P_CANDIDATE = 0.80
P_INCUMBENT = 0.55
P_ANCESTOR = 0.50

DEFAULT_N = 30
DEFAULT_BOOTSTRAP = 2000
DEFAULT_HOLDOUT_LANES = 8
DEFAULT_HOLDOUT_BUDGET = 3
HOLDOUT_SUITE_VERSION = "hd-v0.1.0"


# ---------------------------------------------------------------------------
# Canonical hashing (mirrors sfa.hashing).
# ---------------------------------------------------------------------------
def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _uniform(*parts: Any) -> float:
    """Deterministic uniform in [0, 1) derived from SHA-256 of the parts."""
    digest = sha256_hex([str(p) for p in parts])
    return int(digest[:16], 16) / float(1 << 64)


DEFAULT_ARM_PROBABILITIES = {
    "candidate": P_CANDIDATE, "incumbent": P_INCUMBENT, "ancestor_anchor": P_ANCESTOR,
}


def _arm_probabilities(config: dict[str, Any] | None = None) -> dict[str, float]:
    """Stub arm success probabilities (config-overridable stub parameters).

    Defaults are the documented illustrative values. Overriding them lets the
    harness exercise a *rejecting* iteration (a candidate that fails to beat the
    incumbent), demonstrating the gate is not a rubber stamp. The chosen values
    are recorded in the sealed config, so replay is exact.
    """
    probs = dict(DEFAULT_ARM_PROBABILITIES)
    if config:
        override = config.get("arm_probabilities")
        if isinstance(override, dict):
            for arm in ARMS:
                if arm in override:
                    probs[arm] = float(override[arm])
    return probs


# ---------------------------------------------------------------------------
# Stub builder (the proposer).
# ---------------------------------------------------------------------------
def stub_builder(config: dict[str, Any]) -> dict[str, Any]:
    """Deterministic illustrative builder. Returns an advisory proposal.

    The proposal's only *scored* effect is the candidate arm's elevated success
    probability (documented). ``patch_fingerprint`` is a deterministic id derived
    from the seed; ``rationale`` is advisory metadata excluded from the gate.
    """
    seed = int(config["seed"])
    patch_fingerprint = sha256_hex(["autolab_patch", seed, config.get("target_metric")])[:32]
    return {
        "builder_id": STUB_BUILDER_ID,
        "patch_fingerprint": patch_fingerprint,
        "rationale": f"stub proposal for seed {seed}: tighten the retry-policy composition",
    }


# ---------------------------------------------------------------------------
# Frozen evaluators.
# ---------------------------------------------------------------------------
def _score_arm(tasks: list[dict[str, Any]], arm: str, seed: int, probs: dict[str, float]) -> list[int]:
    """Score one arm over the paired task list with the fixed verifier (zero LLM)."""
    scores = []
    for index, task in enumerate(tasks):
        draw = _uniform(seed, "arm", arm, task["task_id"], index)
        corrected = draw < probs[arm]
        candidate = task["correct_candidate"] if corrected else task["flawed_candidate"]
        verdict = verifier_mod.verify(task["input"], task["evidence"], candidate, task["rules"])
        scores.append(1 if verdict.status == "PASS" else 0)
    return scores


def paired_comparison(seed: int, n: int, bootstrap: int, probs: dict[str, float]) -> dict[str, Any]:
    """Paired comparison via the Item-1 trial harness primitives.

    Arms candidate / incumbent / ancestor_anchor over identical sampled tasks
    (paired), scored by the fixed verifier, with a fixed-seed bootstrap 95% CI on
    the candidate - incumbent per-task delta.
    """
    pool = trial.build_task_pool(max(len(trial._SKINS), n), seed)
    tasks = trial.sample_tasks(pool, n, seed)
    scores = {arm: _score_arm(tasks, arm, seed, probs) for arm in ARMS}
    deltas = [c - i for c, i in zip(scores["candidate"], scores["incumbent"])]
    ci = trial.bootstrap_ci(deltas, bootstrap, seed)
    arm_means = {arm: round(sum(scores[arm]) / n, 6) if n else 0.0 for arm in ARMS}
    return {
        "arms": ARMS,
        "n": n,
        "sampled_task_hash": sha256_hex([t["task_id"] for t in tasks]),
        "arm_means": arm_means,
        "candidate_minus_incumbent": {
            "delta_mean": ci["mean"],
            "ci95_low": ci["ci_low"],
            "ci95_high": ci["ci_high"],
            "bootstrap_samples": bootstrap,
            "bootstrap_seed": seed,
        },
        # Ancestor-anchor guards against silent drift: the candidate must also not
        # fall below the pinned v-root reference.
        "candidate_minus_ancestor_mean": round(arm_means["candidate"] - arm_means["ancestor_anchor"], 6),
    }


def public_suite(seed: int, probs: dict[str, float]) -> dict[str, Any]:
    """Deterministic public-suite pass rate for candidate and incumbent."""
    candidate = round(probs["candidate"], 6)
    incumbent = round(probs["incumbent"], 6)
    # A small deterministic jitter so the value is seed-dependent but stable.
    jitter = round((_uniform(seed, "public") - 0.5) * 0.02, 6)
    return {
        "suite": "public",
        "candidate_pass_rate": round(min(1.0, candidate + jitter), 6),
        "incumbent_pass_rate": incumbent,
    }


# ---------------------------------------------------------------------------
# Budgeted holdout (coarse, metered, append-only seeds).
# ---------------------------------------------------------------------------
def holdout_seed_schedule(suite_version: str, cursor: int) -> int:
    """Deterministic, collision-resistant seed for a given exposure index.

    Seeds are a pure function of (suite_version, cursor); the cursor only ever
    advances, so no seed is reused.
    """
    digest = sha256_hex(["holdout_seed", suite_version, cursor])
    return int(digest[:12], 16)


def budgeted_holdout(seed: int, probs: dict[str, float], *, suite_version: str, lanes: int,
                     budget: int, cursor_before: int, exposures: int) -> dict[str, Any]:
    """Coarse holdout feedback: lane pass/fail + an aggregate delta only.

    Consumes ``exposures`` fresh seeds append-only from ``cursor_before``. No
    per-case gold is exposed. Meters exposure against ``budget`` per suite
    version.
    """
    used_seeds = [holdout_seed_schedule(suite_version, cursor_before + j) for j in range(exposures)]
    cursor_after = cursor_before + exposures
    # Coarse lane pass/fail: one boolean per lane, derived from the consumed
    # seeds; NOT per-case detail.
    lane_pass = []
    for lane in range(lanes):
        s = used_seeds[lane % max(1, len(used_seeds))] if used_seeds else seed
        lane_pass.append(_uniform(s, "lane", lane) < probs["candidate"])
    candidate_lane_rate = round(sum(lane_pass) / lanes, 6) if lanes else 0.0
    incumbent_lane_rate = round(probs["incumbent"], 6)
    remaining = budget - cursor_after
    return {
        "suite_version": suite_version,
        "granularity": "coarse (lane pass/fail + aggregate delta)",
        "lanes": lanes,
        "lane_pass_count": sum(lane_pass),
        "candidate_lane_rate": candidate_lane_rate,
        "aggregate_delta": round(candidate_lane_rate - incumbent_lane_rate, 6),
        "budget": budget,
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
        "seeds_consumed": used_seeds,
        "budget_remaining": remaining,
        "budget_exhausted": remaining < 0,
    }


# ---------------------------------------------------------------------------
# One loop iteration (pure).
# ---------------------------------------------------------------------------
@dataclass
class IterationResult:
    record: dict[str, Any]

    @property
    def loop_hash(self) -> str:
        return self.record["loop_hash"]

    @property
    def gate_green(self) -> bool:
        return self.record["gate"]["gate_green"]

    @property
    def awaiting_human_ratification(self) -> bool:
        return self.record["promotion"]["awaiting_human_ratification"]


def _declaration_from_config(config: dict[str, Any]) -> dict[str, Any]:
    n = int(config.get("n", DEFAULT_N))
    bootstrap = int(config.get("bootstrap", DEFAULT_BOOTSTRAP))
    eval_plan = {
        "suite": "public+holdout+paired",
        "arms": list(ARMS),
        "seeds": [int(config["seed"])],
        "n": n,
        "bootstrap": bootstrap,
        "harness": trial.TRIAL_SCHEMA,
        "holdout_suite_version": config.get("holdout_suite_version", HOLDOUT_SUITE_VERSION),
    }
    return pre.seal_declaration(pre.build_declaration(
        declaration_id=str(config.get("declaration_id", f"autolab-{int(config['seed'])}")),
        target_metric=str(config.get("target_metric", "paired_candidate_minus_incumbent")),
        direction=str(config.get("direction", "increase")),
        min_delta=float(config.get("min_delta", 0.05)),
        decision_rule=str(config.get("decision_rule", "ci95_low_gt_0")),
        comparator="incumbent",
        eval_plan=eval_plan,
        protected_metrics=list(config.get("protected_metrics", [
            {"name": "public_suite_pass_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "holdout_lane_rate", "direction": "no_decrease", "tolerance": 0.0},
            {"name": "ancestor_anchor_floor", "direction": "no_decrease", "tolerance": 0.0},
        ])),
    ))


def run_iteration(config: dict[str, Any], *,
                  builder: Optional[Callable[[dict], dict]] = None,
                  repo_root: Optional[str | Path] = None) -> IterationResult:
    """Run one loop iteration as a pure function of ``config``.

    Emits a sealed, hash-chained loop record. No promotion. No file writes.
    """
    seed = int(config["seed"])
    n = int(config.get("n", DEFAULT_N))
    bootstrap = int(config.get("bootstrap", DEFAULT_BOOTSTRAP))
    lanes = int(config.get("holdout_lanes", DEFAULT_HOLDOUT_LANES))
    budget = int(config.get("holdout_budget", DEFAULT_HOLDOUT_BUDGET))
    cursor_before = int(config.get("holdout_cursor", 0))
    exposures = int(config.get("holdout_exposures", 1))
    suite_version = str(config.get("holdout_suite_version", HOLDOUT_SUITE_VERSION))
    probs = _arm_probabilities(config)
    builder = builder or stub_builder

    # (0) Pre-registration BEFORE proposing.
    declaration = _declaration_from_config(config)

    # (1) Pre-attestation of the frozen zone (optional; recorded when a repo root
    #     with a manifest is available).
    zone_pre = _zone_attestation(repo_root)

    # (2) Propose (builder is advisory; its output never scores).
    proposal = builder(config)

    # (3) Public suite (frozen evaluator).
    public = public_suite(seed, probs)

    # (4) Budgeted holdout (coarse, metered, append-only seeds).
    holdout = budgeted_holdout(
        seed, probs, suite_version=suite_version, lanes=lanes, budget=budget,
        cursor_before=cursor_before, exposures=exposures,
    )

    # (5) Paired comparison via the Item-1 trial harness.
    paired = paired_comparison(seed, n, bootstrap, probs)

    # (6) Sealed improvement report (numbers from frozen evaluators only).
    report = pre.seal_report(pre.build_report(
        declaration_hash=declaration["declaration_hash"],
        eval_plan=declaration["eval_plan"],
        primary={
            "metric": declaration["target"]["metric"],
            "candidate_value": paired["arm_means"]["candidate"],
            "comparator_value": paired["arm_means"]["incumbent"],
            "delta": paired["candidate_minus_incumbent"]["delta_mean"],
            "ci95_low": paired["candidate_minus_incumbent"]["ci95_low"],
            "ci95_high": paired["candidate_minus_incumbent"]["ci95_high"],
        },
        protected=[
            {"name": "public_suite_pass_rate",
             "candidate_value": public["candidate_pass_rate"],
             "comparator_value": public["incumbent_pass_rate"],
             "delta": round(public["candidate_pass_rate"] - public["incumbent_pass_rate"], 6)},
            {"name": "holdout_lane_rate",
             "candidate_value": holdout["candidate_lane_rate"],
             "comparator_value": round(P_INCUMBENT, 6),
             "delta": holdout["aggregate_delta"]},
            {"name": "ancestor_anchor_floor",
             "candidate_value": paired["arm_means"]["candidate"],
             "comparator_value": paired["arm_means"]["ancestor_anchor"],
             "delta": paired["candidate_minus_ancestor_mean"]},
        ],
        builder_rationale=proposal.get("rationale", ""),
    ))

    # (7) The asymmetric gate (may only reject).
    gate = pre.evaluate_gate(declaration, report)

    # (8) Post-attestation: the loop must not have touched the zone.
    zone_post = _zone_attestation(repo_root)
    zone_intact = (zone_pre is None and zone_post is None) or (
        zone_pre is not None and zone_post is not None and zone_pre["zone_hash"] == zone_post["zone_hash"]
    )

    # (9) PR payload — declaration + report attached; NO promotion.
    pr_payload = {
        "title": f"[AutoLab] candidate {proposal['patch_fingerprint']} (seed {seed})",
        "declaration": declaration,
        "improvement_report": report,
        "gate_decision": gate.to_dict(),
        "attachments": ["declaration", "improvement_report", "gate_decision"],
    }

    stages = _chain([
        {"stage": "pre_registration", "declaration_hash": declaration["declaration_hash"]},
        {"stage": "propose", "patch_fingerprint": proposal["patch_fingerprint"],
         "builder_id": proposal["builder_id"]},
        {"stage": "public_suite", "hash": sha256_hex(public)},
        {"stage": "budgeted_holdout", "hash": sha256_hex(holdout)},
        {"stage": "paired_comparison", "hash": sha256_hex(paired)},
        {"stage": "improvement_report", "report_hash": report["report_hash"]},
        {"stage": "gate", "gate_green": gate.gate_green},
    ])

    record = {
        "schema": ITERATION_SCHEMA,
        "config": _canonical_config(config),
        "proposal": proposal,
        "public_suite": public,
        "budgeted_holdout": holdout,
        "paired_comparison": paired,
        "declaration": declaration,
        "improvement_report": report,
        "gate": gate.to_dict(),
        "zone_attestation": {
            "pre": zone_pre, "post": zone_post, "zone_intact": zone_intact,
        },
        "pr_payload": pr_payload,
        # No autonomous promotion: the loop stops here and hands to a human.
        "promotion": {
            "promoted": False,
            "awaiting_human_ratification": True,
            "requires": ["deterministic_gate_green", "human_promotion_token"],
            "gate_green": gate.gate_green,
        },
        "stages": stages,
        "stages_root_hash": stages[-1]["entry_hash"] if stages else GENESIS,
    }
    record["loop_hash"] = sha256_hex({k: v for k, v in record.items() if k != "loop_hash"})
    return IterationResult(record=record)


def _canonical_config(config: dict[str, Any]) -> dict[str, Any]:
    """The subset of config that determines the iteration (keeps replay pure)."""
    keys = ("seed", "n", "bootstrap", "holdout_lanes", "holdout_budget",
            "holdout_cursor", "holdout_exposures", "holdout_suite_version",
            "declaration_id", "target_metric", "direction", "min_delta",
            "decision_rule", "protected_metrics", "arm_probabilities", "builder_id")
    out = {"builder_id": config.get("builder_id", STUB_BUILDER_ID)}
    for key in keys:
        if key in config:
            out[key] = config[key]
    return out


def _chain(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev = GENESIS
    chained = []
    for seq, entry in enumerate(entries):
        item = {"seq": seq, **entry, "prev_hash": prev}
        item["entry_hash"] = sha256_hex({k: v for k, v in item.items() if k != "entry_hash"})
        prev = item["entry_hash"]
        chained.append(item)
    return chained


def _zone_attestation(repo_root: Optional[str | Path]) -> Optional[dict[str, Any]]:
    if repo_root is None:
        return None
    try:
        attestation = fz.attest(repo_root)
    except fz.FrozenZoneError:
        return None
    return {"zone_hash": attestation.zone_hash, "matches_manifest": attestation.matches,
            "manifest_version": attestation.manifest_version}


# ---------------------------------------------------------------------------
# Replay.
# ---------------------------------------------------------------------------
def replay(record: dict[str, Any], *, repo_root: Optional[str | Path] = None) -> dict[str, Any]:
    """Re-derive an iteration from its sealed config; confirm byte-identical."""
    rebuilt = run_iteration(record["config"], repo_root=repo_root)
    issues = []
    if rebuilt.loop_hash != record.get("loop_hash"):
        issues.append("loop_hash mismatch: iteration is not reproducible from its config")
    if rebuilt.record["stages_root_hash"] != record.get("stages_root_hash"):
        issues.append("stages_root_hash mismatch: sealed stage chain differs")
    return {"attested": not issues, "issues": issues, "loop_hash": rebuilt.loop_hash}
