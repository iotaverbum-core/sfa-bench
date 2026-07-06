"""Pre-registration declaration + asymmetric gate (SFA-AutoLab v0, Item 2).

FROZEN ZONE — this module is gate policy and is listed in
``autolab/frozen_manifest.json``. The loop may not patch it; changes flow only
through the human-only amendment channel.

The idea, borrowed from pre-registration in empirical science: **commit to the
claim before you look at the result.** Before a patch is generated, the loop
seals a *declaration* — the target metric, the direction of the expected
improvement, the pre-registered threshold and decision rule, the exact
evaluation plan, and the protected metrics that must not regress (a Pareto
no-regression constraint). Afterwards a frozen evaluator computes an
*improvement report* from raw artifacts. The gate then checks the report against
the sealed declaration.

Three invariants shape this module:

  * **Asymmetric gate (invariant 2).** ``evaluate_gate`` may only *reject*. It
    returns ``gate_green`` (nothing to reject) or a list of rejection reasons. It
    never promotes and carries no promotion field — promotion needs a human token
    (Item 4). The gate is a pure, deterministic function.

  * **Builder cannot attest (invariant 3).** The gate decides from the numeric
    outputs a *frozen evaluator* produced (metric values, deltas, bootstrap CI
    bounds) and the *declared* thresholds/tolerances. It **recomputes** every
    pass/fail from those raw values and ignores any builder-supplied booleans and
    the advisory ``builder_rationale``. A report cannot talk its way past the
    gate.

  * **Determinism (invariant 6).** Everything is a pure function of the sealed
    inputs; canonical hashes seal the declaration and report; no wall-clock,
    network, model, or randomness enters a decision.

Stdlib-only and standalone (canonical encoding mirrors ``sfa.hashing``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

DECLARATION_SCHEMA = "sfa.autolab.preregistration.v0"
REPORT_SCHEMA = "sfa.autolab.improvement_report.v0"
GATE_SCHEMA = "sfa.autolab.preregistration_gate.v0"

DECLARATION_HASH_KEY = "declaration_hash"
REPORT_HASH_KEY = "report_hash"

DIRECTIONS = ("increase", "decrease")
PROTECTED_DIRECTIONS = ("no_decrease", "no_increase")
DECISION_RULES = ("ci95_low_gt_0", "ci95_high_lt_0", "point_delta_only")

# A tiny tolerance so exact-equality comparisons on floats are stable.
_EPS = 1e-9


# ---------------------------------------------------------------------------
# Canonical hashing (mirrors sfa.hashing / autolab.frozen_zone).
# ---------------------------------------------------------------------------
def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _hash_excluding(obj: dict[str, Any], key: str) -> str:
    return sha256_hex({k: v for k, v in obj.items() if k != key})


class PreregistrationError(ValueError):
    """Raised for a malformed declaration or report."""


# ---------------------------------------------------------------------------
# Declaration.
# ---------------------------------------------------------------------------
def build_declaration(
    *,
    declaration_id: str,
    target_metric: str,
    direction: str,
    min_delta: float,
    decision_rule: str,
    comparator: str,
    eval_plan: dict[str, Any],
    protected_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct (unsealed) a pre-registration declaration."""
    if direction not in DIRECTIONS:
        raise PreregistrationError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if decision_rule not in DECISION_RULES:
        raise PreregistrationError(f"decision_rule must be one of {DECISION_RULES}")
    if float(min_delta) < 0:
        raise PreregistrationError("min_delta must be non-negative (a magnitude)")
    protected = []
    for entry in protected_metrics:
        pdir = entry.get("direction")
        if pdir not in PROTECTED_DIRECTIONS:
            raise PreregistrationError(
                f"protected metric direction must be one of {PROTECTED_DIRECTIONS}"
            )
        protected.append({
            "name": str(entry["name"]),
            "direction": pdir,
            "tolerance": float(entry.get("tolerance", 0.0)),
        })
    return {
        "schema": DECLARATION_SCHEMA,
        "declaration_id": str(declaration_id),
        "phase": "pre_patch",
        "target": {
            "metric": str(target_metric),
            "direction": direction,
            "min_delta": float(min_delta),
            "decision_rule": decision_rule,
            "comparator": str(comparator),
        },
        "eval_plan": canonical_eval_plan(eval_plan),
        "protected_metrics": sorted(protected, key=lambda p: p["name"]),
    }


