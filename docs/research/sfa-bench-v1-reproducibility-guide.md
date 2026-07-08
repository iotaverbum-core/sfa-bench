# SFA-Bench v1.0 Reproducibility Guide

This guide gives reviewers one local path for reproducing the v1.0 research
release-pack checks. The path is offline and deterministic under the checked-in
fixtures and the current repository state.

## Preconditions

- Run commands from the repository root.
- Use Python through the Windows launcher as shown below.
- Ensure `origin/main` is available locally before running the frozen-zone check.
- Start from a clean release candidate checkout when running `release_gate.py
  --ci`; the gate rejects untracked files and dirty release artifacts.

## Required Commands

Run the commands in this order:

```powershell
py -3 verify_all.py
py -3 autolab_runner_demo.py
py -3 external_candidate_harness.py --help
py -3 ratification_packet_cli.py --help
py -3 adversarial_candidate_suite.py --ci
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
```

## What Each Command Shows

`py -3 verify_all.py` runs the repository's full offline verification path in an
isolated temporary worktree.

`py -3 autolab_runner_demo.py` demonstrates the governed Item 7 AutoLab runner:
a green path through lineage, a deterministic gate rejection, and a preflight
halt for a frozen-path proposal.

`py -3 external_candidate_harness.py --help` confirms that the Item 9 harness
interface is present for branch or commit evaluation.

`py -3 ratification_packet_cli.py --help` confirms that the Item 10 human-action
interface is present for prepare, ratify, reject, and halt actions.

`py -3 adversarial_candidate_suite.py --ci` runs the Item 11 adversarial cases
and should exit successfully only when the expected halt or rejection outcomes
are observed.

`py -3 release_gate.py --ci` checks release hygiene, including dirty worktree
state, protected paths, generated artifacts, CI command coverage, and release
version records.

`py -3 frozen_zone_check.py --ci --base origin/main` checks that the candidate
does not modify frozen governance paths relative to the selected base.

## Candidate Diff Audit

For the Item 12 release-pack candidate, the branch diff must be limited to the
allowed documentation, example, fixture, and README files:

```powershell
git diff --name-only origin/main...HEAD
```

If any path outside the Item 12 allowed list appears, stop and review the branch
before treating the candidate as acceptable.

## Expected Interpretation

All commands passing supports a bounded reproducibility claim: the release pack
and the repository's deterministic offline governance checks agree for this
candidate. It does not prove alignment, autonomous improvement, general safety,
or production readiness.