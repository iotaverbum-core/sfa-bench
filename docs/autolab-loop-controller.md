# AutoLab Loop Controller (Item 3)

The controller is the orchestrator the loop runs *within*. One iteration is a
**pure, deterministic function of its config**:

```
propose → public suite → budgeted holdout → paired comparison
(candidate / incumbent / ancestor-anchor, identical seeds, bootstrap CI,
 pre-registered threshold) → sealed improvement report → gate → PR payload
```

`autolab/controller.py` is **frozen** (invariant 1; amendment `fz-v0.3.0`): it is
the controller the loop must not patch.

There is deliberately **no promotion path** in the controller. An iteration ends
at "PR opened with declaration + report attached" and records
`awaiting_human_ratification`. Promotion needs deterministic-gate-green **and** a
human token (Item 4).

## The pipeline

0. **Pre-registration** (Item 2). The declaration is sealed *before* proposing —
   target metric, direction, threshold, decision rule, the exact eval plan
   (arms, seed, bootstrap), and protected-metric tolerances.
1. **Pre-attestation.** The frozen-zone hash is captured (when a repo root is
   given). It is re-captured at the end; the loop must not have touched the zone.
2. **Propose.** The builder returns an advisory proposal (a patch fingerprint and
   a rationale). Its output never scores anything. The default `stub` builder is
   a deterministic mechanism model; `--live` (a user-supplied real builder) is
   opt-in and never in CI.
3. **Public suite.** A frozen evaluator's candidate/incumbent pass rates.
4. **Budgeted holdout.** Coarse feedback only — **lane pass/fail and an aggregate
   delta**, never per-case gold. Exposure is metered against a per-suite-version
   budget; seeds are consumed from an **append-only schedule** and never reused
   (invariant 5).
5. **Paired comparison** via the Item-1 trial harness primitives: arms
   `candidate` / `incumbent` / `ancestor_anchor` over **identical sampled tasks**
   (paired), scored by the fixed verifier, with a fixed-seed bootstrap 95% CI on
   the `candidate − incumbent` per-task delta. The **ancestor-anchor** is a
   pinned v-root reference that guards against silent drift.
6. **Improvement report** (Item 2 schema). Its numbers come **only** from the
   frozen evaluators (verifier via the harness, public suite, holdout). The
   builder contributes only the advisory `builder_rationale`.
7. **Gate** (Item 2). The asymmetric gate compares the sealed report to the
   sealed declaration. It may only reject.

The iteration is sealed into a hash-chained record with a `loop_hash`; `replay`
re-derives it byte-for-byte from the sealed config.

## Invariants

- **Frozen zone (1).** The controller reads the frozen evaluators and writes
  nothing to the zone. `zone_attestation.pre`/`.post` bracket the iteration; a
  drift sets `zone_intact = false`.
- **Asymmetric gate (2).** The record's `promotion` block is always
  `{promoted: false, awaiting_human_ratification: true, requires:
  [deterministic_gate_green, human_promotion_token]}`. Even a gate-green
  iteration is not promoted. There is no autonomous promotion path in code.
- **Builder cannot attest (3).** Report numbers are evaluator outputs; the
  builder rationale is advisory and excluded from the gate. Rewriting the
  rationale changes the report seal (provenance) but never the gate decision.
- **Budgeted holdout (5).** Coarse feedback; append-only, non-reused seeds;
  metered exposure with a `budget_exhausted` flag (a circuit breaker in Item 5).
- **Determinism & offline CI (6).** All randomness derives from one integer seed
  via SHA-256; no wall-clock/network/model. `replay` is byte-identical.

## The stub builder (illustrative)

`stub-autolab-builder-v0` proposes a candidate whose only *scored* effect is the
candidate arm's elevated success probability. Defaults:
`p(candidate)=0.80 > p(incumbent)=0.55 > p(ancestor_anchor)=0.50`. These are
config-overridable stub parameters (recorded in the sealed config), which lets
the harness exercise a **rejecting** iteration — a candidate that fails to beat
the incumbent — to show the gate is not a rubber stamp. This is a mechanism
model, not a claim about any real builder. Point `--live` at a real builder to
measure reality.

## CLI / tests

```bash
python loop_controller_demo.py     # full dry-run + rejecting variant + replay
```

`tests/test_controller.py` covers the pipeline, no-promotion, coarse/metered/
append-only holdout, the three arms + declared seed, builder-rationale blindness,
determinism, and byte-identical replay.
