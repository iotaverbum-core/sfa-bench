# v1 Research Release Reviewer Commands

Run these commands from the repository root in a clean checkout with
`origin/main` available.

```powershell
py -3 verify_all.py
py -3 autolab_runner_demo.py
py -3 external_candidate_harness.py --help
py -3 ratification_packet_cli.py --help
py -3 adversarial_candidate_suite.py --ci
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
```

For the Item 12 candidate branch, confirm that only release-pack files changed:

```powershell
git diff --name-only origin/main...HEAD
```

The commands support a bounded claim: deterministic offline governance checks
passed for the candidate under the recorded repository state. They do not prove
alignment, autonomous improvement, general safety, or production readiness.