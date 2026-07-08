# SFA-Bench v1.0 Research Release Pack

SFA-Bench is a deterministic offline governance harness for candidate
improvement. It evaluates proposed repository changes through fixed checks,
candidate packets, explicit human review, lineage recording, and adversarial
pressure. Its purpose is to make improvement claims auditable and reproducible,
not to automate trust.

This release pack summarizes the Item 7-11 governance path and gives reviewers a
bounded way to inspect what the system claims, what it does not claim, how the
pieces fit together, and how to reproduce the local checks.

## Pack Contents

- [Claims and Limits](sfa-bench-v1-claims-and-limits.md)
- [Reproducibility Guide](sfa-bench-v1-reproducibility-guide.md)
- [Threat Model](sfa-bench-v1-threat-model.md)
- [Architecture](sfa-bench-v1-architecture.md)
- [Reviewer Commands](../../examples/v1_research_release_commands.md)
- [Checklist Fixture](../../tests/fixtures/v1_research_release_checklist.json)

## What The System Is

The v1.0 governance path treats a candidate improvement as an object to be
declared, checked, classified, reviewed, and recorded. Candidate generation is
outside the trust boundary. Verification and promotion eligibility are inside the
trust boundary and are controlled by deterministic commands.

The system can say, for a checked-in candidate and the current fixtures, whether
the implemented offline checks passed, whether protected paths were touched,
whether release artifacts are clean, whether a candidate packet is well formed,
and whether a human decision was recorded. It cannot infer intent, prove a
candidate is safe in the world, or replace reviewer judgment.

## Items 7-11

Item 7 established the governed AutoLab runner. The runner orders declaration,
frozen-zone checks, deterministic evaluation, gate outcome, human ratification,
lineage inscription, and circuit-breaker accounting. It does not write patches
or approve its own outputs.

Item 8 exercised the allowed candidate path with a non-frozen documentation
candidate. It demonstrated that a candidate can be useful while staying outside
the frozen governance surface and preserving the same verification discipline.

Item 9 added the external candidate harness. It resolves a branch or commit
against `origin/main`, records the changed paths, checks for frozen-path touches,
runs protected verification in a detached worktree, classifies the outcome, and
writes a candidate packet for review.

Item 10 added the ratification packet and lineage CLI. It consumes a candidate
packet, records an explicit human action, and writes a ratification packet plus a
lineage record. `--ratify` is refused unless the candidate was classified as
`PROMOTION_READY`, and even then the CLI records approval rather than silently
promoting code.

Item 11 added the adversarial candidate suite. It exercises unsafe or malformed
candidate paths, including frozen-path tampering, release-gate dirtiness,
ratification misuse, and malformed packets, and expects controlled halt or
rejection outcomes.

## Review Claim

A reviewer should interpret a passing v1.0 governance run as evidence that the
repository's implemented offline checks accepted the candidate under the current
rules and fixtures, that the candidate did not change frozen paths relative to
the selected base, and that the human-review and lineage surfaces can record the
decision without auto-promotion.

That is a strong claim for local governance hygiene. It is deliberately not a
claim about autonomous intelligence, alignment, universal safety, or production
fitness.

## Rejected Overclaims

- SFA-Bench is not autonomous self-improving AI.
- SFA-Bench is not proof of alignment.
- SFA-Bench is not a safety guarantee.
- SFA-Bench is not a replacement for human judgment.

## Reviewer Path

From a clean checkout with `origin/main` available, run the commands in the
[Reproducibility Guide](sfa-bench-v1-reproducibility-guide.md). The shortest
review path is:

```powershell
py -3 verify_all.py
py -3 autolab_runner_demo.py
py -3 external_candidate_harness.py --help
py -3 ratification_packet_cli.py --help
py -3 adversarial_candidate_suite.py --ci
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
```

For an Item 12 candidate branch, also confirm that the branch diff is limited to
the release-pack files:

```powershell
git diff --name-only origin/main...HEAD
```