# Checkpoint — AutoLab Item 3: Loop controller

Scope: a controller that runs one iteration — propose → public suite → budgeted
holdout → paired comparison via the Item-1 trial harness (arms candidate,
incumbent, ancestor-anchor; identical seeds; bootstrap CI; pre-registered
threshold) → sealed improvement report → PR opened with declaration + report
attached — with no autonomous promotion.

## Deliverables

- `autolab/controller.py` — pure `run_iteration`, `replay`, stub builder,
  frozen-evaluator stages, budgeted holdout, pre/post zone attestation
  (**frozen** via amendment `fz-v0.3.0`).
- `loop_controller_demo.py` — full offline dry-run + rejecting variant + replay
  (added to `verify_all.py`).
- `tests/test_controller.py` — 26 deterministic tests.
- `autolab/frozen_manifest.json` → `fz-v0.3.0` (14 frozen files);
  `autolab/amendments/fz-v0.3.0-add-controller.json` records the
  `d9fa889a… → 7edfb561…` transition.
- `docs/autolab-loop-controller.md`.

## Acceptance criteria

- **Full dry-run on a stub builder in CI.** `loop_controller_demo.py` runs the
  whole pipeline offline and is wired into `verify_all.py`; `test_controller.py`
  asserts the seven pipeline stages and the gate outcome.
- **Byte-identical replay of a loop iteration.** `replay` re-derives the sealed
  `loop_hash` from the config; `test_replay_is_byte_identical` and
  `test_replay_with_repo_root_is_byte_identical`.

## The six hard invariants — explicit accounting

1. **Frozen zone.** The controller is added to the zone (amendment `fz-v0.3.0`).
   Each iteration brackets itself with a pre/post zone attestation; the loop
   reads the frozen evaluators and writes nothing to the zone
   (`test_zone_attestation_matches_manifest`, `zone_intact`). ✔ Enforced.

2. **Asymmetric gate.** *Central to this item.* The record's `promotion` block is
   always `{promoted: false, awaiting_human_ratification: true}`; even a
   gate-green iteration is not promoted, and a rejecting variant is also not
   promoted (`test_no_autonomous_promotion`, `test_even_gate_green_does_not_
   promote`, `test_rejected_candidate_not_promoted`). No autonomous promotion
   path exists in code. ✔ Enforced.

3. **Builder cannot attest.** The improvement-report numbers are frozen-evaluator
   outputs (verifier via the harness, public suite, holdout); the builder
   contributes only an advisory rationale that is excluded from the gate
   (`test_builder_rationale_does_not_move_the_gate`). ✔ Enforced.

4. **Append-only lineage.** The iteration is sealed into a hash-chained stage
   record with a `loop_hash` and `stages_root_hash`
   (`test_stage_chain_is_linked`). `run_iteration` is pure (no writes); the
   inscription/meta-ledger is Item 5. ✔ Consistent; not yet complete (by design).

5. **Budgeted holdout.** Feedback is coarse — lane pass/fail + aggregate delta,
   no per-case gold (`test_holdout_is_coarse`). Seeds are consumed append-only
   from a deterministic schedule with no reuse across cursors
   (`test_no_seed_reuse_across_cursors`), metered against a per-suite-version
   budget with a `budget_exhausted` flag (`test_budget_exhaustion_flagged`). ✔
   Enforced (the exhaustion breaker halts in Item 5).

6. **Determinism and offline CI.** All randomness derives from one integer seed
   via SHA-256; no wall-clock, network, or model. `--live` (a real builder) is
   opt-in and never in CI. 26 tests + the demo run offline; replay is
   byte-identical. ✔ Enforced.

## Verification run

- `python -m unittest discover -s tests` → all OK (26 new).
- `python loop_controller_demo.py` → PASS.
- `python verify_all.py` → PASS (includes `loop_controller_demo.py`).
- `python release_gate.py --ci` → PASS.
- `python frozen_zone_check.py` → attestation PASS at `fz-v0.3.0`.

## Merge-order note

Stacks on Items 1 and 2 (PRs #22, #23) and targets `main` (genesis → the
frozen-zone amendment gate passes without a token). Once earlier items land in
`main`, a rebase makes the `fz-v0.3.0` bump a real amendment requiring
`SFA_FROZEN_ZONE_AMENDMENT_TOKEN=fz-v0.3.0-add-controller` in CI — the intended
human-ratification behavior.

## Conflicts encountered

None. No invariant was bent. The paired comparison reuses the frozen Item-1
harness primitives (`build_task_pool`, `sample_tasks`, `bootstrap_ci`, the
verifier) rather than modifying the harness — its `true_prior/placebo/baseline`
semantics stay intact.

## Not in this item

Promotion/rollback and the pinned anchor-suite tagging are Item 4. The persisted
meta-ledger + circuit breakers (including holdout-budget-exhausted halt) are Item
5. Version of record stays `v1.1.0`.
