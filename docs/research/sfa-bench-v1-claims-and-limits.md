# SFA-Bench v1.0 Claims And Limits

This document states the strongest claims supported by the v1.0 research release
pack and the limits that must travel with those claims.

## Supported Claims

SFA-Bench is a deterministic offline governance harness for candidate
improvement. Under the checked-in implementation and fixtures, it can run a
repeatable local verification path without provider credentials, network access,
or live model calls.

The governed candidate path can record a candidate's changed files, detect
frozen-path touches relative to `origin/main`, run protected verification
commands, classify outcomes, and write a candidate packet for review.

The ratification path can validate candidate packets, refuse ratification for
non-`PROMOTION_READY` candidates, record explicit human actions, and write
lineage records without moving branch pointers or promoting code by itself.

The adversarial candidate suite can exercise specific unsafe or malformed inputs
and confirm that those cases halt or reject with expected outcomes.

The release gate can reject dirty release state, protected path modifications,
generated sealed artifacts in the index, missing CI command coverage, and version
record mismatches covered by its implemented checks.

## Required Limits

The claims above apply to the repository's implemented checks. They do not cover
unmodeled attacks, unreviewed code paths, future changes, production deployment
conditions, external model behavior, or semantic correctness outside the fixed
verification rules.

Passing the v1.0 governance path means that deterministic checks passed for the
candidate under review. It does not mean the candidate is useful, wise, safe to
deploy, or aligned with a user's goals.

Candidate generation remains outside the trust boundary. The system can govern a
candidate that someone or something proposes; it does not make proposal intent
trustworthy.

Human ratification remains a record of explicit review action. It is not a proof
that the human was correct, authorized in every possible organizational context,
or free from social, procedural, or operational error.

## Rejected Overclaims

- SFA-Bench is not autonomous self-improving AI.
- SFA-Bench is not proof of alignment.
- SFA-Bench is not a safety guarantee.
- SFA-Bench is not a replacement for human judgment.

## Interpretation Rule

Use the narrowest true statement: "This candidate passed the implemented offline
governance checks under the recorded base and fixtures." Do not shorten that to
"the system improved itself" or "the candidate is safe."