"""Prior State Trial harness (research core).

Measures whether injecting a *matured lesson* (a "prior") into the proposer
improves outcomes, scored entirely by the deterministic SFA verifier. Three arms:

  * ``true_prior``    - the matured lesson matching the task's failure family.
  * ``placebo_prior`` - a length- and format-matched, content-irrelevant lesson
                        drawn from an unrelated family (the control).
  * ``baseline``      - no prior.

The headline result is ``true_prior - placebo_prior``: a lesson that only helps
because of its *content* must beat a matched-but-irrelevant lesson.

Invariant compliance:
  * The proposer never scores. Every accept/reject is ``verifier.verify`` - a pure
    deterministic function. The prior only shapes the proposer's proposal.
  * Fully deterministic: all randomness is derived from a single integer seed via
    SHA-256, so ``run_trial(config)`` is a pure function of ``config`` and replays
    byte-for-byte. No wall-clock time enters the sealed report.
  * Offline by default: the ``stub`` proposer makes no network or model call. A
    live model is only used behind an explicit CLI ``--live`` flag with a
    user-supplied key (never in CI).

The default ``stub`` proposer is an illustrative mechanism model (like the
fingerprint fixture model ids): under the true prior it corrects the
characteristic flaw with high probability; under placebo/baseline it does not.
It demonstrates and reproducibly tests the harness and metrics; it is not a claim
about any real model. Point ``--live`` at a real model to measure reality.
"""
from __future__ import annotations

from typing import Any, Callable

from . import families as families_mod
from . import policy as policy_mod
from . import verifier as verifier_mod
from .hashing import sha256_hex

TRIAL_SCHEMA = "sfa.prior_state_trial.v1"
RUN_SCHEMA = "sfa.prior_state_trial_run.v1"
STUB_MODEL_ID = "stub-prior-model-v0"
GENESIS = "GENESIS"

ARMS = ("true_prior", "placebo_prior", "baseline")
DEFAULT_N = 30
DEFAULT_BOOTSTRAP = 2000
# Illustrative stub success probabilities (documented in docs/prior-state-trial.md).
P_TRUE = 0.85
P_CONTROL = 0.25

# One rotating skin per task; an invariant logical core (a claim that must match
# an evidence fact) under different surface subjects/values.
_SKINS = (
    ("deductible", "$1,000", "$500"),
    ("annual_premium", "$2,400", "$3,900"),
    ("coverage_limit", "$250,000", "$100,000"),
    ("interest_rate", "7%", "3%"),
    ("effective_date", "2026-01-01", "2025-06-30"),
    ("vendor", "Acme Corp", "Globex Corp"),
)

# The matured lesson that fixes a "contradicts_evidence" failure is the real
# generator-side directive for that family.
_TRUE_DIRECTIVE = policy_mod.DIRECTIVES["contradicts_evidence"]
_UNRELATED_DIRECTIVE = policy_mod.DIRECTIVES["missing_required_field"]


def _uniform(*parts: Any) -> float:
    """Deterministic uniform in [0, 1) derived from SHA-256 of the parts."""
    digest = sha256_hex([str(p) for p in parts])
    return int(digest[:16], 16) / float(1 << 64)


def _rules() -> dict[str, Any]:
    return {
        "verifier_version": verifier_mod.VERIFIER_VERSION,
        "rules": [
            {"id": "schema", "type": "field_types",
             "types": {"conclusion": "str", "cited_evidence": "list", "claims": "list"}},
            {"id": "required", "type": "required_fields",
             "fields": ["conclusion", "cited_evidence", "claims"]},
            {"id": "citations", "type": "citations_exist",
             "field": "cited_evidence", "evidence_collection": "facts", "id_key": "id"},
            {"id": "grounding", "type": "claims_match_evidence",
             "claims_field": "claims", "evidence_collection": "facts",
             "match_on": "subject", "value_key": "value"},
        ],
    }


