# External Candidate Harness Minimal PowerShell Usage

This flow evaluates a committed candidate branch or SHA against `origin/main`
without switching the current checkout.

```powershell
# 1. Start from a clean checkout with current refs.
git fetch origin main
git status --short --branch

# 2. Evaluate a candidate commit SHA.
py -3 external_candidate_harness.py --target <commit-sha>

# Or evaluate a candidate branch.
py -3 external_candidate_harness.py --branch <branch-name>

# 3. Inspect the packet path printed by the harness.
Get-Content out/candidate_packets/<run_id>/candidate_packet.md
Get-Content out/candidate_packets/<run_id>/candidate_packet.json

# 4. Promotion-ready candidates also produce a human review template.
Get-Content out/candidate_packets/<run_id>/ratification_template.md
```

The harness runs these protected commands in a detached temporary worktree at the
candidate commit:

```powershell
py -3 verify_all.py
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
```

The final packet outcome is `PROMOTION_READY` only when all protected commands
pass and the candidate changes no path frozen as of `origin/main`.
