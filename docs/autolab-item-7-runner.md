# AutoLab Item 7 Runner (`fz-v0.7.0`)

AutoLab Item 7 adds the frozen end-to-end runner released as `fz-v0.7.0`.
The runner is the orchestration layer that calls the existing AutoLab controls in
the required order. It does not generate patches, rewrite history, or replace
human approval. Its job is to make the allowed path explicit and auditable.

## What the Runner Enforces

The Item 7 runner connects these controls into one sequence:

1. **Proposal declaration**: the candidate run starts from a pre-registration
   declaration that names the target metric, decision rule, evaluation plan, and
   protected metrics before the builder result is evaluated.
2. **Frozen-zone checks**: the runner refuses to start while an active halt is
   present, evaluates circuit breakers before invoking the builder, and relies on
   the controller to attest the frozen zone before and after the builder callback.
3. **Pre-registered evaluation**: the evaluator returns an improvement report
   bound to the sealed declaration and declared evaluation plan.
4. **Deterministic gate**: the pre-registration gate recomputes pass/fail from
   raw report fields. A red gate appends `gate_rejected`; it does not promote.
5. **Human ratification**: a green deterministic gate is not sufficient. The
   runner requires a sealed human ratification record and a matching token before
   appending `human_ratification`.
6. **Lineage inscription**: a ratified promotion is inscribed into append-only
   lineage so the current target is derived from ledger history, not rewritten
   state.
7. **Circuit-breaker accounting**: rejection events and post-run breaker checks
   give Item 6 the history needed to count repeated failures, halted runs,
   exhausted holdout budget, and withered lineages.

## Release Boundary

`fz-v0.7.0` adds `autolab/runner.py` to the frozen zone through amendment
`fz-v0.7.0-add-runner`. Candidate patches may use the runner, docs, examples,
and fixtures. They must not modify frozen governance files unless a separate
human amendment is intended.

## Demo Outcomes

`autolab_runner_demo.py` demonstrates three expected paths:

- green path: promoted and inscribed into lineage;
- gate-red path: rejected at the deterministic gate; and
- preflight breaker: halted before builder invocation because a frozen path was
  proposed.

The same expected outcomes are recorded in
[`tests/fixtures/autolab_item7_expected_outcomes.json`](../tests/fixtures/autolab_item7_expected_outcomes.json).