def build_task_pool(pool_size: int, seed: int) -> list[dict[str, Any]]:
    """Deterministically build a pool of verifier tasks (invariant core, rotating skins)."""
    pool = []
    for i in range(pool_size):
        subject, correct, wrong = _SKINS[i % len(_SKINS)]
        task_id = f"task_{i:04d}_{subject}"
        evidence = {"facts": [{"id": "f1", "subject": subject, "value": correct}]}
        task_input = {"case_id": task_id, "question": f"What is the {subject}?"}
        correct_candidate = {
            "conclusion": f"The {subject} is {correct}.",
            "cited_evidence": ["f1"],
            "claims": [{"subject": subject, "value": correct}],
        }
        flawed_candidate = {
            "conclusion": f"The {subject} is {wrong}.",
            "cited_evidence": ["f1"],
            "claims": [{"subject": subject, "value": wrong}],
        }
        pool.append({
            "task_id": task_id,
            "input": task_input,
            "evidence": evidence,
            "rules": _rules(),
            "correct_candidate": correct_candidate,
            "flawed_candidate": flawed_candidate,
            "failure_family": "contradicts_evidence",
        })
    return pool


def sample_tasks(pool: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Deterministically sample n tasks (with replacement) from the pool."""
    size = len(pool)
    out = []
    for j in range(n):
        idx = int(_uniform(seed, "sample", j) * size)
        out.append(pool[min(idx, size - 1)])
    return out


def _prior_for_arm(arm: str) -> dict[str, Any] | None:
    if arm == "baseline":
        return None
    if arm == "true_prior":
        return {"directive_id": _TRUE_DIRECTIVE["directive_id"], "text": _TRUE_DIRECTIVE["text"]}
    if arm == "placebo_prior":
        return {"directive_id": _UNRELATED_DIRECTIVE["directive_id"],
                "text": _length_match(_UNRELATED_DIRECTIVE["text"], len(_TRUE_DIRECTIVE["text"]))}
    raise ValueError(f"unknown arm: {arm!r}")


def _length_match(text: str, target_len: int) -> str:
    """Pad or trim to match the true prior's length (format-matched control)."""
    if len(text) >= target_len:
        return text[:target_len]
    return text + " " * (target_len - len(text))


def _arm_probability(arm: str) -> float:
    return P_TRUE if arm == "true_prior" else P_CONTROL


def stub_propose(task: dict[str, Any], arm: str, prior: dict[str, Any] | None,
                 seed: int, index: int) -> dict[str, Any]:
    """Deterministic illustrative proposer. Returns the corrected or flawed candidate.

    The prior's *content* only matters through the arm's success probability, which
    the documentation states exactly. ``index`` is the sample position, so tasks
    sampled with replacement draw independently. No scoring happens here.
    """
    draw = _uniform(seed, "propose", task["task_id"], arm, index)
    corrected = draw < _arm_probability(arm)
    return task["correct_candidate"] if corrected else task["flawed_candidate"]


def _score_task(task: dict[str, Any], arm: str, seed: int, index: int,
                proposer: Callable[[dict, str, dict | None, int, int], dict]) -> dict[str, Any]:
    prior = _prior_for_arm(arm)
    candidate = proposer(task, arm, prior, seed, index)
    # The prior never reaches the verifier; the verifier scores deterministically.
    verdict = verifier_mod.verify(task["input"], task["evidence"], candidate, task["rules"])
    family = None
    if verdict.status == "FAIL":
        family = families_mod.classify_family(verdict.category, candidate, task["evidence"])
    return {
        "schema": RUN_SCHEMA,
        "arm": arm,
        "index": index,
        "task_id": task["task_id"],
        "prior_id": (prior or {}).get("directive_id"),
        "prior_hash": sha256_hex(prior) if prior is not None else None,
        "candidate_hash": sha256_hex(candidate),
        "status": verdict.status,
        "category": verdict.category,
        "family": family,
        "score": 1 if verdict.status == "PASS" else 0,
        "verdict_hash": sha256_hex(verdict.to_dict()),
    }


def _chain(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev = GENESIS
    chained = []
    for seq, run in enumerate(runs):
        entry = {"seq": seq, **run, "prev_hash": prev}
        entry["entry_hash"] = sha256_hex({k: v for k, v in entry.items() if k != "entry_hash"})
        prev = entry["entry_hash"]
        chained.append(entry)
    return chained


def bootstrap_ci(deltas: list[float], bootstrap: int, seed: int) -> dict[str, Any]:
    """Percentile bootstrap 95% CI of the mean paired delta (fixed seed)."""
    n = len(deltas)
    if n == 0:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "bootstrap": bootstrap}
    means = []
    for b in range(bootstrap):
        total = 0.0
        for i in range(n):
            idx = int(_uniform(seed, "bootstrap", b, i) * n)
            total += deltas[min(idx, n - 1)]
        means.append(total / n)
    means.sort()
    lo = means[int(0.025 * (bootstrap - 1))]
    hi = means[int(0.975 * (bootstrap - 1))]
    return {
        "mean": round(sum(deltas) / n, 6),
        "ci_low": round(lo, 6),
        "ci_high": round(hi, 6),
        "bootstrap": bootstrap,
    }


def _wld(a_scores: list[int], b_scores: list[int]) -> dict[str, int]:
    w = l = d = 0
    for a, b in zip(a_scores, b_scores):
        if a > b:
            w += 1
        elif a < b:
            l += 1
        else:
            d += 1
    return {"win": w, "loss": l, "draw": d}


def run_trial(config: dict[str, Any], *,
              proposer: Callable[[dict, str, dict | None, int], dict] | None = None) -> dict[str, Any]:
    """Pure function of ``config``; returns a sealed, hash-chained trial report."""
    seed = int(config["seed"])
    n = int(config.get("n", DEFAULT_N))
    arms = list(config.get("arms", ARMS))
    bootstrap = int(config.get("bootstrap", DEFAULT_BOOTSTRAP))
    pool_size = int(config.get("pool_size", max(len(_SKINS), n)))
    proposer = proposer or stub_propose

    pool = build_task_pool(pool_size, seed)
    tasks = sample_tasks(pool, n, seed)

    runs = []
    scores: dict[str, list[int]] = {arm: [] for arm in arms}
    for arm in arms:
        for index, task in enumerate(tasks):
            record = _score_task(task, arm, seed, index, proposer)
            runs.append(record)
            scores[arm].append(record["score"])

    chained = _chain(runs)
    arm_stats = {
        arm: {
            "n": n,
            "passes": sum(scores[arm]),
            "mean_score": round(sum(scores[arm]) / n, 6) if n else 0.0,
        }
        for arm in arms
    }
    comparisons = {}
    for a in arms:
        for b in arms:
            if a != b:
                comparisons[f"{a}_vs_{b}"] = _wld(scores[a], scores[b])

    headline = None
    if "true_prior" in arms and "placebo_prior" in arms:
        deltas = [t - p for t, p in zip(scores["true_prior"], scores["placebo_prior"])]
        ci = bootstrap_ci(deltas, bootstrap, seed)
        headline = {
            "metric": "true_prior_minus_placebo_mean_score",
            "comparator": "placebo_prior",
            "delta_mean": ci["mean"],
            "ci95_low": ci["ci_low"],
            "ci95_high": ci["ci_high"],
            "bootstrap_samples": bootstrap,
            "bootstrap_seed": seed,
            "significant": ci["ci_low"] > 0.0,
        }

    report = {
        "schema": TRIAL_SCHEMA,
        "config": {
            "model_id": config.get("model_id", STUB_MODEL_ID),
            "seed": seed,
            "n": n,
            "arms": arms,
            "bootstrap": bootstrap,
            "pool_size": pool_size,
            "stub_probabilities": {"true_prior": P_TRUE, "control": P_CONTROL},
            "task_pool_hash": sha256_hex([t["task_id"] for t in pool]),
            "sampled_task_hash": sha256_hex([t["task_id"] for t in tasks]),
        },
        "arms": arm_stats,
        "comparisons": comparisons,
        "headline": headline,
        "runs": chained,
        "runs_root_hash": chained[-1]["entry_hash"] if chained else GENESIS,
    }
    report["report_sha"] = sha256_hex({k: v for k, v in report.items() if k != "report_sha"})
    return report


def replay(report: dict[str, Any]) -> dict[str, Any]:
    """Re-derive a report from its sealed config and confirm byte-identical output."""
    rebuilt = run_trial(report["config"])
    issues = []
    if rebuilt["report_sha"] != report.get("report_sha"):
        issues.append("report_sha mismatch: report is not reproducible from its config")
    if rebuilt["runs_root_hash"] != report.get("runs_root_hash"):
        issues.append("runs_root_hash mismatch: sealed run chain differs")
    return {"attested": not issues, "issues": issues, "report_sha": rebuilt["report_sha"]}
