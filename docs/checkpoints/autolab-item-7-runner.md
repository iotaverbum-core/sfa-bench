# AutoLab Item 7 Checkpoint - End-to-End Runner

Item 7 adds the frozen orchestration layer that runs the full AutoLab path
without letting a caller skip gate, human, lineage, or breaker steps.

## Added

- `autolab/runner.py`: frozen end-to-end runner for controller ordering,
  improvement-report sealing, deterministic gate evaluation, human ratification,
  lineage inscription, rejection logging, and pre/post circuit breakers.
- `autolab_runner_demo.py`: offline demo covering a green path, a gate-red
  rejection, and a preflight halt that prevents builder invocation.
- `tests/test_autolab_runner.py`: deterministic tests for successful promotion,
  gate rejection, missing/wrong ratification, active halt blocking, preflight
  halt, postflight budget-exhaustion halt, and frozen-zone integration.
- Frozen-zone amendment `fz-v0.7.0-add-runner`: adds the runner to the frozen
  zone and advances the manifest to `fz-v0.7.0`.

## Invariants

- **No run through active halt.** A live halt must be cleared by Item 6 restart
  clearance before the runner can start.
- **Builder cannot bypass ordering.** The builder runs only through Item 3
  controller ordering, after declaration sealing and any holdout reservation.
- **Rejections are ledgered.** Red gates and failed human promotion attempts
  append rejection events for breaker accounting.
- **Promotion is still human-gated.** A green deterministic gate is not enough;
  the sealed ratification record and matching token remain required.
- **Lineage is automatic after promotion.** A human-ratified promotion is
  immediately inscribed before the runner reports success.