def canonical_eval_plan(eval_plan: dict[str, Any]) -> dict[str, Any]:
    """Normalize an eval plan so declaration/report comparison is order-stable."""
    plan = dict(eval_plan)
    if "arms" in plan and isinstance(plan["arms"], list):
        plan["arms"] = list(plan["arms"])  # arms are ordered; keep as declared
    if "seeds" in plan and isinstance(plan["seeds"], list):
        plan["seeds"] = list(plan["seeds"])  # seeds are ordered; keep as declared
    return plan


def seal_declaration(declaration: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a ``declaration_hash`` sealing its content."""
    validate_declaration(declaration)
    sealed = {k: v for k, v in declaration.items() if k != DECLARATION_HASH_KEY}
    sealed[DECLARATION_HASH_KEY] = _hash_excluding(sealed, DECLARATION_HASH_KEY)
    return sealed


def validate_declaration(declaration: dict[str, Any]) -> None:
    if declaration.get("schema") != DECLARATION_SCHEMA:
        raise PreregistrationError(f"declaration schema must be {DECLARATION_SCHEMA}")
    target = declaration.get("target")
    if not isinstance(target, dict):
        raise PreregistrationError("declaration.target missing")
    if target.get("direction") not in DIRECTIONS:
        raise PreregistrationError("declaration.target.direction invalid")
    if target.get("decision_rule") not in DECISION_RULES:
        raise PreregistrationError("declaration.target.decision_rule invalid")
    if not isinstance(declaration.get("eval_plan"), dict):
        raise PreregistrationError("declaration.eval_plan missing")
    if not isinstance(declaration.get("protected_metrics"), list):
        raise PreregistrationError("declaration.protected_metrics missing")


# ---------------------------------------------------------------------------
# Improvement report (computed by frozen evaluators, not the builder).
# ---------------------------------------------------------------------------
def build_report(
    *,
    declaration_hash: str,
    eval_plan: dict[str, Any],
    primary: dict[str, Any],
    protected: list[dict[str, Any]],
    builder_rationale: str = "",
) -> dict[str, Any]:
    """Construct (unsealed) an improvement report.

    ``primary`` and ``protected`` carry the *raw* frozen-evaluator numbers
    (metric values, deltas, CI bounds). ``builder_rationale`` is advisory and is
    excluded from every gate check.
    """
    return {
        "schema": REPORT_SCHEMA,
        "declaration_hash": str(declaration_hash),
        "eval_plan": canonical_eval_plan(eval_plan),
        "primary": dict(primary),
        "protected": [dict(p) for p in protected],
        "builder_rationale": str(builder_rationale),
    }


def seal_report(report: dict[str, Any]) -> dict[str, Any]:
    sealed = {k: v for k, v in report.items() if k != REPORT_HASH_KEY}
    sealed[REPORT_HASH_KEY] = _hash_excluding(sealed, REPORT_HASH_KEY)
    return sealed


# ---------------------------------------------------------------------------
# The asymmetric gate.
# ---------------------------------------------------------------------------
@dataclass
class GateDecision:
    gate_green: bool
    reasons: list[str]
    declaration_hash: str
    report_hash: Optional[str]
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GATE_SCHEMA,
            "gate_green": self.gate_green,
            "reasons": list(self.reasons),
            "declaration_hash": self.declaration_hash,
            "report_hash": self.report_hash,
            "checks": self.checks,
        }


def _direction_ok(direction: str, delta: float, min_delta: float) -> bool:
    if direction == "increase":
        return delta >= min_delta - _EPS
    return delta <= -min_delta + _EPS  # decrease: delta must be <= -min_delta


def _decision_rule_ok(rule: str, ci_low: Optional[float], ci_high: Optional[float]) -> bool:
    if rule == "point_delta_only":
        return True
    if rule == "ci95_low_gt_0":
        return ci_low is not None and ci_low > _EPS
    if rule == "ci95_high_lt_0":
        return ci_high is not None and ci_high < -_EPS
    return False


def _protected_ok(direction: str, delta: float, tolerance: float) -> bool:
    """A protected metric holds if it does not move the wrong way beyond tolerance."""
    if direction == "no_decrease":
        return delta >= -abs(tolerance) - _EPS
    # no_increase
    return delta <= abs(tolerance) + _EPS


def evaluate_gate(declaration: dict[str, Any], report: dict[str, Any]) -> GateDecision:
    """Compare a sealed report to a sealed declaration. May only reject.

    Every pass/fail is recomputed from the report's *raw* numeric fields and the
    declaration's thresholds — builder-supplied booleans and ``builder_rationale``
    are ignored (invariant 3).
    """
    validate_declaration(declaration)
    decl_hash = declaration.get(DECLARATION_HASH_KEY)
    if not decl_hash:
        raise PreregistrationError("declaration is not sealed (no declaration_hash)")
    # Re-seal defensively: the declaration must actually hash to its stated hash.
    if _hash_excluding(declaration, DECLARATION_HASH_KEY) != decl_hash:
        raise PreregistrationError("declaration_hash does not match declaration content")

    reasons: list[str] = []
    checks: dict[str, Any] = {}
    report_hash = report.get(REPORT_HASH_KEY)

    # 1. Declaration binding: the report must reference this exact declaration.
    binding_ok = report.get("declaration_hash") == decl_hash
    checks["declaration_binding"] = binding_ok
    if not binding_ok:
        reasons.append(
            "declaration binding mismatch: report.declaration_hash "
            f"{report.get('declaration_hash')} != {decl_hash}"
        )

    # 2. Eval-plan conformance: the report must have used the pre-registered plan.
    plan_ok = canonical_bytes(canonical_eval_plan(report.get("eval_plan", {}))) == \
        canonical_bytes(declaration["eval_plan"])
    checks["eval_plan_conformance"] = plan_ok
    if not plan_ok:
        reasons.append("eval plan deviates from the pre-registration")

    # 3. Primary metric: direction, threshold, and decision rule (recomputed).
    target = declaration["target"]
    primary = report.get("primary", {})
    primary_checks: dict[str, Any] = {}
    if primary.get("metric") != target["metric"]:
        reasons.append(
            f"primary metric {primary.get('metric')!r} != declared {target['metric']!r}"
        )
        primary_checks["metric_match"] = False
    else:
        primary_checks["metric_match"] = True
        delta = _as_float(primary.get("delta"))
        if delta is None:
            reasons.append("primary.delta missing or non-numeric")
        else:
            dir_ok = _direction_ok(target["direction"], delta, float(target["min_delta"]))
            rule_ok = _decision_rule_ok(
                target["decision_rule"],
                _as_float(primary.get("ci95_low")),
                _as_float(primary.get("ci95_high")),
            )
            primary_checks["direction_threshold"] = dir_ok
            primary_checks["decision_rule"] = rule_ok
            primary_checks["delta"] = delta
            if not dir_ok:
                reasons.append(
                    f"primary delta {delta} does not meet declared "
                    f"{target['direction']} >= {target['min_delta']}"
                )
            if not rule_ok:
                reasons.append(
                    f"decision rule {target['decision_rule']!r} not satisfied "
                    f"(ci_low={primary.get('ci95_low')}, ci_high={primary.get('ci95_high')})"
                )
    checks["primary"] = primary_checks

    # 4. Pareto no-regression on protected metrics (recomputed from raw deltas).
    protected_report = {p.get("name"): p for p in report.get("protected", [])}
    protected_checks: list[dict[str, Any]] = []
    for declared in declaration["protected_metrics"]:
        name = declared["name"]
        observed = protected_report.get(name)
        if observed is None:
            reasons.append(f"protected metric {name!r} missing from report")
            protected_checks.append({"name": name, "present": False, "ok": False})
            continue
        delta = _as_float(observed.get("delta"))
        if delta is None:
            reasons.append(f"protected metric {name!r} has no numeric delta")
            protected_checks.append({"name": name, "present": True, "ok": False})
            continue
        ok = _protected_ok(declared["direction"], delta, declared["tolerance"])
        if not ok:
            reasons.append(
                f"protected metric {name!r} regressed: delta {delta} violates "
                f"{declared['direction']} within tolerance {declared['tolerance']}"
            )
        protected_checks.append({"name": name, "present": True, "delta": delta, "ok": ok})
    checks["protected"] = protected_checks
    checks["pareto_no_regression"] = all(c.get("ok") for c in protected_checks)

    return GateDecision(
        gate_green=not reasons,
        reasons=reasons,
        declaration_hash=decl_hash,
        report_hash=report_hash,
        checks=checks,
    )


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):  # guard: bools are ints in Python
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
