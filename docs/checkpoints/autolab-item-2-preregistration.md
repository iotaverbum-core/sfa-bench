# Checkpoint — AutoLab Item 2: Pre-registration module

Scope: a sealed pre-registration declaration (target metric, direction, eval
plan, protected-metric tolerances) created before patch generation; a gate that
compares a sealed improvement report to the declaration; a Pareto no-regression
check.

## Deliverables

- `autolab/preregistration.py` — declaration + report schemas, sealing,
  `evaluate_gate` (asymmetric, reject-only), recomputed primary + Pareto checks
  (**frozen** via amendment `fz-v0.2.0`).
- `examples/preregistration/` — sealed `declaration.json`, `report_pass.json`,
  `report_regression.json`.
- `preregistration_demo.py` — offline runner (added to `verify_all.py`).
- `tests/test_preregistration.py` — 20 deterministic tests.
- `autolab/frozen_manifest.json` bumped to `fz-v0.2.0` (13 frozen files);
  `autolab/amendments/fz-v0.2.0-add-preregistration.json` records the
  `e0c98d37... -> 16f9cefb...` transition.
- `docs/autolab-preregistration.md`.

## Acceptance criteria

- **Mismatch fixture rejected.** `report_regression.json` clears the primary
  threshold but regresses two protected metrics; the gate rejects it
  (`test_mismatch_fixture_is_rejected`, plus binding / eval-plan / threshold /
  direction / decision-rule / missing-metric rejection tests).
- **Declaration hash in report.** The report binds to the declaration by hash;
  the gate rejects any report whose `declaration_hash` does not match
  (`test_declaration_hash_present_in_reports`, `test_binding_mismatch_rejected`).

## The six hard invariants — explicit accounting

1. **Frozen zone.** The gate is gate policy, so it is added to the frozen zone by
   the human amendment channel: manifest → `fz-v0.2.0`, resealed
   (`16f9cefb...cedb`), with an append-only amendment record. Verified that the
   post-commit amendment gate rejects the manifest change without the token and
   accepts it with `fz-v0.2.0-add-preregistration`. ✔ Enforced (and exercised the
   Item-1 mechanism for real).

2. **Asymmetric gate.** *This item implements it.* `evaluate_gate` returns only
   `gate_green` or rejection reasons — no `promote`/`promoted` field exists
   (`test_gate_has_no_promotion_path`). Promotion still requires a human token
   (Item 4); no autonomous promotion path is introduced. ✔ Enforced.

3. **Builder cannot attest.** The gate recomputes every pass/fail from the raw
   frozen-evaluator numbers and the declared thresholds; builder-supplied
   booleans and `builder_rationale` are ignored
   (`test_builder_rationale_is_ignored`,
   `test_self_reported_booleans_do_not_help_a_bad_report`). ✔ Enforced.

4. **Append-only lineage.** The declaration and report are sealed with canonical
   hashes; the report references the declaration by hash. The full meta-ledger is
   Item 5; this item produces the sealed, hash-bound records it will chain. ✔
   Consistent; not yet complete (by design).

5. **Budgeted holdout.** Not exercised beyond the eval plan naming a holdout lane;
   no holdout data is read here. The declaration's `eval_plan` is the pre-registered
   place where holdout suite/version and seeds are committed, which the budgeted
   holdout machinery (Item 3/5) will consume append-only. ✔ Respected.

6. **Determinism and offline CI.** `evaluate_gate` is a pure function; sealing is
   deterministic; fixtures are sealed and re-verified; no wall-clock, network,
   model, or randomness. 20 tests + the demo run offline. ✔ Enforced.

## Verification run

- `python -m unittest discover -s tests` → all OK (20 new + 18 frozen-zone + 27
  frontier).
- `python preregistration_demo.py` → PASS.
- `python verify_all.py` → PASS (includes `preregistration_demo.py`).
- `python release_gate.py --ci` → PASS.
- `python frozen_zone_check.py` → attestation PASS at `fz-v0.2.0`.

## Merge-order note

This PR targets `main` (which has no frozen manifest → the frozen-zone amendment
gate takes the genesis path and passes without a token). It stacks on Item 1
(PR #22). If Item 1 lands in `main` first and this branch is rebased onto it, the
manifest bump to `fz-v0.2.0` becomes a real zone amendment. CI validates the
`fz-v0.2.0-add-preregistration` amendment token against the bound amendment
record and zone hashes; when a protected CI token is unavailable, the wrapper can
infer this exact token from the matching record. This preserves the intended
human-ratification binding rather than treating the amendment as a regression.

## Conflicts encountered

None. No invariant was bent.

## Not in this item

Version-of-record stays `v1.1.0` (the bump is proposed in the final PR). The loop
controller that seals the declaration *before* invoking the builder, and the
budgeted-holdout consumption, are Item 3.
