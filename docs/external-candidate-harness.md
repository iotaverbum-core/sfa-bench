# External Candidate Harness

Item 9 adds a minimal local harness for evaluating an external candidate branch
or commit against `origin/main`. It is intentionally outside the frozen zone: it
does not change verifier policy, release policy, holdout data, or AutoLab
governance code. Its job is to inspect a candidate, run protected checks in a
detached worktree, and write an auditable packet for human review.

## What It Does

The harness accepts exactly one candidate selector:

```powershell
py -3 external_candidate_harness.py --target <commit-sha>
py -3 external_candidate_harness.py --branch <branch-name>
```

For the resolved commit, it:

1. resolves `origin/main` and the candidate selector to commits;
2. computes `git diff --name-only origin/main...<candidate>`;
3. loads `origin/main:autolab/frozen_manifest.json`;
4. records any changed path that is frozen as of `origin/main`;
5. creates a detached temporary worktree at the candidate commit;
6. runs the protected verification commands; and
7. writes a candidate packet under `out/candidate_packets/<run_id>/`.

The protected commands are:

```powershell
py -3 verify_all.py
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
```

The candidate must already be committed. Uncommitted working-tree changes are
not part of a branch or commit SHA and are not evaluated.

## Outputs

Every run writes:

```text
out/candidate_packets/<run_id>/candidate_packet.json
out/candidate_packets/<run_id>/candidate_packet.md
```

When deterministic checks classify the candidate as `PROMOTION_READY`, the
harness also writes:

```text
out/candidate_packets/<run_id>/ratification_template.md
```

The ratification template is not an automatic approval. It is a review document
for the human promotion step.

## Outcome Classes

The packet outcome is one of:

- `PROMOTION_READY`: protected verification passed and no frozen path changed.
- `REJECTED_BY_TESTS`: `verify_all.py` failed.
- `REJECTED_BY_RELEASE_GATE`: `release_gate.py --ci` failed.
- `REJECTED_BY_FROZEN_ZONE`: a frozen path changed or the frozen-zone check
  failed.
- `HALTED_BY_PREFLIGHT`: the harness could not resolve refs, inspect the base
  manifest, create the candidate worktree, or find a required executable.

Frozen-zone rejection has priority over test and release-gate failures because a
candidate that touches frozen policy must not be promoted through the external
candidate path.

## Packet Contents

The JSON packet records:

- base ref and resolved base commit;
- candidate selector, resolved ref, and resolved commit;
- the `origin/main...<candidate>` changed-path list;
- frozen paths touched as of the base manifest;
- protected command argv, exit code, duration, and output; and
- the final outcome class and reason.

An example fixture is available at
[`tests/fixtures/external_candidate_packet_example.json`](../tests/fixtures/external_candidate_packet_example.json).

## Operational Notes

Run `git fetch origin main` before evaluating a remote candidate if local
`origin/main` may be stale. The harness itself is offline and does not fetch.

Candidate packets are local run artifacts. If you run repository release gates
after generating packets in the same checkout, remove or intentionally stage the
packet outputs first because `release_gate.py --ci` rejects untracked files.
