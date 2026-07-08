# SFA-Bench v1.0 Architecture

SFA-Bench is a deterministic offline governance harness for candidate
improvement. The architecture separates proposal generation from verification,
classification, human action, and lineage.

## Governance Flow

```text
external candidate -> candidate packet -> verification -> outcome classification -> ratification packet -> explicit human action -> lineage record -> adversarial pressure
```

The same flow as staged components:

```text
external candidate
        |
        v
candidate packet
        |
        v
verification
        |
        v
outcome classification
        |
        v
ratification packet
        |
        v
explicit human action
        |
        v
lineage record
        |
        v
adversarial pressure
```

## Components

External candidate: a branch or commit proposed outside the verifier. The system
does not trust the source of the candidate by default.

Candidate packet: the Item 9 harness output. It records base and target commits,
changed files, frozen-path status, protected command results, and the final
outcome.

Verification: deterministic offline commands run against the candidate. These
commands check repository behavior, release hygiene, and frozen-zone discipline
without live model calls.

Outcome classification: the harness maps command results and frozen-path status
to explicit classes such as `PROMOTION_READY`, `REJECTED_BY_TESTS`,
`REJECTED_BY_RELEASE_GATE`, `REJECTED_BY_FROZEN_ZONE`, or
`HALTED_BY_PREFLIGHT`.

Ratification packet: the Item 10 CLI review artifact. It carries the validated
candidate evidence into a human decision surface.

Explicit human action: prepare, ratify, reject, or halt. Ratification is refused
unless the candidate packet is `PROMOTION_READY`, and no action silently
promotes code.

Lineage record: a decision record derived from validated packet fields and the
explicit human action. It records what was decided; it is not a hidden verifier
input.

Adversarial pressure: the Item 11 suite applies controlled unsafe and malformed
candidate cases so the governance path keeps rejecting known bad patterns.

## Boundaries

The verifier boundary remains fixed: candidate content, evidence, and rules feed
the deterministic checks. Human rationale, lineage history, policy guidance,
model identity, and raw external context do not enter verifier judgment.

The human boundary remains explicit: a green deterministic result can make a
candidate eligible for review, but it cannot approve itself.

The release boundary remains clean: generated outputs and dirty local state must
not be treated as release evidence.

## Failure Behavior

The architecture prefers halt or rejection over silent promotion. Frozen-path
changes halt or reject. Malformed packets reject. Dirty release artifacts reject.
Non-promotion ratification attempts are refused. Repeated or recorded failures
remain visible to the governance path instead of being erased from review.