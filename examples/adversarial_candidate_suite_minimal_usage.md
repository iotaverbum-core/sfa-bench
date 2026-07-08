# Adversarial Candidate Suite Minimal PowerShell Usage

Run the suite from the repository root:

```powershell
py -3 adversarial_candidate_suite.py
```

For CI-style labeling:

```powershell
py -3 adversarial_candidate_suite.py --ci
```

The command creates temporary detached worktrees, runs the controlled adversarial
cases, prints expected versus actual outcomes, and exits with status `0` only
when every case passes.

After a successful run, the active checkout should not contain generated
candidate packets or ratification packets from the suite.
