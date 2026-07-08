# Adversarial Candidate Suite

Item 11 adds a minimal local suite for checking that unsafe or malformed
external-candidate inputs stop with predictable outcomes. The suite does not
promote candidates, update branch pointers, or write run artifacts into the
active checkout. It creates disposable temporary repositories from `origin/main`,
commits controlled adversarial candidates there, and removes the repositories
before exiting.

## Command

```powershell
py -3 adversarial_candidate_suite.py
py -3 adversarial_candidate_suite.py --ci
```

The final status is `PASS` only when every case reports the expected outcome and
expected reason fragment.

## Cases

The case descriptions live in
[`tests/fixtures/adversarial_candidate_cases.json`](../tests/fixtures/adversarial_candidate_cases.json).
The suite runs five cases:

- `safe_docs_candidate`: creates a docs-only candidate and expects
  `PROMOTION_READY` after frozen-path preflight and release-gate checks.
- `frozen_path_tamper`: creates a candidate touching a path frozen as of
  `origin/main` and halts before harness execution with
  `HALTED_BY_PREFLIGHT` and reason `frozen_path_change_proposed`.
- `release_gate_failure`: creates an untracked runtime output in the temporary
  repository; the suite must classify the release-gate failure as
  `REJECTED_BY_RELEASE_GATE`.
- `non_promotion_ratification_attempt`: passes a valid non-promotion candidate
  packet to `ratification_packet_cli.py --ratify`; the CLI refusal is recorded
  as `RATIFICATION_REFUSED`.
- `malformed_packet`: passes a candidate packet missing required fields to the
  ratification CLI and expects `MALFORMED_PACKET_REJECTED`.

## Workspace Discipline

The suite builds disposable Git repositories under a temporary directory from a
`git archive` of `origin/main`. Candidate commits and generated ratification
outputs are created only inside those temporary repositories, not under the
active checkout. The active branch history is not mutated.

The suite does not create branches, tags, or main-history commits in the active
checkout.

## Relationship To Items 9 And 10

The suite uses the Item 9 outcome vocabulary and tests the same decision
surfaces without running the full external candidate harness for every case. It
directly checks frozen-path preflight, invokes the real `release_gate.py --ci`
for release cleanliness, and invokes the real Item 10
`ratification_packet_cli.py` for ratification refusal and malformed-packet
handling.
